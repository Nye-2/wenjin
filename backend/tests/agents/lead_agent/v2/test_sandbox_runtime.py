import json
import sys
from unittest.mock import AsyncMock

import pytest

from src.agents.harness.command_audit import HarnessCommand, audit_command
from src.agents.lead_agent.v2.sandbox_runtime import (
    SandboxCommandExecutionError,
    run_python_script,
    run_python_smoke_check,
)
from src.agents.lead_agent.v2.workspace_sandbox import ENSURE_WORKSPACE_VENV_COMMAND
from src.sandbox.base import CommandResult, FileInfo
from src.sandbox.providers.local import LocalSandbox
from src.subagents.v2.base import SubagentContext
from src.subagents.v2.registry import REGISTRY
from src.subagents.v2.types.sandbox import SandboxPythonSubagent


class _FakeSandbox:
    def __init__(self, result: CommandResult | list[CommandResult]) -> None:
        self.results = list(result) if isinstance(result, list) else [result]
        self.commands: list[tuple[str, int]] = []
        self.command_options: list[dict] = []
        self.files: dict[str, str] = {}

    async def execute_command(self, command: str, timeout: int = 300, **kwargs) -> CommandResult:
        self.commands.append((command, timeout))
        self.command_options.append(dict(kwargs))
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]

    async def write_file(self, path: str, content: str, append: bool = False) -> None:
        self.files[path] = self.files.get(path, "") + content if append else content

    async def read_file(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    async def list_dir(self, path: str, max_depth: int = 2) -> list[FileInfo]:
        root = path.rstrip("/")
        entries: dict[str, FileInfo] = {}
        for file_path, content in self.files.items():
            if not file_path.startswith(f"{root}/"):
                continue
            relative = file_path[len(root) + 1 :]
            parts = relative.split("/")
            if len(parts) > max_depth + 1:
                continue
            current = root
            for part in parts[:-1]:
                current = f"{current}/{part}"
                entries.setdefault(
                    current,
                    FileInfo(name=part, path=current, is_dir=True, size=None),
                )
            entries[file_path] = FileInfo(
                name=parts[-1],
                path=file_path,
                is_dir=False,
                size=len(content.encode("utf-8")),
            )
        return [entries[key] for key in sorted(entries)]


class _FakeProvider:
    image = "fake-python:3.13"

    def __init__(self, result: CommandResult | list[CommandResult]) -> None:
        self.sandbox = _FakeSandbox(result)
        self.acquired: list[str] = []
        self.released: list[_FakeSandbox] = []

    async def acquire(self, thread_id: str) -> _FakeSandbox:
        self.acquired.append(thread_id)
        return self.sandbox

    async def release(self, sandbox: _FakeSandbox) -> None:
        self.released.append(sandbox)


class _LocalProvider:
    image = "local-python:3.13"

    def __init__(self, sandbox: LocalSandbox) -> None:
        self.sandbox = sandbox
        self.acquired: list[str] = []
        self.released: list[LocalSandbox] = []

    async def acquire(self, thread_id: str) -> LocalSandbox:
        self.acquired.append(thread_id)
        return self.sandbox

    async def release(self, sandbox: LocalSandbox) -> None:
        self.released.append(sandbox)


class _FakeWorkspaceSandboxManager:
    def __init__(self) -> None:
        self.created_jobs: list[dict] = []
        self.updated_jobs: list[dict] = []
        self.acquired_leases: list[dict] = []
        self.released_leases: list[dict] = []

    async def get_or_create_environment(
        self,
        *,
        workspace_id,
        sandbox_policy,
        resource_limits,
        runtime_image,
    ):
        return type(
            "Env",
            (),
            {
                "id": "env-1",
                "sandbox_id": f"workspace-{workspace_id}",
                "metadata_json": {"provider_key": f"workspace-{workspace_id}"},
            },
        )()

    async def create_job(self, **kwargs):
        self.created_jobs.append(kwargs)
        return type("Job", (), {"id": f"job-{len(self.created_jobs)}", "operation": kwargs["operation"]})()

    async def update_job(self, job_id, **kwargs):
        self.updated_jobs.append({"job_id": job_id, **kwargs})

    async def acquire_lease(self, **kwargs):
        self.acquired_leases.append(kwargs)
        return "lease-token-1"

    async def release_lease(self, **kwargs):
        self.released_leases.append(kwargs)


def _policy() -> dict:
    return {
        "mode": "required",
        "allowed_operations": ["run_python"],
        "resource_limits": {"cpu": 1, "memory_mb": 512, "timeout_seconds": 60},
    }


def _install_policy() -> dict:
    policy = _policy()
    policy["allowed_operations"] = ["run_python", "install_python_packages"]
    policy["allow_package_install"] = True
    return policy


@pytest.mark.asyncio
async def test_run_python_smoke_check_uses_fixed_command_and_releases_sandbox() -> None:
    stdout = json.dumps(
        {
            "ok": True,
            "mean": 5,
            "python": "3.13.0",
            "engine": "lead_agent_docker_sandbox",
        }
    )
    provider = _FakeProvider(CommandResult(stdout=stdout, stderr="", exit_code=0))
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_smoke_check(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="sandbox_validation__python_smoke",
        sandbox_policy=_policy(),
        provider=provider,
        manager=manager,
        billing_reservation_id="reservation-1",
    )

    assert provider.acquired == ["workspace-ws-1"]
    assert provider.released == [provider.sandbox]
    [(command, timeout)] = provider.sandbox.commands
    assert timeout == 60
    assert "statistics.mean(data)" in command
    assert "lead_agent_docker_sandbox" in command
    assert result["status"] == "completed"
    assert result["sandbox_environment_id"] == "env-1"
    assert result["sandbox_job_id"] == "job-1"
    assert result["mean"] == 5
    assert "LeadAgentRuntime / subagent node" in result["report_markdown"]
    assert manager.created_jobs[0]["operation"] == "smoke_check"
    assert manager.created_jobs[0]["metadata"]["credit_reservation_id"] == "reservation-1"


@pytest.mark.asyncio
async def test_run_python_smoke_check_runs_when_only_python3_is_on_path(tmp_path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", str(bin_dir))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sandbox = LocalSandbox(
        id="workspace-ws-local",
        path_mappings={"/workspace": str(workspace)},
    )
    provider = _LocalProvider(sandbox)
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_smoke_check(
        workspace_id="ws-local",
        execution_id="exec-local",
        node_id="sandbox_validation__python_smoke",
        sandbox_policy=_policy(),
        provider=provider,
        manager=manager,
    )

    assert result["status"] == "completed"
    assert result["mean"] == 5
    assert result["engine"] == "lead_agent_docker_sandbox"
    assert provider.acquired == ["workspace-ws-local"]
    assert provider.released == [sandbox]


@pytest.mark.asyncio
async def test_run_python_smoke_check_rejects_policy_without_run_python() -> None:
    provider = _FakeProvider(CommandResult(stdout="", stderr="", exit_code=0))

    with pytest.raises(PermissionError):
        await run_python_smoke_check(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="node",
            sandbox_policy={"mode": "none", "allowed_operations": []},
            provider=provider,
        )

    assert provider.acquired == []


@pytest.mark.asyncio
async def test_run_python_script_writes_script_and_returns_report() -> None:
    stdout = json.dumps({"ok": True, "metric": 0.42})
    provider = _FakeProvider(CommandResult(stdout=stdout, stderr="", exit_code=0))
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="import json\nprint(json.dumps({'ok': True, 'metric': 0.42}))\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
        billing_reservation_id="reservation-1",
    )

    assert provider.acquired == ["workspace-ws-1"]
    assert provider.released == [provider.sandbox]
    assert provider.sandbox.files["/workspace/scripts/analysis_probe.py"].startswith("import json")
    [(venv_command, _), (command, timeout)] = provider.sandbox.commands
    assert "python -m venv /workspace/.wenjin/env/python" in venv_command
    assert "python3 -m venv /workspace/.wenjin/env/python" in venv_command
    assert command == "/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis_probe.py"
    assert timeout == 60
    assert result["status"] == "completed"
    assert result["operation"] == "python_script"
    assert result["sandbox_environment_id"] == "env-1"
    assert result["sandbox_job_id"] == "job-1"
    assert result["parsed_stdout"] == {"ok": True, "metric": 0.42}
    assert result["script_hash"]
    assert "analysis_probe.py" in result["report_markdown"]
    assert manager.created_jobs[0]["operation"] == "run_python"
    assert manager.created_jobs[0]["metadata"]["credit_reservation_id"] == "reservation-1"
    run_audit = manager.created_jobs[0]["metadata"]["command_audit"]
    assert run_audit["verdict"] == "pass"
    assert run_audit["risk_level"] == "low"
    assert run_audit["command"]["argv"] == [
        "/workspace/.wenjin/env/python/bin/python",
        "/workspace/scripts/analysis_probe.py",
    ]
    assert result["command_audit"] == run_audit


@pytest.mark.asyncio
async def test_run_python_script_syncs_dataset_manifest_before_script_execution() -> None:
    stdout = json.dumps({"ok": True})
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(stdout=stdout, stderr="", exit_code=0),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()
    original_execute = provider.sandbox.execute_command

    async def _assert_manifest_before_script(command: str, timeout: int = 300, **kwargs) -> CommandResult:
        if command == "/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis_probe.py":
            manifest = json.loads(provider.sandbox.files["/workspace/datasets/manifest.json"])
            assert manifest["datasets"] == [
                {
                    "path": "/workspace/datasets/raw/survey.csv",
                    "source_id": "source-1",
                    "title": "Survey data",
                }
            ]
        return await original_execute(command, timeout=timeout, **kwargs)

    provider.sandbox.execute_command = _assert_manifest_before_script  # type: ignore[method-assign]

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="print('{\"ok\": true}')\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
        dataset_provenance=[
            {
                "path": "/workspace/datasets/raw/survey.csv",
                "source_id": "source-1",
                "title": "Survey data",
            },
            {"path": "/workspace/outputs/result.csv", "source_id": "bad"},
        ],
    )

    assert result["status"] == "completed"
    assert json.loads(provider.sandbox.files["/workspace/datasets/manifest.json"])["datasets"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "source_id": "source-1",
            "title": "Survey data",
        }
    ]


@pytest.mark.asyncio
async def test_run_python_script_reports_synced_dataset_provenance() -> None:
    stdout = json.dumps({"ok": True})
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(stdout=stdout, stderr="", exit_code=0),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="print('{\"ok\": true}')\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
        dataset_provenance=[
            {
                "path": "/workspace/datasets/raw/survey.csv",
                "source_id": "source-1",
                "title": "Survey data",
                "content_hash": "sha256:abc",
            },
            {"path": "/workspace/outputs/result.csv", "source_id": "bad"},
        ],
    )

    assert result["dataset_provenance"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "source_id": "source-1",
            "title": "Survey data",
            "content_hash": "sha256:abc",
        }
    ]
    report = result["report_markdown"]
    assert "## Dataset provenance" in report
    assert "/workspace/datasets/manifest.json" in report
    assert "/workspace/datasets/raw/survey.csv" in report
    assert "source-1" in report
    assert "/workspace/outputs/result.csv" not in report


@pytest.mark.asyncio
async def test_run_python_script_blocks_forbidden_command_policy_before_job(monkeypatch) -> None:
    provider = _FakeProvider(CommandResult(stdout="", stderr="", exit_code=0))
    manager = _FakeWorkspaceSandboxManager()

    def _forbidden_audit(*_args, **_kwargs):
        return audit_command(HarnessCommand(argv=("curl", "https://example.invalid"), cwd="/workspace"))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.sandbox_job_runner.audit_command",
        _forbidden_audit,
    )

    with pytest.raises(PermissionError, match="program_forbidden"):
        await run_python_script(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="analysis_probe",
            sandbox_policy=_policy(),
            script="print('blocked')",
            script_name="analysis_probe.py",
            provider=provider,
            manager=manager,
        )

    assert manager.created_jobs == []
    assert provider.acquired == []


@pytest.mark.asyncio
async def test_run_python_script_runs_with_local_sandbox_provider_interface(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sandbox = LocalSandbox(
        id="workspace-ws-local",
        path_mappings={"/workspace": str(workspace)},
    )
    provider = _LocalProvider(sandbox)
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-local",
        execution_id="exec-local",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="import json\nprint(json.dumps({'ok': True, 'rows': 2}, sort_keys=True))\n",
        script_name="probe.py",
        provider=provider,
        manager=manager,
    )

    assert provider.acquired == ["workspace-ws-local"]
    assert provider.released == [sandbox]
    assert await sandbox.read_file("/workspace/scripts/probe.py")
    assert result["status"] == "completed"
    assert result["parsed_stdout"] == {"ok": True, "rows": 2}
    assert manager.created_jobs[0]["operation"] == "run_python"
    assert manager.updated_jobs[-1] == {
        "job_id": "job-1",
        "status": "succeeded",
        "exit_code": 0,
    }


@pytest.mark.asyncio
async def test_run_python_script_persists_workspace_type_profile_in_layout_manifest(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sandbox = LocalSandbox(
        id="workspace-ws-local",
        path_mappings={"/workspace": str(workspace)},
    )
    provider = _LocalProvider(sandbox)
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-local",
        workspace_type="sci",
        execution_id="exec-local",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="import json\nprint(json.dumps({'ok': True}, sort_keys=True))\n",
        script_name="probe.py",
        provider=provider,
        manager=manager,
    )

    manifest = json.loads((workspace / ".wenjin" / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert manifest["workspace_id"] == "ws-local"
    assert manifest["sandbox_id"] == "workspace-ws-local"
    assert manifest["workspace_type"] == "sci"
    assert manifest["workspace_profile"]["workspace_type"] == "sci"
    assert "/workspace/main/main.tex" in manifest["workspace_profile"]["primary_files"]


@pytest.mark.asyncio
async def test_run_python_script_externalizes_large_stdout_before_returning_payload() -> None:
    stdout = "\n".join(f"row {index:03d} {'x' * 20}" for index in range(1, 31))
    provider = _FakeProvider(CommandResult(stdout=stdout, stderr="", exit_code=0))
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy={
            **_policy(),
            "output_budget": {
                "externalize_above_chars": 120,
                "preview_head_chars": 60,
                "preview_tail_chars": 40,
                "stdout_max_chars": 80,
            },
        },
        script="print('large')\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
    )

    assert result["stdout_externalized"]
    assert len(result["output_refs"]) == 1
    stdout_ref = result["output_refs"][0]
    assert stdout_ref.startswith(
        "/workspace/outputs/harness/exec-1/analysis_probe/analysis_probe/sandbox.run_python.stdout-"
    )
    assert stdout_ref.endswith(".txt")
    assert provider.sandbox.files[stdout_ref] == stdout
    assert "Full sandbox.run_python.stdout output saved to" in result["stdout"]
    assert "row 001" in result["stdout"]
    assert "row 030" in result["stdout"]
    assert stdout not in result["report_markdown"]


@pytest.mark.asyncio
async def test_run_python_script_discovers_user_reviewable_generated_artifacts() -> None:
    stdout = json.dumps({"ok": True})
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(stdout=stdout, stderr="", exit_code=0),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    original_execute = provider.sandbox.execute_command

    async def _execute_and_generate(command: str, timeout: int = 300, **kwargs) -> CommandResult:
        result = await original_execute(command, timeout=timeout, **kwargs)
        if command == "/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis_probe.py":
            provider.sandbox.files["/workspace/outputs/figure.png"] = "fake image bytes"
            provider.sandbox.files["/workspace/outputs/data/metrics.json"] = '{"accuracy": 0.91}'
            provider.sandbox.files["/workspace/reports/summary.md"] = "# Summary\n\nDone."
            provider.sandbox.files["/workspace/outputs/harness/exec-1/internal/tool.txt"] = "internal"
        return result

    provider.sandbox.execute_command = _execute_and_generate  # type: ignore[method-assign]

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="print('{\"ok\": true}')\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
    )

    generated = result["generated_artifacts"]
    assert [artifact["path"] for artifact in generated] == [
        "/workspace/outputs/data/metrics.json",
        "/workspace/outputs/figure.png",
        "/workspace/reports/summary.md",
    ]
    assert [artifact["artifact_kind"] for artifact in generated] == [
        "sandbox_output",
        "sandbox_output",
        "sandbox_report",
    ]
    assert all(artifact["materialization_status"] == "candidate" for artifact in generated)
    assert all(artifact["review_surface"] == "sandbox_artifact" for artifact in generated)
    assert all("content_hash" in artifact for artifact in generated)
    assert "/workspace/outputs/harness/exec-1/internal/tool.txt" not in {
        artifact["path"] for artifact in generated
    }
    assert "Generated artifacts" in result["report_markdown"]
    assert "/workspace/reports/summary.md" in result["report_markdown"]


@pytest.mark.asyncio
async def test_run_python_script_keeps_success_when_artifact_discovery_fails() -> None:
    stdout = json.dumps({"ok": True})
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(stdout=stdout, stderr="", exit_code=0),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    async def _broken_list_dir(path: str, max_depth: int = 2) -> list[FileInfo]:
        raise PermissionError(path)

    provider.sandbox.list_dir = _broken_list_dir  # type: ignore[method-assign]

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="print('{\"ok\": true}')\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
    )

    assert result["status"] == "completed"
    assert result["parsed_stdout"] == {"ok": True}
    assert result["generated_artifacts"] == []
    assert manager.updated_jobs[-1] == {"job_id": "job-1", "status": "succeeded", "exit_code": 0}


@pytest.mark.asyncio
async def test_run_python_script_installs_declared_dependency_hints_before_execution() -> None:
    stdout = json.dumps({"ok": True, "rows": 3})
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(stdout="installed pandas", stderr="", exit_code=0),
            CommandResult(stdout=stdout, stderr="", exit_code=0),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_install_policy(),
        script="import pandas as pd\nprint('{\"ok\": true, \"rows\": 3}')\n",
        script_name="analysis_probe.py",
        dependency_hints=["pandas==2.2.3"],
        provider=provider,
        manager=manager,
    )

    assert [job["operation"] for job in manager.created_jobs] == ["run_python", "install_dependencies"]
    install_job = manager.created_jobs[1]
    assert install_job["billable"] is False
    assert install_job["metadata"]["packages"] == ["pandas==2.2.3"]
    install_audit = install_job["metadata"]["command_audit"]
    assert install_audit["verdict"] == "warn"
    assert install_audit["risk_level"] == "medium"
    assert "package_install" in install_audit["reasons"]
    assert install_audit["command"]["network_profile"] == "package_index_only"
    assert result["install_command_audits"] == [install_audit]
    assert [options["network_profile"] for options in provider.sandbox.command_options] == [
        "none",
        "package_index_only",
        "none",
    ]
    assert provider.sandbox.commands[1][0].startswith(
        "/workspace/.wenjin/env/python/bin/python -m pip install"
    )
    assert "--cache-dir /workspace/.wenjin/cache/pip" in provider.sandbox.commands[1][0]
    assert "pandas==2.2.3" in provider.sandbox.commands[1][0]
    assert result["installed_packages"] == ["pandas==2.2.3"]
    assert result["retry_count"] == 0
    report = result["report_markdown"]
    assert "## Reproducibility" in report
    assert "/workspace/scripts/analysis_probe.py" in report
    assert "Requested dependencies: `pandas==2.2.3`" in report
    assert "Installed dependencies: `pandas==2.2.3`" in report
    assert "Install job ids: `job-2`" in report
    assert "Retry count: 0" in report
    assert "Run command audit: pass / low" in report


@pytest.mark.asyncio
async def test_run_python_script_installs_missing_module_and_retries_once() -> None:
    stdout = json.dumps({"ok": True})
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(
                stdout="",
                stderr="ModuleNotFoundError: No module named 'requests'",
                exit_code=1,
            ),
            CommandResult(stdout="installed requests", stderr="", exit_code=0),
            CommandResult(stdout=stdout, stderr="", exit_code=0),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_install_policy(),
        script="import requests\nprint('{\"ok\": true}')\n",
        script_name="analysis_probe.py",
        provider=provider,
        manager=manager,
    )

    assert [job["operation"] for job in manager.created_jobs] == ["run_python", "install_dependencies"]
    assert manager.created_jobs[1]["metadata"]["packages"] == ["requests"]
    assert [command for command, _ in provider.sandbox.commands] == [
        ENSURE_WORKSPACE_VENV_COMMAND,
        "/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis_probe.py",
        "/workspace/.wenjin/env/python/bin/python -m pip install --disable-pip-version-check --no-input --cache-dir /workspace/.wenjin/cache/pip requests",
        "/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis_probe.py",
    ]
    assert result["status"] == "completed"
    assert result["installed_packages"] == ["requests"]
    assert result["retry_count"] == 1


@pytest.mark.asyncio
async def test_run_python_script_marks_run_job_failed_when_dependency_install_fails() -> None:
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(
                stdout="",
                stderr="ModuleNotFoundError: No module named 'requests'",
                exit_code=1,
            ),
            CommandResult(stdout="", stderr="pip unavailable", exit_code=2),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    with pytest.raises(SandboxCommandExecutionError) as exc_info:
        await run_python_script(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="analysis_probe",
            sandbox_policy=_install_policy(),
            script="import requests\n",
            script_name="analysis_probe.py",
            provider=provider,
            manager=manager,
        )

    assert exc_info.value.output["operation"] == "install_dependencies"
    report = exc_info.value.output["report_markdown"]
    assert "## Recovery guidance" in report
    assert "Dependency installation failed before the Python script could be retried." in report
    assert "Check dependency_hints for a valid pinned package spec" in report
    assert "Install job ids: `job-2`" in report
    failed_updates = [
        update for update in manager.updated_jobs
        if update["status"] == "failed"
    ]
    assert {update["job_id"] for update in failed_updates} == {"job-1", "job-2"}
    assert manager.released_leases == [{"workspace_id": "ws-1", "lease_token": "lease-token-1"}]
    assert provider.released == [provider.sandbox]


@pytest.mark.asyncio
async def test_run_python_script_preserves_setup_failure_exit_code() -> None:
    provider = _FakeProvider(CommandResult(stdout="", stderr="venv unavailable", exit_code=127))
    manager = _FakeWorkspaceSandboxManager()

    with pytest.raises(SandboxCommandExecutionError):
        await run_python_script(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="analysis_probe",
            sandbox_policy=_policy(),
            script="print('ok')",
            script_name="analysis_probe.py",
            provider=provider,
            manager=manager,
        )

    run_failed_updates = [
        update for update in manager.updated_jobs if update["job_id"] == "job-1" and update["status"] == "failed"
    ]
    assert run_failed_updates[-1]["exit_code"] == 127


@pytest.mark.asyncio
async def test_run_python_script_raises_billable_error_for_nonzero_exit() -> None:
    provider = _FakeProvider(
        [
            CommandResult(stdout="", stderr="", exit_code=0),
            CommandResult(stdout="", stderr="boom", exit_code=2),
        ]
    )
    manager = _FakeWorkspaceSandboxManager()

    with pytest.raises(SandboxCommandExecutionError) as exc_info:
        await run_python_script(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="analysis_probe",
            sandbox_policy=_policy(),
            script="raise SystemExit(2)\n",
            script_name="analysis_probe.py",
            provider=provider,
            manager=manager,
        )

    assert provider.released == [provider.sandbox]
    assert exc_info.value.output["status"] == "failed"
    assert exc_info.value.output["exit_code"] == 2
    assert "boom" in exc_info.value.output["report_markdown"]


@pytest.mark.asyncio
async def test_sandbox_python_subagent_runs_through_lead_runtime_context(monkeypatch) -> None:
    calls: list[dict] = []

    async def _fake_run_python_smoke_check(**kwargs):
        calls.append(kwargs)
        return {
            "status": "completed",
            "operation": "smoke_check",
            "mean": 5,
            "python": "3.13.0",
            "engine": "lead_agent_docker_sandbox",
            "stdout": "{}",
            "stderr": "",
            "exit_code": 0,
            "docker_image": "fake-python:3.13",
            "report_markdown": "ok",
        }

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.run_python_smoke_check",
        _fake_run_python_smoke_check,
    )
    reservation_calls: list[dict] = []
    settlement_calls: list[dict] = []

    class _FakeCreditService:
        async def estimate_sandbox_reservation_credits(self, **kwargs):
            return 5

        async def estimate_sandbox_settlement_credits(self, **kwargs):
            return 1

        async def reserve_for_sandbox_operation(self, **kwargs):
            reservation_calls.append(kwargs)
            return type("Reservation", (), {"id": "reservation-1", "reserved_credits": 5})()

        async def settle_sandbox_reservation(self, **kwargs):
            settlement_calls.append(kwargs)
            return (
                type("Reservation", (), {"id": "reservation-1", "status": "settled"})(),
                type("Tx", (), {"id": "credit-tx-1", "balance_after": 9})(),
            )

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.CreditService",
        lambda: _FakeCreditService(),
    )

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"operation": "smoke_check", "node_id": "phase__node", "user_id": "user-1"},
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    result = await SandboxPythonSubagent().run(ctx)

    assert calls[0]["workspace_id"] == "ws-1"
    assert calls[0]["execution_id"] == "exec-1"
    assert calls[0]["node_id"] == "phase__node"
    assert calls[0]["sandbox_policy"] == _policy()
    assert calls[0]["billing_reservation_id"] == "reservation-1"
    assert result.output["status"] == "completed"
    assert result.output["billing"]["transaction_id"] == "credit-tx-1"
    reservation_call = dict(reservation_calls[0])
    assert reservation_call["expires_at"] is not None
    reservation_call.pop("expires_at")
    assert reservation_call == {
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "execution_id": "exec-1",
        "node_id": "phase__node",
        "operation": "run_python",
        "estimated_credits": 5,
        "metadata": {"source": "sandbox_python_subagent"},
    }
    assert settlement_calls[0]["reservation_id"] == "reservation-1"
    assert settlement_calls[0]["operation"] == "run_python"
    assert result.tool_calls and result.tool_calls[0]["name"] == "sandbox.run_python"
    assert result.tool_calls[0]["billing"]["credits_charged"] == 1


@pytest.mark.asyncio
async def test_sandbox_python_subagent_settles_user_code_failure(monkeypatch) -> None:
    async def _fake_run_python_script(**kwargs):
        raise SandboxCommandExecutionError(
            "script failed",
            output={"status": "failed", "exit_code": 1},
        )

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.run_python_script",
        _fake_run_python_script,
    )
    fake_credit_service = type(
        "CreditServiceStub",
        (),
        {
            "estimate_sandbox_reservation_credits": AsyncMock(return_value=5),
            "estimate_sandbox_settlement_credits": AsyncMock(return_value=1),
            "reserve_for_sandbox_operation": AsyncMock(
                return_value=type("Reservation", (), {"id": "reservation-2", "reserved_credits": 5})()
            ),
            "settle_sandbox_reservation": AsyncMock(
                return_value=(
                    type("Reservation", (), {"id": "reservation-2", "status": "settled"})(),
                    type("Tx", (), {"id": "credit-tx-2", "balance_after": 9})(),
                )
            ),
            "release_reservation": AsyncMock(),
        },
    )()
    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.CreditService",
        lambda: fake_credit_service,
    )

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={
            "operation": "python_script",
            "node_id": "phase__probe",
            "user_id": "user-1",
            "script": "raise SystemExit(1)",
        },
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    with pytest.raises(SandboxCommandExecutionError):
        await SandboxPythonSubagent().run(ctx)

    fake_credit_service.settle_sandbox_reservation.assert_awaited_once()
    fake_credit_service.release_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_sandbox_python_subagent_requires_user_id_for_billing() -> None:
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"operation": "smoke_check", "node_id": "phase__node"},
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    with pytest.raises(ValueError, match="sandbox billing requires user_id"):
        await SandboxPythonSubagent().run(ctx)


@pytest.mark.asyncio
async def test_sandbox_python_subagent_runs_declared_python_script(monkeypatch) -> None:
    calls: list[dict] = []

    async def _fake_run_python_script(**kwargs):
        calls.append(kwargs)
        return {
            "status": "completed",
            "operation": "python_script",
            "stdout": "{}",
            "stderr": "",
            "exit_code": 0,
            "docker_image": "fake-python:3.13",
            "script_hash": "hash-1",
            "report_markdown": "script ok",
        }

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.run_python_script",
        _fake_run_python_script,
    )
    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.CreditService",
        lambda: type(
            "CreditServiceStub",
            (),
            {
                "estimate_sandbox_reservation_credits": AsyncMock(return_value=5),
                "estimate_sandbox_settlement_credits": AsyncMock(return_value=1),
                "reserve_for_sandbox_operation": AsyncMock(
                    return_value=type("Reservation", (), {"id": "reservation-2", "reserved_credits": 5})()
                ),
                "settle_sandbox_reservation": AsyncMock(
                    return_value=(
                        type("Reservation", (), {"id": "reservation-2", "status": "settled"})(),
                        type("Tx", (), {"id": "credit-tx-2", "balance_after": 9})(),
                    )
                ),
            },
        )(),
    )

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={
            "operation": "python_script",
            "node_id": "phase__probe",
            "user_id": "user-1",
            "script": "print('ok')",
            "script_name": "probe.py",
            "dependency_hints": ["pandas==2.2.3"],
        },
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    result = await SandboxPythonSubagent().run(ctx)

    assert calls[0]["workspace_id"] == "ws-1"
    assert calls[0]["execution_id"] == "exec-1"
    assert calls[0]["node_id"] == "phase__probe"
    assert calls[0]["script"] == "print('ok')"
    assert calls[0]["script_name"] == "probe.py"
    assert calls[0]["dependency_hints"] == ["pandas==2.2.3"]
    assert calls[0]["billing_reservation_id"] == "reservation-2"
    assert result.output["operation"] == "python_script"
    assert result.tool_calls and result.tool_calls[0]["args"]["operation"] == "python_script"


def test_sandbox_python_subagent_is_registered() -> None:
    assert REGISTRY.get("sandbox_python") is SandboxPythonSubagent

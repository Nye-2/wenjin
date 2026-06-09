from __future__ import annotations

import asyncio

import pytest

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext
from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools
from src.agents.harness.scheduler import WorkspaceToolQueueTimeout, WorkspaceToolScheduler
from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError


def _ctx(publish_event=None, context_bundle: dict | None = None) -> HarnessRunContext:
    return HarnessRunContext(
        workspace_id="ws-1",
        user_id="user-1",
        execution_id="exec-1",
        node_id="node-1",
        invocation_id="invocation-1",
        workspace_type="sci",
        capability_id="capability-1",
        context_bundle=context_bundle or {},
        capability_policy={
            "sandbox_policy": {
                "mode": "required",
                "allowed_operations": ["run_python", "install_python_packages"],
                "allow_package_install": True,
                "resource_limits": {"timeout_seconds": 60},
            }
        },
        publish_event=publish_event,
    )


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run_python_script(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "completed",
            "stdout": "{\"ok\": true}",
            "stderr": "",
            "parsed_stdout": {"ok": True},
            "sandbox_job_id": "job-1",
        }


class _AuditedRunner:
    async def run_python_script(self, **kwargs):
        return {
            "status": "completed",
            "stdout": "{\"ok\": true}",
            "stderr": "",
            "parsed_stdout": {"ok": True},
            "sandbox_job_id": "job-1",
            "command_audit": {
                "verdict": "pass",
                "risk_level": "low",
                "reasons": [],
                "command": {
                    "argv": [
                        "/workspace/.wenjin/env/python/bin/python",
                        "/workspace/scripts/analysis.py",
                    ],
                    "shell_command": None,
                    "cwd": "/workspace",
                    "env": {},
                    "network_profile": "none",
                    "timeout_seconds": None,
                    "output_bytes_cap": None,
                },
            },
        }


class _ReproducibleRunner:
    async def run_python_script(self, **kwargs):
        return {
            "status": "completed",
            "stdout": "{\"ok\": true}",
            "stderr": "",
            "parsed_stdout": {"ok": True},
            "sandbox_environment_id": "env-1",
            "sandbox_job_id": "job-1",
            "script_name": kwargs["script_name"],
            "script_path": f"/workspace/scripts/{kwargs['script_name']}",
            "dependency_hints": ["pandas", "numpy"],
            "installed_packages": ["pandas", "numpy"],
            "generated_artifacts": [
                {
                    "path": "/workspace/reports/analysis.md",
                    "name": "analysis.md",
                    "kind": "markdown",
                    "description": "Readable experiment report.",
                    "size_bytes": 128,
                    "source_script": "/workspace/scripts/analysis.py",
                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                    "notes": "Ready for review.",
                }
            ],
            "command_audit": {
                "verdict": "pass",
                "risk_level": "low",
                "reasons": [],
                "command": {
                    "argv": [
                        "/workspace/.wenjin/env/python/bin/python",
                        "/workspace/scripts/analysis.py",
                    ],
                    "shell_command": None,
                    "cwd": "/workspace",
                    "env": {},
                    "network_profile": "none",
                    "timeout_seconds": 30,
                    "output_bytes_cap": 20000,
                },
            },
            "install_job_ids": ["install-1"],
            "retry_count": 1,
            "install_command_audits": [
                {
                    "verdict": "pass",
                    "risk_level": "low",
                    "reasons": [],
                    "command": {
                        "argv": [
                            "/workspace/.wenjin/env/python/bin/python",
                            "-m",
                            "pip",
                            "install",
                            "pandas",
                            "numpy",
                        ],
                        "shell_command": None,
                        "cwd": "/workspace",
                        "env": {},
                        "network_profile": "package_install",
                        "timeout_seconds": 120,
                        "output_bytes_cap": 20000,
                    },
                }
            ],
        }


class _DatasetProvenanceRunner:
    async def run_python_script(self, **kwargs):
        return {
            "status": "completed",
            "stdout": "{\"ok\": true}",
            "stderr": "",
            "parsed_stdout": {"ok": True},
            "sandbox_environment_id": "env-1",
            "sandbox_job_id": "job-1",
            "script_name": kwargs["script_name"],
            "script_path": f"/workspace/scripts/{kwargs['script_name']}",
            "dependency_hints": [],
            "installed_packages": [],
            "generated_artifacts": [],
            "dataset_provenance": [
                {
                    "path": "/workspace/datasets/raw/survey.csv",
                    "source_id": "source-1",
                    "title": "Survey data",
                    "content_hash": "sha256:abc",
                }
            ],
            "command_audit": {
                "verdict": "pass",
                "risk_level": "low",
                "reasons": [],
                "command": {
                    "argv": [
                        "/workspace/.wenjin/env/python/bin/python",
                        "/workspace/scripts/analysis.py",
                    ],
                    "shell_command": None,
                    "cwd": "/workspace",
                    "env": {},
                    "network_profile": "none",
                    "timeout_seconds": 30,
                    "output_bytes_cap": 20000,
                },
            },
        }


class _FailingRunner:
    async def run_python_script(self, **kwargs):
        raise SandboxCommandExecutionError(
            "Docker sandbox Python script failed (exit_code=2, stderr=boom)",
            output={
                "status": "failed",
                "operation": "python_script",
                "stdout": "",
                "stderr": "boom",
                "parsed_stdout": {},
                "exit_code": 2,
                "sandbox_environment_id": "env-1",
                "sandbox_job_id": "job-1",
                "script_name": kwargs["script_name"],
                "script_path": f"/workspace/scripts/{kwargs['script_name']}",
                "dependency_hints": ["pandas"],
                "retry_count": 0,
                "output_refs": [],
            },
        )


@pytest.mark.asyncio
async def test_scheduler_serializes_same_workspace_calls() -> None:
    scheduler = WorkspaceToolScheduler()
    running = 0
    max_running = 0

    async def job() -> str:
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        running -= 1
        return "ok"

    result = await asyncio.gather(
        scheduler.run("ws-1", job),
        scheduler.run("ws-1", job),
    )

    assert result == ["ok", "ok"]
    assert max_running == 1


@pytest.mark.asyncio
async def test_scheduler_releases_idle_workspace_lock_after_run() -> None:
    scheduler = WorkspaceToolScheduler()

    result = await scheduler.run("ws-1", lambda: "ok")

    assert result == "ok"
    assert scheduler._locks == {}


@pytest.mark.asyncio
async def test_scheduler_times_out_when_workspace_queue_is_busy() -> None:
    scheduler = WorkspaceToolScheduler()
    release = asyncio.Event()

    async def blocker() -> str:
        await release.wait()
        return "done"

    task = asyncio.create_task(scheduler.run("ws-1", blocker))
    await asyncio.sleep(0)
    with pytest.raises(WorkspaceToolQueueTimeout):
        await scheduler.run("ws-1", lambda: asyncio.sleep(0), timeout_seconds=0.001)
    release.set()
    await task


@pytest.mark.asyncio
async def test_scheduler_cleans_timeout_waiter_after_running_job_completes() -> None:
    scheduler = WorkspaceToolScheduler()
    release = asyncio.Event()

    async def blocker() -> str:
        await release.wait()
        return "done"

    task = asyncio.create_task(scheduler.run("ws-1", blocker))
    await asyncio.sleep(0)

    with pytest.raises(WorkspaceToolQueueTimeout):
        await scheduler.run("ws-1", lambda: "late", timeout_seconds=0.001)
    assert "ws-1" in scheduler._locks

    release.set()
    assert await task == "done"
    assert scheduler._locks == {}


@pytest.mark.asyncio
async def test_run_python_uses_existing_sandbox_job_runner_through_scheduler() -> None:
    runner = _FakeRunner()
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=runner,
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
        dependency_hints=["pandas"],
    )

    assert result.structured_payload["sandbox_job_id"] == "job-1"
    assert result.structured_payload["parsed_stdout"] == {"ok": True}
    assert "completed" in result.preview_text
    [call] = runner.calls
    assert call["workspace_id"] == "ws-1"
    assert call["execution_id"] == "exec-1"
    assert call["node_id"] == "node-1"
    assert call["sandbox_policy"]["allowed_operations"] == ["run_python", "install_python_packages"]
    assert call["dependency_hints"] == ["pandas"]


@pytest.mark.asyncio
async def test_run_python_passes_dataset_provenance_from_context_bundle() -> None:
    runner = _FakeRunner()
    tool = SandboxExecutionTools(
        context=_ctx(
            context_bundle={
                "workspace_file_summary": {
                    "dataset_provenance": [
                        {
                            "path": "/workspace/datasets/raw/survey.csv",
                            "source_id": "source-1",
                            "title": "Survey data",
                        }
                    ]
                }
            }
        ),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=runner,
        scheduler=WorkspaceToolScheduler(),
    )

    await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
        dependency_hints=["pandas"],
    )

    [call] = runner.calls
    assert call["dataset_provenance"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "source_id": "source-1",
            "title": "Survey data",
        }
    ]


@pytest.mark.asyncio
async def test_run_python_returns_execution_manifest() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
            max_sandbox_seconds=45,
        ),
        runner=_FakeRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="../../bad script",
        dependency_hints=["pandas"],
    )

    manifest = result.structured_payload["execution_manifest"]
    assert manifest["schema"] == "wenjin.harness.run_python.execution_manifest.v1"
    assert manifest["tool"] == "sandbox.run_python"
    assert manifest["workspace_id"] == "ws-1"
    assert manifest["execution_id"] == "exec-1"
    assert manifest["node_id"] == "node-1"
    assert manifest["script_name"] == ".._.._bad_script.py"
    assert manifest["script_path"] == "/workspace/scripts/.._.._bad_script.py"
    assert manifest["dependency_hints"] == ["pandas"]
    assert manifest["network_profile"] == "none"
    assert manifest["timeout_seconds"] == 30


@pytest.mark.asyncio
async def test_run_python_returns_reproducibility_manifest() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
            max_sandbox_seconds=60,
        ),
        runner=_ReproducibleRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
        dependency_hints=["pandas", "numpy"],
    )

    manifest = result.structured_payload["reproducibility_manifest"]
    assert manifest == {
        "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
        "tool": "sandbox.run_python",
        "workspace_id": "ws-1",
        "execution_id": "exec-1",
        "node_id": "node-1",
        "invocation_id": "invocation-1",
        "script": {
            "name": "analysis.py",
            "path": "/workspace/scripts/analysis.py",
        },
        "sandbox": {
            "environment_id": "env-1",
            "run_job_id": "job-1",
            "install_job_ids": ["install-1"],
            "network_profile": "none",
            "timeout_seconds": 30,
            "retry_count": 1,
        },
        "dependencies": {
            "requested": ["pandas", "numpy"],
            "installed": ["pandas", "numpy"],
        },
        "artifacts": [
            {
                "path": "/workspace/reports/analysis.md",
                "name": "analysis.md",
                "kind": "markdown",
                "description": "Readable experiment report.",
                "size_bytes": 128,
                "source_script": "/workspace/scripts/analysis.py",
                "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                "notes": "Ready for review.",
            }
        ],
        "command_audit": {
            "run_verdict": "pass",
            "run_risk_level": "low",
            "install_verdicts": ["pass"],
            "install_risk_levels": ["low"],
        },
    }


@pytest.mark.asyncio
async def test_run_python_returns_experiment_narrative_for_long_running_context() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(
            context_bundle={
                "workspace_file_summary": {
                    "dataset_provenance": [
                        {
                            "path": "/workspace/datasets/raw/survey.csv",
                            "source_id": "source-1",
                            "title": "Survey data",
                            "content_hash": "sha256:abc",
                        }
                    ]
                }
            }
        ),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
            max_sandbox_seconds=60,
        ),
        runner=_ReproducibleRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
        dependency_hints=["pandas", "numpy"],
    )

    narrative = result.structured_payload["experiment_narrative"]
    assert narrative == {
        "schema": "wenjin.harness.run_python.experiment_narrative.v1",
        "status": "completed",
        "script_path": "/workspace/scripts/analysis.py",
        "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
        "artifact_paths": ["/workspace/reports/analysis.md"],
        "dependency_names": ["pandas", "numpy"],
        "command_risk": {
            "run": "low",
            "install": ["low"],
        },
        "next_actions": [
            "Review generated artifacts before using them as workspace deliverables.",
            "Reuse the same script path and dataset manifest for follow-up experiments.",
        ],
    }
    report = result.structured_payload["report_markdown"]
    assert "## Experiment narrative" in report
    assert "Status: `completed`" in report
    assert "/workspace/datasets/raw/survey.csv" in report
    assert "/workspace/reports/analysis.md" in report


@pytest.mark.asyncio
async def test_run_python_reproducibility_manifest_includes_dataset_provenance() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
            max_sandbox_seconds=60,
        ),
        runner=_DatasetProvenanceRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
    )

    manifest = result.structured_payload["reproducibility_manifest"]
    assert manifest["datasets"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "source_id": "source-1",
            "title": "Survey data",
            "content_hash": "sha256:abc",
        }
    ]


@pytest.mark.asyncio
async def test_run_python_manifest_filters_invalid_workspace_paths() -> None:
    class InvalidPathRunner:
        async def run_python_script(self, **kwargs):
            return {
                "status": "completed",
                "stdout": "{\"ok\": true}",
                "stderr": "",
                "parsed_stdout": {"ok": True},
                "sandbox_job_id": "job-1",
                "script_path": "/workspace/scripts/../.env",
                "dataset_provenance": [
                    {"path": "/workspace/datasets/../.env", "source_id": "bad"},
                    {"path": "/workspace/datasets/raw/survey.csv", "source_id": "source-1"},
                ],
                "generated_artifacts": [
                    {"path": "/workspace/outputs/../.env", "artifact_kind": "secret"},
                    {"path": "/workspace/reports/summary.md", "artifact_kind": "report"},
                ],
            }

    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=InvalidPathRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(script="print('{\"ok\": true}')", script_name="analysis.py")

    manifest = result.structured_payload["reproducibility_manifest"]
    narrative = result.structured_payload["experiment_narrative"]
    assert manifest["script"]["path"] == ""
    assert manifest["datasets"] == [
        {"path": "/workspace/datasets/raw/survey.csv", "source_id": "source-1"}
    ]
    assert manifest["artifacts"] == [
        {"path": "/workspace/reports/summary.md", "artifact_kind": "report"}
    ]
    assert narrative["script_path"] == ""
    assert narrative["dataset_paths"] == ["/workspace/datasets/raw/survey.csv"]
    assert narrative["artifact_paths"] == ["/workspace/reports/summary.md"]
    assert "/workspace/outputs/../.env" not in result.structured_payload["report_markdown"]


@pytest.mark.asyncio
async def test_run_python_sanitizes_script_name_before_runner_boundary() -> None:
    runner = _FakeRunner()
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.run_python"})),
        runner=runner,
        scheduler=WorkspaceToolScheduler(),
    )

    await tool.run_python(
        script="print('ok')",
        script_name="../../bad script",
    )

    [call] = runner.calls
    assert call["script_name"] == ".._.._bad_script.py"


@pytest.mark.asyncio
async def test_run_python_downgrades_user_code_failure_with_classification() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=_FailingRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="raise SystemExit(2)",
        script_name="analysis.py",
        dependency_hints=["pandas"],
    )

    assert result.structured_payload["status"] == "failed"
    assert result.structured_payload["exit_code"] == 2
    assert result.error == "python_exit_nonzero: exit_code=2"
    classification = result.structured_payload["failure_classification"]
    assert classification == {
        "schema": "wenjin.harness.run_python.failure_classification.v1",
        "category": "user_code",
        "reason": "nonzero_exit",
        "failure_code": "python_exit_nonzero",
        "exit_code": 2,
        "stderr_preview": "boom",
        "recoverable": True,
    }
    assert result.structured_payload["execution_manifest"]["script_path"] == "/workspace/scripts/analysis.py"
    report = result.structured_payload["report_markdown"]
    assert "Recovery guidance" in report
    assert "Revise the Python script" in report


@pytest.mark.asyncio
async def test_run_python_propagates_externalized_output_refs() -> None:
    class ExternalizedRunner:
        async def run_python_script(self, **kwargs):
            return {
                "status": "completed",
                "stdout": "Total output lines: 30\n\nrow 001\n\n[Full sandbox.run_python.stdout output saved to /workspace/outputs/harness/exec-1/node-1/node-1/sandbox.run_python.stdout.txt]\n\nrow 030",
                "stderr": "",
                "parsed_stdout": {},
                "sandbox_job_id": "job-1",
                "stdout_externalized": True,
                "output_refs": [
                    "/workspace/outputs/harness/exec-1/node-1/node-1/sandbox.run_python.stdout.txt"
                ],
            }

    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=ExternalizedRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(script="print('large')", script_name="analysis.py")

    assert result.externalized
    assert result.truncated
    assert result.output_refs == (
        "/workspace/outputs/harness/exec-1/node-1/node-1/sandbox.run_python.stdout.txt",
    )


@pytest.mark.asyncio
async def test_run_python_publishes_command_audit_event() -> None:
    events: list[tuple[str, str, dict]] = []

    async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
        events.append((execution_id, event_type, payload))

    tool = SandboxExecutionTools(
        context=_ctx(publish_event=publish_event),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=_AuditedRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(script="print({'ok': True})", script_name="analysis.py")

    assert result.structured_payload["command_audit"]["verdict"] == "pass"
    audit_events = [event for event in events if event[1] == "execution.harness.command_audit"]
    assert audit_events
    _, _, payload = audit_events[-1]
    assert payload["visibility"] == "team_visible"
    assert payload["sequence_kind"] == "audit"
    assert payload["payload"]["name"] == "sandbox.run_python"
    assert payload["payload"]["sandbox_job_id"] == "job-1"
    assert payload["payload"]["command_audit"]["risk_level"] == "low"


@pytest.mark.asyncio
async def test_run_python_requires_explicit_permission() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(),
        runner=_FakeRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    with pytest.raises(PermissionError, match="run_python"):
        await tool.run_python(script="print('no')", script_name="analysis.py")

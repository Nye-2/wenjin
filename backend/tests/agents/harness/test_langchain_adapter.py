from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents.harness.args_summary import summarize_tool_args
from src.agents.harness.langchain_adapter import _tool_result_metadata, build_langchain_tools
from src.sandbox.providers.local import LocalSandbox
from src.subagents.v2.base import SubagentContext


def _ctx(
    sandbox: LocalSandbox,
    *,
    tool_records: list[dict] | None = None,
    publish_event=None,
    tools: list[str] | None = None,
    capability_policy: dict | None = None,
    skill: dict | None = None,
) -> SubagentContext:
    workspace_data = {"_harness_sandbox": sandbox}
    if tool_records is not None:
        workspace_data["_harness_tool_records"] = tool_records
    selected_tools = tools or ["sandbox.read_file"]
    return SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="read file",
        inputs={"user_id": "user-1", "workspace_type": "sci", "capability_id": "capability-1"},
        tools=selected_tools,
        workspace_data=workspace_data,
        publish_event=publish_event,
        capability_policy=capability_policy or {
            "allowed_tools": ["sandbox.read_file"],
            "sandbox_policy": {
                "output_budget": {
                    "read_max_chars": 20,
                    "externalize_above_chars": 1000,
                }
            },
        },
        skill=skill,
    )


class _Provider:
    def __init__(self, sandbox: LocalSandbox) -> None:
        self.sandbox = sandbox

    async def acquire(self, _sandbox_key: str) -> LocalSandbox:
        return self.sandbox

    async def release(self, _sandbox: LocalSandbox) -> None:
        return None


@pytest.mark.asyncio
async def test_langchain_read_file_tool_accepts_max_chars_to_narrow_budget() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/main/paper.txt", "abcdefghijkl\n")
        tools = build_langchain_tools(_ctx(sandbox), ["sandbox.read_file"])
        assert [tool.name for tool in tools] == ["sandbox_read_file", "sandbox_read_output_ref"]
        tool = tools[0]

        raw = await tool.ainvoke(
            {
                "path": "/workspace/main/paper.txt",
                "max_chars": 4,
            }
        )

    payload = json.loads(raw)
    assert payload["preview"] == "abcd"
    assert payload["truncated"] is True


@pytest.mark.asyncio
async def test_langchain_read_output_ref_tool_uses_explicit_ref_schema() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        output_ref = "/workspace/tmp/tasks/.harness/outputs/exec-1/node-1/invocation-1/stdout.txt"
        await sandbox.write_file(output_ref, "alpha\nbeta\ngamma\n")
        [tool] = build_langchain_tools(
            _ctx(
                sandbox,
                tools=["sandbox.read_output_ref"],
                capability_policy={
                    "allowed_tools": ["sandbox.read_output_ref"],
                    "permissions": ["filesystem.read"],
                    "sandbox_policy": {"output_budget": {"read_max_chars": 20}},
                },
                skill={"allowed_tools": ["sandbox.read_output_ref"]},
            ),
            ["sandbox.read_output_ref"],
        )

        raw = await tool.ainvoke(
            {
                "output_ref": output_ref,
                "start_line": 2,
                "end_line": 2,
            }
        )

    payload = json.loads(raw)
    assert payload["preview"] == "beta\n"
    assert payload["payload"]["output_ref"] == output_ref


@pytest.mark.asyncio
async def test_langchain_file_tools_refresh_workspace_type_profile_without_injected_sandbox(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        provider = _Provider(sandbox)

        class _Session:
            async def build_context(self, *, workspace_id, workspace_type, sandbox_policy):
                return SimpleNamespace(
                    provider=provider,
                    sandbox_key=f"workspace-{workspace_id}",
                    workspace_type=workspace_type,
                )

        monkeypatch.setattr(
            "src.agents.harness.langchain_adapter.SandboxRuntimeSession",
            _Session,
        )
        ctx = SubagentContext(
            workspace_id="ws-1",
            execution_id="exec-1",
            prompt="list workspace",
            inputs={"user_id": "user-1", "workspace_type": "sci", "capability_id": "capability-1"},
            tools=["sandbox.list_dir"],
            workspace_data={},
            capability_policy={
                "allowed_tools": ["sandbox.list_dir"],
                "sandbox_policy": {},
            },
        )
        [tool] = build_langchain_tools(ctx, ["sandbox.list_dir"])

        raw = await tool.ainvoke({"path": "/workspace/main"})

        payload = json.loads(raw)
        manifest = json.loads((workspace / ".wenjin" / "manifest.json").read_text(encoding="utf-8"))
        assert payload["payload"]["path"] == "/workspace/main"
        assert manifest["workspace_type"] == "sci"
        assert manifest["workspace_profile"]["workspace_type"] == "sci"


@pytest.mark.asyncio
async def test_langchain_register_dataset_records_manifest_file_change() -> None:
    records: list[dict] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/datasets/sample.csv", "x,y\n1,2\n")
        [tool] = build_langchain_tools(
            _ctx(
                sandbox,
                tool_records=records,
                tools=["sandbox.register_dataset"],
                capability_policy={
                    "allowed_tools": ["sandbox.register_dataset"],
                    "permissions": ["filesystem.write", "filesystem.diff"],
                },
                skill={"allowed_tools": ["sandbox.register_dataset"]},
            ),
            ["sandbox.register_dataset"],
        )

        raw = await tool.ainvoke(
            {
                "path": "/workspace/datasets/sample.csv",
                "source_id": "upload-1",
                "license": "CC-BY-4.0",
            }
        )

    payload = json.loads(raw)
    assert payload["payload"]["schema"] == "wenjin.harness.dataset_registration.v1"
    assert payload["payload"]["status"] == "registered"
    assert payload["file_change"]["path"] == "/workspace/datasets/manifest.json"
    assert records[-1]["name"] == "sandbox.register_dataset"
    assert records[-1]["status"] == "completed"
    assert records[-1]["file_changes"][0]["path"] == "/workspace/datasets/manifest.json"


@pytest.mark.asyncio
async def test_langchain_register_artifact_records_manifest_file_change() -> None:
    records: list[dict] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/outputs/result.csv", "x,y\n1,2\n")
        [tool] = build_langchain_tools(
            _ctx(
                sandbox,
                tool_records=records,
                tools=["sandbox.register_artifact"],
                capability_policy={
                    "allowed_tools": ["sandbox.register_artifact"],
                    "permissions": ["filesystem.write", "filesystem.diff"],
                },
                skill={"allowed_tools": ["sandbox.register_artifact"]},
            ),
            ["sandbox.register_artifact"],
        )

        raw = await tool.ainvoke(
            {
                "path": "/workspace/outputs/result.csv",
                "title": "Cleaned panel metrics",
                "artifact_kind": "table",
            }
        )

    payload = json.loads(raw)
    assert payload["payload"]["schema"] == "wenjin.harness.artifact_registration.v1"
    assert payload["payload"]["status"] == "registered"
    assert payload["file_change"]["path"] == "/workspace/reports/artifacts.json"
    assert records[-1]["name"] == "sandbox.register_artifact"
    assert records[-1]["status"] == "completed"
    assert records[-1]["file_changes"][0]["path"] == "/workspace/reports/artifacts.json"


@pytest.mark.asyncio
async def test_langchain_apply_patch_records_multiple_file_changes() -> None:
    records: list[dict] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/main/paper.tex", "Title: Old\n")
        await sandbox.write_file("/workspace/scripts/analysis.py", "print('old')\n")
        [tool] = build_langchain_tools(
            _ctx(
                sandbox,
                tool_records=records,
                tools=["sandbox.apply_patch"],
                capability_policy={
                    "allowed_tools": ["sandbox.apply_patch"],
                    "permissions": ["filesystem.write", "filesystem.diff"],
                },
                skill={"allowed_tools": ["sandbox.apply_patch"]},
            ),
            ["sandbox.apply_patch"],
        )

        raw = await tool.ainvoke(
            {
                "edits": [
                    {
                        "path": "/workspace/main/paper.tex",
                        "old": "Title: Old",
                        "new": "Title: New",
                    },
                    {
                        "path": "/workspace/scripts/analysis.py",
                        "old": "print('old')",
                        "new": "print('new')",
                    },
                ]
            }
        )

    payload = json.loads(raw)
    assert payload["payload"]["schema"] == "wenjin.harness.structured_patch.v1"
    assert payload["payload"]["changed_paths"] == [
        "/workspace/main/paper.tex",
        "/workspace/scripts/analysis.py",
    ]
    assert [change["path"] for change in payload["file_changes"]] == [
        "/workspace/main/paper.tex",
        "/workspace/scripts/analysis.py",
    ]
    assert records[-1]["name"] == "sandbox.apply_patch"
    assert [change["path"] for change in records[-1]["file_changes"]] == [
        "/workspace/main/paper.tex",
        "/workspace/scripts/analysis.py",
    ]


@pytest.mark.asyncio
async def test_langchain_tool_downgrades_harness_exception_to_recoverable_result() -> None:
    records: list[dict] = []
    events: list[tuple[str, str, dict]] = []

    async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
        events.append((execution_id, event_type, payload))

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/.env", "SECRET=1\n")
        tools = build_langchain_tools(
            _ctx(sandbox, tool_records=records, publish_event=publish_event),
            ["sandbox.read_file"],
        )
        tool = tools[0]

        raw = await tool.ainvoke({"path": "/workspace/.env"})

    payload = json.loads(raw)
    assert payload["error"] == "HarnessPathError: protected path is not accessible: /workspace/.env"
    assert payload["payload"]["error_code"] == "tool_error"
    assert payload["payload"]["exception_type"] == "HarnessPathError"
    assert records[-1]["status"] == "failed"
    assert records[-1]["metadata"]["recoverable_error"] == payload["error"]
    failed_events = [event for event in events if event[1] == "execution.harness.tool_call.failed"]
    assert failed_events
    assert failed_events[-1][2]["payload"]["recoverable_error"] == payload["error"]


@pytest.mark.asyncio
async def test_langchain_tool_downgrades_input_validation_error_to_recoverable_result() -> None:
    records: list[dict] = []
    events: list[tuple[str, str, dict]] = []

    async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
        events.append((execution_id, event_type, payload))

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/main/paper.txt", "abcdefghijkl\n")
        tools = build_langchain_tools(
            _ctx(sandbox, tool_records=records, publish_event=publish_event),
            ["sandbox.read_file"],
        )
        tool = tools[0]

        raw = await tool.ainvoke(
            {
                "path": "/workspace/main/paper.txt",
                "max_chars": 0,
            }
        )

    payload = json.loads(raw)
    assert payload["payload"]["error_code"] == "tool_input_validation"
    assert payload["payload"]["exception_type"] == "ValidationError"
    assert payload["payload"]["validation"]["errors"] == [
        {
            "loc": ["max_chars"],
            "msg": "Input should be greater than or equal to 1",
            "type": "greater_than_equal",
        }
    ]
    assert "input_value" not in raw
    assert records[-1]["status"] == "failed"
    assert records[-1]["metadata"]["error_code"] == "tool_input_validation"
    assert records[-1]["metadata"]["recoverable_error"] == payload["error"]
    await asyncio.sleep(0)
    failed_events = [event for event in events if event[1] == "execution.harness.tool_call.failed"]
    assert failed_events
    assert failed_events[-1][2]["payload"]["error_code"] == "tool_input_validation"
    assert failed_events[-1][2]["payload"]["validation"]["errors"][0]["loc"] == ["max_chars"]


def test_tool_result_metadata_exposes_run_python_manifest_and_failure_classification() -> None:
    raw = json.dumps(
        {
            "preview": "Python execution failed: python_exit_nonzero: exit_code=2",
            "payload": {
                "status": "failed",
                "error_code": "python_exit_nonzero",
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "tool": "sandbox.run_python",
                    "script_name": "analysis.py",
                },
                "reproducibility_manifest": {
                    "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
                    "tool": "sandbox.run_python",
                    "sandbox": {"run_job_id": "job-1"},
                },
                "experiment_narrative": {
                    "schema": "wenjin.harness.run_python.experiment_narrative.v1",
                    "status": "failed",
                    "script_path": "/workspace/scripts/analysis.py",
                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                    "artifact_paths": [],
                    "dependency_names": ["pandas"],
                    "next_actions": ["Revise the script."],
                },
                "failure_classification": {
                    "schema": "wenjin.harness.run_python.failure_classification.v1",
                    "category": "user_code",
                    "reason": "nonzero_exit",
                    "failure_code": "python_exit_nonzero",
                    "exit_code": 2,
                    "recoverable": True,
                },
                "experiment_interpretation": {
                    "schema": "wenjin.harness.experiment_interpretation.v1",
                    "method_summary": "Compared model accuracy on a held-out benchmark split.",
                    "metric_definitions": [{"name": "accuracy"}],
                    "verified_results": [
                        {
                            "metric": "accuracy",
                            "value": 0.91,
                            "artifact_path": "/workspace/outputs/result.json",
                        }
                    ],
                    "limitations": ["Only one benchmark split was evaluated."],
                    "dataset_paths": ["/workspace/datasets/raw/survey.csv"],
                },
            },
            "truncated": False,
            "externalized": False,
            "output_refs": [],
            "error": "python_exit_nonzero: exit_code=2",
        },
        ensure_ascii=False,
    )

    metadata = _tool_result_metadata(raw)

    assert metadata["recoverable_error"] == "python_exit_nonzero: exit_code=2"
    assert metadata["error_code"] == "python_exit_nonzero"
    assert metadata["execution_manifest"]["tool"] == "sandbox.run_python"
    assert metadata["reproducibility_manifest"]["schema"] == (
        "wenjin.harness.run_python.reproducibility_manifest.v1"
    )
    assert metadata["reproducibility_manifest"]["sandbox"]["run_job_id"] == "job-1"
    assert metadata["experiment_narrative"]["schema"] == (
        "wenjin.harness.run_python.experiment_narrative.v1"
    )
    assert metadata["experiment_narrative"]["dataset_paths"] == [
        "/workspace/datasets/raw/survey.csv"
    ]
    assert metadata["failure_classification"]["failure_code"] == "python_exit_nonzero"
    assert metadata["experiment_interpretation"]["metric_definitions"] == [{"name": "accuracy"}]
    assert metadata["experiment_interpretation"]["dataset_paths"] == [
        "/workspace/datasets/raw/survey.csv"
    ]


def test_summarize_args_redacts_large_tool_text_payloads() -> None:
    script = "print('sk-secret-script')\n"
    content = "OPENAI_API_KEY=sk-secret-content\n"

    summary = summarize_tool_args(
        {
            "path": "/workspace/scripts/analysis.py",
            "script": script,
            "content": content,
        }
    )

    assert summary["path"] == "/workspace/scripts/analysis.py"
    assert summary["script"] == {
        "redacted": True,
        "chars": len(script),
        "sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
    }
    assert summary["content"] == {
        "redacted": True,
        "chars": len(content),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    dumped = json.dumps(summary, ensure_ascii=False)
    assert "sk-secret-script" not in dumped
    assert "sk-secret-content" not in dumped


def test_summarize_args_redacts_dependency_hints_before_validation() -> None:
    dependency_hints = [
        "pandas",
        "https://token.example.invalid/simple?api_key=sk-secret-dependency",
    ]

    summary = summarize_tool_args(
        {
            "script_name": "analysis.py",
            "dependency_hints": dependency_hints,
        }
    )

    encoded = json.dumps(dependency_hints, ensure_ascii=False, sort_keys=True, default=str)
    assert summary["script_name"] == "analysis.py"
    assert summary["dependency_hints"] == {
        "redacted": True,
        "kind": "list",
        "items": 2,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    dumped = json.dumps(summary, ensure_ascii=False)
    assert "pandas" not in dumped
    assert "sk-secret-dependency" not in dumped


def test_summarize_args_redacts_apply_patch_edits_before_validation() -> None:
    edits = [
        {
            "path": "/workspace/main/paper.tex",
            "old": "contains sk-secret-old",
            "new": "contains sk-secret-new",
        }
    ]

    summary = summarize_tool_args({"edits": edits})

    encoded = json.dumps(edits, ensure_ascii=False, sort_keys=True, default=str)
    assert summary["edits"] == {
        "redacted": True,
        "kind": "list",
        "items": 1,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    dumped = json.dumps(summary, ensure_ascii=False)
    assert "sk-secret-old" not in dumped
    assert "sk-secret-new" not in dumped

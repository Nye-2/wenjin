from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from src.agents.harness.args_summary import summarize_tool_args
from src.agents.harness.langchain_adapter import _tool_result_metadata, build_langchain_tools
from src.sandbox.providers.local import LocalSandbox
from src.subagents.v2.base import SubagentContext


def _ctx(sandbox: LocalSandbox, *, tool_records: list[dict] | None = None, publish_event=None) -> SubagentContext:
    workspace_data = {"_harness_sandbox": sandbox}
    if tool_records is not None:
        workspace_data["_harness_tool_records"] = tool_records
    return SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="read file",
        inputs={"user_id": "user-1", "workspace_type": "sci", "capability_id": "capability-1"},
        tools=["sandbox.read_file"],
        workspace_data=workspace_data,
        publish_event=publish_event,
        capability_policy={
            "allowed_tools": ["sandbox.read_file"],
            "sandbox_policy": {
                "output_budget": {
                    "read_max_chars": 20,
                    "externalize_above_chars": 1000,
                }
            },
        },
    )


@pytest.mark.asyncio
async def test_langchain_read_file_tool_accepts_max_chars_to_narrow_budget() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/main/paper.txt", "abcdefghijkl\n")
        [tool] = build_langchain_tools(_ctx(sandbox), ["sandbox.read_file"])

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
        [tool] = build_langchain_tools(
            _ctx(sandbox, tool_records=records, publish_event=publish_event),
            ["sandbox.read_file"],
        )

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

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
        await sandbox.write_file("/workspace/main/paper.txt", "abcdefghijkl\n")
        [tool] = build_langchain_tools(
            _ctx(sandbox, tool_records=records),
            ["sandbox.read_file"],
        )

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
                "failure_classification": {
                    "schema": "wenjin.harness.run_python.failure_classification.v1",
                    "category": "user_code",
                    "reason": "nonzero_exit",
                    "failure_code": "python_exit_nonzero",
                    "exit_code": 2,
                    "recoverable": True,
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
    assert metadata["failure_classification"]["failure_code"] == "python_exit_nonzero"


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

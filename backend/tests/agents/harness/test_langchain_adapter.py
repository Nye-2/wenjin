from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.harness.langchain_adapter import build_langchain_tools
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

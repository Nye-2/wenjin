from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.harness.langchain_adapter import build_langchain_tools
from src.sandbox.providers.local import LocalSandbox
from src.subagents.v2.base import SubagentContext


def _ctx(sandbox: LocalSandbox) -> SubagentContext:
    return SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="read file",
        inputs={"user_id": "user-1", "workspace_type": "sci", "capability_id": "capability-1"},
        tools=["sandbox.read_file"],
        workspace_data={"_harness_sandbox": sandbox},
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

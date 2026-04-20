"""Tests for SandboxAuditMiddleware."""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage

from src.agents.middlewares.sandbox_audit import SandboxAuditMiddleware


@pytest.mark.asyncio
async def test_sandbox_audit_blocks_high_risk_commands():
    middleware = SandboxAuditMiddleware()

    with pytest.raises(RuntimeError, match="Command blocked by sandbox audit"):
        await middleware.before_tool(
            state={},
            config={"configurable": {"thread_id": "thread-1", "tool_call_id": "call-1"}},
            tool_name="bash",
            tool_args={"command": "rm -rf /"},
        )


@pytest.mark.asyncio
async def test_sandbox_audit_warns_on_medium_risk_commands():
    middleware = SandboxAuditMiddleware()
    config = {"configurable": {"thread_id": "thread-1", "tool_call_id": "call-2"}}

    tool_name, tool_args = await middleware.before_tool(
        state={},
        config=config,
        tool_name="bash",
        tool_args={"command": "pip install pandas"},
    )
    assert tool_name == "bash"
    assert tool_args["command"] == "pip install pandas"

    result = ToolMessage(content="ok", tool_call_id="call-2", name="bash")
    updated = await middleware.after_tool(
        state={},
        config=config,
        tool_name="bash",
        tool_result=result,
    )
    assert isinstance(updated, ToolMessage)
    assert "[Sandbox Audit Warning]" in str(updated.content)


@pytest.mark.asyncio
async def test_sandbox_audit_no_warning_for_safe_commands():
    middleware = SandboxAuditMiddleware()
    config = {"configurable": {"thread_id": "thread-1", "tool_call_id": "call-3"}}

    await middleware.before_tool(
        state={},
        config=config,
        tool_name="bash",
        tool_args={"command": "ls -la"},
    )
    updated = await middleware.after_tool(
        state={},
        config=config,
        tool_name="bash",
        tool_result="listing output",
    )
    assert updated == "listing output"

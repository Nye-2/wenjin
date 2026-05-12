"""Test emit_delta callback on SubagentContext."""
import pytest

from src.subagents.v2.base import SubagentContext


def test_subagent_context_has_optional_emit_delta():
    """SubagentContext accepts an optional emit_delta callback."""
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="test",
        inputs={},
        tools=[],
    )
    assert ctx.emit_delta is None


@pytest.mark.asyncio
async def test_subagent_context_emit_delta_callable():
    """emit_delta can be called to emit events."""
    calls = []

    async def recorder(event_type: str, content: str) -> None:
        calls.append((event_type, content))

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="test",
        inputs={},
        tools=[],
        emit_delta=recorder,
    )
    await ctx.emit_delta("thinking", "hello ")
    await ctx.emit_delta("thinking", "world")
    assert calls == [("thinking", "hello "), ("thinking", "world")]


@pytest.mark.asyncio
async def test_subagent_context_emit_noop_when_none():
    """emit_delta does nothing when not provided."""
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="test",
        inputs={},
        tools=[],
    )
    # Should not raise
    await ctx.emit("thinking", "test")

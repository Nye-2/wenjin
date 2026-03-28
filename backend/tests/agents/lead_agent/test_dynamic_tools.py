"""Tests for DynamicToolNode tool-level middleware hooks."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from src.agents.lead_agent.dynamic_tools import DynamicToolNode
from src.agents.middlewares.base import Middleware


@tool
async def echo_tool(text: str) -> str:
    """Return the provided text unchanged."""
    return text


class _RewriteMiddleware(Middleware):
    async def before_model(self, state, config):
        return {}

    async def before_tool(self, state, config, tool_name, tool_args):
        if tool_name == "echo_tool":
            return tool_name, {"text": f"{tool_args['text']} world"}
        return tool_name, tool_args

    async def after_tool(self, state, config, tool_name, tool_result):
        if tool_name == "echo_tool":
            return f"{tool_result}!"
        return tool_result


@pytest.mark.asyncio
async def test_dynamic_tool_node_applies_tool_middlewares():
    node = DynamicToolNode(
        lambda: [echo_tool],
        middlewares=[_RewriteMiddleware()],
    )

    result = await node.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "echo_tool",
                            "args": {"text": "hello"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        config={"configurable": {}},
        store=None,
    )

    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.content == "hello world!"


def test_tool_refresh_skips_rebuild_within_ttl():
    """_refresh_tools should not rebuild if called again within TTL and tools unchanged."""
    call_count = 0

    def counting_loader():
        nonlocal call_count
        call_count += 1
        return [echo_tool]

    node = DynamicToolNode(counting_loader, refresh_interval=60.0)
    node._refresh_tools()   # first call: load
    node._refresh_tools()   # second call: should skip (within TTL, names unchanged)

    assert call_count == 1, "Loader must only be called once within TTL when tools unchanged"


def test_tool_refresh_reloads_after_ttl(monkeypatch):
    """_refresh_tools must reload after TTL expires."""
    import time

    call_count = 0

    def counting_loader():
        nonlocal call_count
        call_count += 1
        return [echo_tool]

    node = DynamicToolNode(counting_loader, refresh_interval=0.05)  # 50ms TTL
    node._refresh_tools()

    # Advance time past TTL
    monkeypatch.setattr(time, "monotonic", lambda: node._last_refresh + 1.0)
    node._refresh_tools()

    assert call_count == 2, "Loader must be called again after TTL expires"


def test_tool_refresh_forced_when_tools_change():
    """_refresh_tools must rebuild immediately when the tool set changes."""
    from langchain_core.tools import tool

    tools_v1 = [echo_tool]

    @tool
    async def extra_tool(x: int) -> int:
        """Return x."""
        return x

    tools_v2 = [echo_tool, extra_tool]
    iteration = [0]

    def versioned_loader():
        return tools_v1 if iteration[0] == 0 else tools_v2

    node = DynamicToolNode(versioned_loader, refresh_interval=60.0)
    node._refresh_tools()  # loads v1, stores names

    iteration[0] = 1
    # Force TTL bypass: mark last refresh as stale
    node._last_refresh = 0.0
    node._refresh_tools()  # detects new tool, rebuilds

    assert "extra_tool" in node.tools_by_name

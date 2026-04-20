"""Tests for DynamicToolNode tool-level middleware hooks."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from src.agents.lead_agent.dynamic_tools import DynamicToolNode
from src.agents.middlewares.base import Middleware
from src.agents.middlewares.sandbox_audit import SandboxAuditMiddleware
from src.agents.middlewares.tool_error_handling import ToolErrorHandlingMiddleware


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

    if isinstance(result, dict):
        tool_message = result["messages"][-1]
    else:
        tool_message = result[-1]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.content == "hello world!"


@pytest.mark.asyncio
async def test_dynamic_tool_node_before_tool_error_returns_tool_message():
    called = {"value": False}

    @tool
    async def tracked_tool() -> str:
        """Return a fixed payload when invoked."""
        called["value"] = True
        return "ok"

    class _BlockingMiddleware(Middleware):
        async def before_model(self, state, config):
            return {}

        async def before_tool(self, state, config, tool_name, tool_args):
            raise RuntimeError("blocked by middleware")

    node = DynamicToolNode(
        lambda: [tracked_tool],
        middlewares=[_BlockingMiddleware()],
    )

    result = await node.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "tracked_tool",
                            "args": {},
                            "id": "call-err-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        config={"configurable": {"thread_id": "thread-1", "tool_call_id": "call-err-1"}},
        store=None,
    )

    tool_message = (
        result["messages"][-1]
        if isinstance(result, dict)
        else result[-1]
    )
    assert isinstance(tool_message, ToolMessage)
    assert getattr(tool_message, "status", None) == "error"
    assert "blocked by middleware" in str(tool_message.content)
    assert called["value"] is False


@pytest.mark.asyncio
async def test_dynamic_tool_node_enforces_sandbox_audit_block():
    called = {"value": False}

    @tool("bash")
    async def fake_bash(command: str) -> str:
        """Fake bash tool for middleware integration checks."""
        called["value"] = True
        return f"ran: {command}"

    node = DynamicToolNode(
        lambda: [fake_bash],
        middlewares=[SandboxAuditMiddleware()],
    )

    result = await node.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "bash",
                            "args": {"command": "rm -rf /"},
                            "id": "call-audit-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        config={"configurable": {"thread_id": "thread-1", "tool_call_id": "call-audit-1"}},
        store=None,
    )

    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert getattr(tool_message, "status", None) == "error"
    assert "Command blocked by sandbox audit" in str(tool_message.content)
    assert called["value"] is False


@pytest.mark.asyncio
async def test_dynamic_tool_node_uses_tool_error_handling_middleware_message():
    @tool
    async def failing_tool() -> str:
        """Raise a deterministic tool failure."""
        raise ValueError("boom")

    node = DynamicToolNode(
        lambda: [failing_tool],
        middlewares=[ToolErrorHandlingMiddleware()],
    )

    result = await node.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "failing_tool",
                            "args": {},
                            "id": "call-tool-err-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        config={"configurable": {"thread_id": "thread-1", "tool_call_id": "call-tool-err-1"}},
        store=None,
    )

    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert getattr(tool_message, "status", None) == "error"
    assert "Tool 'failing_tool' failed with ValueError" in str(tool_message.content)


@pytest.mark.asyncio
async def test_dynamic_tool_node_normalizes_placeholder_tool_call_id_in_command_update():
    @tool
    async def command_tool() -> Command:
        """Return Command update with a placeholder tool_call_id."""
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="ok",
                        tool_call_id="command_tool",
                    )
                ]
            }
        )

    node = DynamicToolNode(lambda: [command_tool])

    result = await node.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "command_tool",
                            "args": {},
                            "id": "call-command-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        config={"configurable": {}},
        store=None,
    )

    last_item = result["messages"][-1] if isinstance(result, dict) else result[-1]
    if isinstance(last_item, Command):
        tool_message = last_item.update["messages"][-1]
    else:
        tool_message = last_item

    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "call-command-1"
    assert str(tool_message.content) == "ok"


def test_tool_refresh_skips_rebuild_within_ttl():
    """_refresh_tools should not rebuild if called again within TTL and tools unchanged."""
    call_count = 0

    def counting_loader():
        nonlocal call_count
        call_count += 1
        return [echo_tool]

    node = DynamicToolNode(counting_loader, refresh_interval=60.0)
    node._refresh_tools()   # constructor already loaded; this should skip (within TTL)
    node._refresh_tools()   # also skips within TTL

    assert call_count == 1, "Loader must only be called once (at construction) within TTL when tools unchanged"


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


def test_invalidate_tool_cache_forces_rebuild():
    """invalidate_tool_cache() must cause a full reload on the next invocation."""
    call_count = 0

    def counting_loader():
        nonlocal call_count
        call_count += 1
        return [echo_tool]

    node = DynamicToolNode(counting_loader, refresh_interval=60.0)
    # Constructor already called loader once; cache is warm
    node.invalidate_tool_cache()
    node._refresh_tools()  # Must reload because cache was invalidated

    assert call_count == 2, "Loader must be called again after cache invalidation"


def test_run_coroutine_sync_warns_when_loop_is_running(caplog):
    """_run_coroutine_sync must emit a WARNING when called inside a running event loop."""
    import asyncio
    import logging

    async def _check_warning():
        async def noop():
            return 42

        with caplog.at_level(logging.WARNING, logger="src.agents.lead_agent.dynamic_tools"):
            # We're inside an event loop here; this should trigger the warning
            result = DynamicToolNode._run_coroutine_sync(noop())
        return result

    result = asyncio.run(_check_warning())
    assert result == 42
    assert any("sync" in record.message.lower() or "thread" in record.message.lower()
               for record in caplog.records), (
        "Expected a WARNING log when _run_coroutine_sync spawns a thread inside a running loop"
    )


def test_run_coroutine_sync_raises_on_thread_timeout(monkeypatch):
    """_run_coroutine_sync must raise TimeoutError if thread does not finish within 30s."""
    import threading

    import src.agents.lead_agent.dynamic_tools as dt_module

    def patched_join(self, timeout=None):
        # Simulate a join that returns immediately (as if timeout expired)
        # but the thread never completes, so is_alive() returns True
        pass

    # Make is_alive always return True to simulate a timed-out thread
    monkeypatch.setattr(threading.Thread, "join", patched_join)
    monkeypatch.setattr(threading.Thread, "is_alive", lambda self: True)

    # Simulate being inside a running event loop so the thread path is taken
    monkeypatch.setattr(dt_module.asyncio, "get_running_loop", lambda: object())

    async def noop():
        return 42

    coro = noop()
    try:
        with pytest.raises(TimeoutError, match="30 s"):
            DynamicToolNode._run_coroutine_sync(coro)
    finally:
        coro.close()

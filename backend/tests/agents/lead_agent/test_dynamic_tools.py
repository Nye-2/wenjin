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

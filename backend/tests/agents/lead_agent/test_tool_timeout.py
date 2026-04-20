"""Tests for per-tool timeout and output truncation."""

import asyncio

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from src.agents.lead_agent.dynamic_tools import DynamicToolNode
from src.config.llm_config import LLMSettings


@tool
async def slow_tool(text: str) -> str:
    """A tool that sleeps forever."""
    await asyncio.sleep(10)
    return "done"


@tool
async def big_tool(text: str) -> str:
    """A tool that returns a huge response."""
    return "x" * 500


@tool
async def normal_tool(text: str) -> str:
    """A tool that returns a short response."""
    return "short result"


class TestToolTimeout:
    @pytest.mark.asyncio
    async def test_tool_timeout_returns_error_message(self):
        """A hanging tool should return an error ToolMessage, not hang."""
        original = LLMSettings.TOOL_TIMEOUT
        LLMSettings.TOOL_TIMEOUT = 0.1  # 100ms

        try:
            node = DynamicToolNode(lambda: [slow_tool])
            call = {"name": "slow_tool", "args": {"text": "hi"}, "id": "call-1", "type": "tool_call"}

            result = await node._arun_one_with_middlewares(
                call=call,
                input_type="list",
                config={"configurable": {}},
                state={"messages": []},
            )

            assert isinstance(result, ToolMessage)
            content = result.content if isinstance(result.content, str) else str(result.content)
            assert "timeout" in content.lower() or "timed out" in content.lower()
        finally:
            LLMSettings.TOOL_TIMEOUT = original


class TestToolOutputTruncation:
    @pytest.mark.asyncio
    async def test_oversized_output_is_truncated(self):
        """Tool output exceeding TOOL_OUTPUT_MAX_CHARS should be truncated."""
        original = LLMSettings.TOOL_OUTPUT_MAX_CHARS
        LLMSettings.TOOL_OUTPUT_MAX_CHARS = 100

        try:
            node = DynamicToolNode(lambda: [big_tool])
            call = {"name": "big_tool", "args": {"text": "hi"}, "id": "call-1", "type": "tool_call"}

            result = await node._arun_one_with_middlewares(
                call=call,
                input_type="list",
                config={"configurable": {}},
                state={"messages": []},
            )

            assert isinstance(result, ToolMessage)
            content = result.content if isinstance(result.content, str) else str(result.content)
            # Should be truncated: 100 chars + truncation notice
            assert len(content) < 500
            assert "truncated" in content.lower()
        finally:
            LLMSettings.TOOL_OUTPUT_MAX_CHARS = original

    @pytest.mark.asyncio
    async def test_normal_output_is_not_truncated(self):
        """Tool output within limit should not be modified."""
        original = LLMSettings.TOOL_OUTPUT_MAX_CHARS
        LLMSettings.TOOL_OUTPUT_MAX_CHARS = 10000

        try:
            node = DynamicToolNode(lambda: [normal_tool])
            call = {"name": "normal_tool", "args": {"text": "hi"}, "id": "call-1", "type": "tool_call"}

            result = await node._arun_one_with_middlewares(
                call=call,
                input_type="list",
                config={"configurable": {}},
                state={"messages": []},
            )

            assert isinstance(result, ToolMessage)
            content = result.content if isinstance(result.content, str) else str(result.content)
            assert "truncated" not in content.lower()
        finally:
            LLMSettings.TOOL_OUTPUT_MAX_CHARS = original

"""Tests for ToolErrorHandlingMiddleware."""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage

from src.agents.middlewares.tool_error_handling import ToolErrorHandlingMiddleware


@pytest.mark.asyncio
async def test_tool_error_handling_builds_error_tool_message():
    middleware = ToolErrorHandlingMiddleware()
    result = await middleware.on_tool_error(
        state={},
        config={"configurable": {"tool_call_id": "call-1"}},
        tool_name="bash",
        tool_args={"command": "cat missing.txt"},
        error=FileNotFoundError("missing file"),
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.name == "bash"
    assert result.tool_call_id == "call-1"
    assert "FileNotFoundError" in str(result.content)
    assert "missing file" in str(result.content)


@pytest.mark.asyncio
async def test_tool_error_handling_truncates_error_detail():
    middleware = ToolErrorHandlingMiddleware(max_detail_chars=120)
    long_message = "x" * 1000
    result = await middleware.on_tool_error(
        state={},
        config={"configurable": {"tool_call_id": "call-2"}},
        tool_name="read_file",
        tool_args={"file_path": "a.txt"},
        error=RuntimeError(long_message),
    )

    assert isinstance(result, ToolMessage)
    assert len(str(result.content)) < 500
    assert "..." in str(result.content)

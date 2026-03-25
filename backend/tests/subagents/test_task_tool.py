"""Tests for the task delegation tool with real executor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.executor import SubagentStatus
from src.subagents.task_tool import task_tool


class TestTaskTool:
    @pytest.mark.asyncio
    async def test_unknown_type_returns_error(self):
        result = await task_tool.ainvoke({
            "description": "Test",
            "prompt": "Do something",
            "subagent_type": "nonexistent_type",
        })
        assert "Error" in result or "Unknown" in result

    @pytest.mark.asyncio
    async def test_known_type_delegates(self):
        """Known subagent type should attempt delegation."""
        with patch("src.subagents.task_tool.SubagentExecutor") as MockExec:
            mock_result = MagicMock()
            mock_result.status = SubagentStatus.COMPLETED
            mock_result.result = "Task done"
            mock_result.error = None
            MockExec.return_value.aexecute = AsyncMock(return_value=mock_result)

            result = await task_tool.ainvoke({
                "description": "Search papers",
                "prompt": "Find LLM alignment papers",
                "subagent_type": "scout",
            })
            assert "completed" in result.lower() or "done" in result.lower()

    @pytest.mark.asyncio
    async def test_known_type_forwards_thread_context(self):
        """Delegated subagents should inherit the parent thread runtime context."""
        with patch("src.subagents.task_tool.SubagentExecutor") as MockExec:
            mock_result = MagicMock()
            mock_result.status = SubagentStatus.COMPLETED
            mock_result.result = "Task done"
            mock_result.error = None
            MockExec.return_value.aexecute = AsyncMock(return_value=mock_result)

            result = await task_tool.coroutine(
                description="Search papers",
                prompt="Find LLM alignment papers",
                subagent_type="scout",
                config={"configurable": {"thread_id": "thread-1", "model_name": "gpt-4o"}},
            )

            assert "completed" in result.lower() or "done" in result.lower()
            _, kwargs = MockExec.call_args
            assert kwargs["thread_id"] == "thread-1"
            assert kwargs["parent_model"] == "gpt-4o"

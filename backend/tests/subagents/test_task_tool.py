"""Tests for the task delegation tool with real executor."""

from unittest.mock import MagicMock, patch

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
            MockExec.return_value.execute.return_value = mock_result

            result = await task_tool.ainvoke({
                "description": "Search papers",
                "prompt": "Find LLM alignment papers",
                "subagent_type": "scout",
            })
            assert "completed" in result.lower() or "done" in result.lower()

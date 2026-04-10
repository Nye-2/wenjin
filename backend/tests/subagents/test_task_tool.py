"""Tests for the task delegation tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.models import SubagentResult, SubagentStatus
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
        mock_manager = MagicMock()
        mock_manager._config.default_timeout = 900
        mock_manager._config.max_turns_limit = 50
        mock_manager.spawn = AsyncMock(return_value="task-123")
        mock_manager.wait_for_completion = AsyncMock(
            return_value=SubagentResult(
                task_id="task-123",
                status=SubagentStatus.COMPLETED,
                output="Task done",
                error=None,
            )
        )

        with patch("src.subagents.task_tool.get_manager", return_value=mock_manager):
            result = await task_tool.ainvoke({
                "description": "Search papers",
                "prompt": "Find LLM alignment papers",
                "subagent_type": "scout",
            })
        assert "completed" in result.lower() or "done" in result.lower()
        mock_manager.spawn.assert_awaited_once()
        mock_manager.wait_for_completion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_known_type_forwards_thread_context(self):
        """Delegated subagents should inherit the parent thread runtime context."""
        mock_manager = MagicMock()
        mock_manager._config.default_timeout = 900
        mock_manager._config.max_turns_limit = 50
        mock_manager.spawn = AsyncMock(return_value="task-123")
        mock_manager.wait_for_completion = AsyncMock(
            return_value=SubagentResult(
                task_id="task-123",
                status=SubagentStatus.COMPLETED,
                output="Task done",
                error=None,
            )
        )

        with patch("src.subagents.task_tool.get_manager", return_value=mock_manager), patch(
            "src.subagents.task_tool.build_subagent_context_snapshot",
            AsyncMock(return_value="## Inherited Workspace Context\n- workspace_type: sci"),
        ):
            result = await task_tool.coroutine(
                description="Search papers",
                prompt="Find LLM alignment papers",
                subagent_type="scout",
                config={
                    "configurable": {
                        "thread_id": "thread-1",
                        "workspace_id": "ws-1",
                        "user_id": "user-1",
                        "model_name": "gpt-4o",
                    }
                },
                state={
                    "workspace_type": "sci",
                    "current_skill": "framework-designer",
                },
            )

        assert "completed" in result.lower() or "done" in result.lower()
        task = mock_manager.spawn.await_args.args[0]
        assert task.thread_id == "thread-1"
        assert task.max_turns == 10
        assert task.timeout == 900
        assert task.tools == ["semantic_scholar_search"]
        assert task.metadata["subagent_type"] == "scout"
        assert task.metadata["system_prompt"]
        assert task.metadata["workspace_id"] == "ws-1"
        assert task.metadata["user_id"] == "user-1"
        assert task.metadata["model_name"] == "gpt-4o"
        assert "## Inherited Workspace Context" in task.metadata["system_prompt"]
        assert mock_manager.wait_for_completion.await_args.args == ("thread-1", task.task_id)
        assert mock_manager.wait_for_completion.await_args.kwargs == {"user_id": "user-1"}

    @pytest.mark.asyncio
    async def test_known_type_without_parent_thread_uses_isolated_context(self):
        """Detached task-tool runs should not require thread ownership state."""
        mock_manager = MagicMock()
        mock_manager._config.default_timeout = 900
        mock_manager._config.max_turns_limit = 50
        mock_manager.spawn = AsyncMock(return_value="task-123")
        mock_manager.wait_for_completion = AsyncMock(
            return_value=SubagentResult(
                task_id="task-123",
                status=SubagentStatus.TIMED_OUT,
                output=None,
                error="Exceeded time limit",
            )
        )

        with patch("src.subagents.task_tool.get_manager", return_value=mock_manager):
            result = await task_tool.coroutine(
                description="Search papers",
                prompt="Find LLM alignment papers",
                subagent_type="scout",
                config={"configurable": {"model_name": "gpt-4o"}},
            )

        assert "timed out" in result.lower()
        task = mock_manager.spawn.await_args.args[0]
        assert task.thread_id.startswith("subagent-tool-")
        assert "user_id" not in task.metadata
        assert "workspace_id" not in task.metadata
        assert task.metadata["model_name"] == "gpt-4o"

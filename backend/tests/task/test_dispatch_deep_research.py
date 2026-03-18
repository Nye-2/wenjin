"""Regression tests for deep_research dispatch routing."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_dispatch_thesis_deep_research_uses_langgraph_workspace_and_feature():
    """Thesis deep_research should dispatch with ('thesis', 'deep_research')."""
    from src.task.tasks.base import _dispatch_task

    progress = AsyncMock()
    payload = {
        "workspace_type": "thesis",
        "workspace_id": "ws-1",
        "feature_id": "deep_research",
    }

    with (
        patch("src.task.registry.is_valid_task_type", return_value=True),
        patch(
            "src.task.handlers.workspace_feature_handler._try_langgraph_execution",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_try,
        patch(
            "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
        ) as mock_schedule,
    ):
        result = await _dispatch_task("deep_research", payload, progress)

    mock_try.assert_awaited_once_with("thesis", "deep_research", payload, progress)
    mock_schedule.assert_called_once_with("thesis", payload, {"success": True})
    assert result == {"success": True}

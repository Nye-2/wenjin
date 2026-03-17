"""Tests for thesis deep_research routing to LangGraph with skill fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_dispatch_deep_research_thesis_prefers_langgraph():
    """Thesis deep_research should try LangGraph before skill execution."""
    from src.task.tasks.base import _dispatch_task

    progress = AsyncMock()
    payload = {
        "workspace_type": "thesis",
        "feature_id": "deep_research",
        "workspace_id": "ws-1",
    }
    langgraph_result = {
        "feature_id": "deep_research",
        "generation_mode": "llm",
    }

    with (
        patch("src.task.registry.is_valid_task_type", return_value=True),
        patch(
            "src.task.handlers.workspace_feature_handler._try_langgraph_execution",
            new_callable=AsyncMock,
            return_value=langgraph_result,
        ) as mock_try_langgraph,
        patch("src.task.tasks.base.get_skill_task_handler") as mock_get_handler,
    ):
        result = await _dispatch_task("deep_research", payload, progress)

    assert result == langgraph_result
    mock_try_langgraph.assert_awaited_once_with("deep_research", payload, progress)
    mock_get_handler.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_deep_research_thesis_falls_back_to_skill():
    """If LangGraph is unavailable, thesis deep_research should fall back to skill."""
    from src.task.tasks.base import _dispatch_task

    progress = AsyncMock()
    payload = {
        "workspace_type": "thesis",
        "feature_id": "deep_research",
        "workspace_id": "ws-1",
    }

    skill_handler = MagicMock()
    skill_handler.get_skill_name.return_value = "deep-research"
    skill_handler.execute_skill = AsyncMock(return_value={"success": True, "content": "ok"})

    with (
        patch("src.task.registry.is_valid_task_type", return_value=True),
        patch(
            "src.task.handlers.workspace_feature_handler._try_langgraph_execution",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_try_langgraph,
        patch("src.task.tasks.base.get_skill_task_handler", return_value=skill_handler),
    ):
        result = await _dispatch_task("deep_research", payload, progress)

    assert result["success"] is True
    mock_try_langgraph.assert_awaited_once_with("deep_research", payload, progress)
    skill_handler.execute_skill.assert_awaited_once_with("deep_research", payload, progress)

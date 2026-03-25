"""Regression tests for workspace feature dispatch routing."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_dispatch_workspace_feature_routes_to_workspace_feature_handler():
    """Canonical workspace_feature tasks should dispatch via the shared handler."""
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
            "src.task.handlers.workspace_feature_handler.execute_workspace_feature",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_execute,
    ):
        result = await _dispatch_task("workspace_feature", payload, progress)

    mock_execute.assert_awaited_once_with(payload, progress)
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_dispatch_paper_extraction_routes_to_paper_extraction_handler():
    """paper_extraction should dispatch via its dedicated internal handler."""
    from src.task.tasks.base import _dispatch_task

    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "paper_id": "paper-1",
        "tier": 2,
    }

    with (
        patch("src.task.registry.is_valid_task_type", return_value=True),
        patch(
            "src.task.handlers.paper_extraction_handler.execute_paper_extraction",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_execute,
    ):
        result = await _dispatch_task("paper_extraction", payload, progress)

    mock_execute.assert_awaited_once_with(payload, progress)
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_dispatch_unknown_raw_task_type_fails_fast():
    """Unknown raw task types must fail before entering the canonical chain."""
    from src.task.tasks.base import _dispatch_task

    progress = AsyncMock()
    payload = {"workspace_id": "ws-1"}

    with pytest.raises(ValueError, match="Unknown task type: paper_processing"):
        await _dispatch_task("paper_processing", payload, progress)

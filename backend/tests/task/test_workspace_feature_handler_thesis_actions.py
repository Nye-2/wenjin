"""Tests for thesis-writing action normalization in workspace feature handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import execute_workspace_feature


@pytest.mark.asyncio
async def test_execute_workspace_feature_thesis_writing_defaults_missing_action():
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "thesis_writing",
        "params": {},
    }

    with patch(
        "src.task.handlers.workspace_feature_handler._try_langgraph_execution",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_try, patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ):
        result = await execute_workspace_feature(payload, progress)

    assert result == {"success": True}
    called_payload = mock_try.await_args.args[2]
    assert called_payload["params"]["action"] == "write_all"


@pytest.mark.asyncio
async def test_execute_workspace_feature_thesis_writing_rejects_unknown_action():
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "thesis_writing",
        "params": {"action": "not_supported"},
    }

    with pytest.raises(ValueError, match="Unsupported thesis_writing action"):
        await execute_workspace_feature(payload, progress)


@pytest.mark.asyncio
async def test_execute_workspace_feature_thesis_writing_normalizes_action_case():
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "feature_id": "thesis_writing",
        "params": {"action": "WRITE_CHAPTER"},
    }

    with patch(
        "src.task.handlers.workspace_feature_handler._try_langgraph_execution",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_try, patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ):
        result = await execute_workspace_feature(payload, progress)

    assert result == {"success": True}
    called_payload = mock_try.await_args.args[2]
    assert called_payload["params"]["action"] == "write_chapter"

"""Tests for Prometheus task metrics in executor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTaskMetricsInLocalExecutor:
    """Verify track_task_start / track_task_end are called in _run_task_locally."""

    @pytest.mark.asyncio
    async def test_track_task_called_on_success(self):
        """track_task_start and track_task_end are called on successful task."""
        mock_redis = MagicMock()
        mock_redis._client = MagicMock()
        mock_redis.set_agent_status = AsyncMock()
        mock_redis.client = MagicMock()

        mock_store = AsyncMock()
        mock_store.mark_task_started = AsyncMock()
        mock_store.mark_task_completed = AsyncMock()

        mock_progress = AsyncMock()

        with (
            patch("src.academic.cache.redis_client.redis_client", mock_redis),
            patch("src.database.get_db_session") as mock_db_ctx,
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch(
                "src.task.tasks.base._dispatch_task",
                new_callable=AsyncMock,
                return_value={"status": "ok"},
            ),
            patch("src.task.executor.track_task_start") as mock_start,
            patch("src.task.executor.track_task_end") as mock_end,
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            from src.task.executor import _run_task_locally

            await _run_task_locally("task-1", "test_type", {"workspace_id": "ws-1"})

        mock_start.assert_called_once()
        mock_end.assert_called_once()
        call_args = mock_end.call_args
        assert call_args[0][0] == "test_type"  # task_type
        assert isinstance(call_args[0][1], float)  # duration

    @pytest.mark.asyncio
    async def test_track_task_called_on_failure(self):
        """track_task_end is called even when task fails."""
        mock_redis = MagicMock()
        mock_redis._client = MagicMock()
        mock_redis.set_agent_status = AsyncMock()
        mock_redis.client = MagicMock()

        mock_store = AsyncMock()
        mock_store.mark_task_started = AsyncMock()
        mock_store.mark_task_completed = AsyncMock()
        mock_store.get_task_record = AsyncMock(return_value=None)

        mock_progress = AsyncMock()

        with (
            patch("src.academic.cache.redis_client.redis_client", mock_redis),
            patch("src.database.get_db_session") as mock_db_ctx,
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch(
                "src.task.tasks.base._dispatch_task",
                new_callable=AsyncMock,
                side_effect=ValueError("boom"),
            ),
            patch("src.task.executor.track_task_start") as mock_start,
            patch("src.task.executor.track_task_end") as mock_end,
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            from src.task.executor import _run_task_locally

            await _run_task_locally("task-1", "test_type", {"workspace_id": "ws-1"})

        mock_start.assert_called_once()
        mock_end.assert_called_once()
        call_args = mock_end.call_args
        assert call_args[0][0] == "test_type"
        assert isinstance(call_args[0][1], float)

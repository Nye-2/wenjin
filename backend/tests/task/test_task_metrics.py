"""Tests for Prometheus task metrics in executor."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTaskMetricsInSharedRunner:
    """Verify the shared task runner records metrics consistently."""

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
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch(
                "src.task.tasks.base._dispatch_task",
                new_callable=AsyncMock,
                return_value={"status": "ok"},
            ),
            patch("src.observability.prometheus.track_task_start") as mock_start,
            patch("src.observability.prometheus.track_task_end") as mock_end,
        ):
            from src.task.tasks.base import _execute_task_async

            fake_task = SimpleNamespace(
                request=SimpleNamespace(hostname="test-worker"),
            )
            await _execute_task_async(
                fake_task,
                "task-1",
                "test_type",
                {"workspace_id": "ws-1"},
            )

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
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch(
                "src.task.tasks.base._dispatch_task",
                new_callable=AsyncMock,
                side_effect=ValueError("boom"),
            ),
            patch("src.observability.prometheus.track_task_start") as mock_start,
            patch("src.observability.prometheus.track_task_end") as mock_end,
        ):
            from src.task.tasks.base import _execute_task_async

            fake_task = SimpleNamespace(
                request=SimpleNamespace(hostname="test-worker"),
            )
            with pytest.raises(ValueError, match="boom"):
                await _execute_task_async(
                    fake_task,
                    "task-1",
                    "test_type",
                    {"workspace_id": "ws-1"},
                )

        mock_start.assert_called_once()
        mock_end.assert_called_once()
        call_args = mock_end.call_args
        assert call_args[0][0] == "test_type"
        assert isinstance(call_args[0][1], float)

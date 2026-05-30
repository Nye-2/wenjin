"""Tests for agent status tracking in task execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAgentStatusInSharedRunner:
    @pytest.mark.asyncio
    async def test_sets_running_status_on_start(self):
        """Agent status is set to running when task starts with thread_id."""
        mock_redis = MagicMock()
        mock_redis._client = MagicMock()
        mock_redis.set_agent_status = AsyncMock()
        mock_redis.client = MagicMock()
        mock_redis.client.publish = AsyncMock()

        mock_store = AsyncMock()
        mock_store.mark_task_started = AsyncMock()
        mock_store.mark_task_completed = AsyncMock()
        mock_store.get_task_record = AsyncMock(return_value=None)

        mock_progress = AsyncMock()

        payload = {"thread_id": "thread-abc", "workspace_id": "ws-1"}

        with (
            patch("src.academic.cache.redis_client.redis_client", mock_redis),
            patch("src.config.redis_settings.enabled", True),
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch("src.task.tasks.base._dispatch_task", new_callable=AsyncMock, return_value={"status": "ok"}),
            patch("src.task.tasks.base._append_task_thread_message", new_callable=AsyncMock),
        ):
            from src.task.tasks.base import _execute_task_async

            fake_task = SimpleNamespace(
                request=SimpleNamespace(hostname="test-worker"),
            )
            await _execute_task_async(fake_task, "task-1", "test_type", payload)

        # Check set_agent_status was called with "running" and then "completed"
        calls = mock_redis.set_agent_status.call_args_list
        assert len(calls) >= 2
        assert calls[0].args == ("thread-abc", "running")
        assert calls[0].kwargs.get("skill") == "test_type"
        assert calls[0].kwargs.get("clear_skill") is False
        assert calls[1].args == ("thread-abc", "completed")
        assert calls[1].kwargs.get("clear_skill") is False

    @pytest.mark.asyncio
    async def test_no_status_set_without_thread_id(self):
        """Agent status is NOT set when payload has no thread_id."""
        mock_redis = MagicMock()
        mock_redis._client = MagicMock()
        mock_redis.set_agent_status = AsyncMock()
        mock_redis.client = MagicMock()
        mock_redis.client.publish = AsyncMock()

        mock_store = AsyncMock()
        mock_store.mark_task_started = AsyncMock()
        mock_store.mark_task_completed = AsyncMock()

        mock_progress = AsyncMock()

        payload = {"workspace_id": "ws-1"}  # no thread_id

        with (
            patch("src.academic.cache.redis_client.redis_client", mock_redis),
            patch("src.config.redis_settings.enabled", True),
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch("src.task.tasks.base._dispatch_task", new_callable=AsyncMock, return_value={"status": "ok"}),
            patch("src.task.tasks.base._append_task_thread_message", new_callable=AsyncMock),
        ):
            from src.task.tasks.base import _execute_task_async

            fake_task = SimpleNamespace(
                request=SimpleNamespace(hostname="test-worker"),
            )
            await _execute_task_async(fake_task, "task-1", "test_type", payload)

        mock_redis.set_agent_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_sets_failed_status_on_error(self):
        """Agent status is set to failed when task raises."""
        mock_redis = MagicMock()
        mock_redis._client = MagicMock()
        mock_redis.set_agent_status = AsyncMock()
        mock_redis.client = MagicMock()
        mock_redis.client.publish = AsyncMock()

        mock_store = AsyncMock()
        mock_store.mark_task_started = AsyncMock()
        mock_store.mark_task_completed = AsyncMock()
        mock_store.get_task_record = AsyncMock(return_value=None)

        mock_progress = AsyncMock()

        payload = {"thread_id": "thread-xyz", "workspace_id": "ws-1"}

        with (
            patch("src.academic.cache.redis_client.redis_client", mock_redis),
            patch("src.config.redis_settings.enabled", True),
            patch("src.task.progress.ProgressTracker", return_value=mock_progress),
            patch("src.task.store.TaskStore", return_value=mock_store),
            patch("src.task.tasks.base._dispatch_task", new_callable=AsyncMock, side_effect=ValueError("boom")),
            patch("src.task.tasks.base._append_task_thread_message", new_callable=AsyncMock),
        ):
            from src.task.tasks.base import _execute_task_async

            fake_task = SimpleNamespace(
                request=SimpleNamespace(hostname="test-worker"),
            )
            with pytest.raises(ValueError, match="boom"):
                await _execute_task_async(fake_task, "task-1", "test_type", payload)

        calls = mock_redis.set_agent_status.call_args_list
        assert len(calls) >= 2
        assert calls[0].args == ("thread-xyz", "running")
        assert calls[0].kwargs.get("clear_skill") is False
        assert calls[1].args == ("thread-xyz", "failed")
        assert calls[1].kwargs.get("clear_skill") is False

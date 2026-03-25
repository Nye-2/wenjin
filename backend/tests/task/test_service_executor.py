"""Tests for TaskService executor integration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.task.service import TaskService


@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.create_task_record_guarded = AsyncMock(
        return_value=(
            MagicMock(
                created_at=datetime.now(UTC),
                started_at=None,
                task_type="workspace_feature",
            ),
            0,
        )
    )
    return store


class TestSubmitTaskUsesExecutor:
    """TaskService.submit_task should delegate to get_executor()."""

    @pytest.mark.asyncio
    async def test_submit_calls_executor_not_celery_directly(self, mock_store):
        """submit_task should use executor abstraction, not celery_app.send_task."""
        service = TaskService(mock_store)

        mock_executor = AsyncMock()
        with (
            patch("src.task.service.get_executor", return_value=mock_executor),
            patch("src.task.service.is_valid_task_type", return_value=True),
            patch("src.task.service.get_task_config", return_value=MagicMock(queue="default")),
        ):
            await service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-1"},
                priority=5,
            )

        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args
        assert call_kwargs.kwargs.get("task_id") or call_kwargs[0][0]  # task_id passed

    @pytest.mark.asyncio
    async def test_submit_publishes_canonical_task_activity(self, mock_store):
        """submit_task should publish an activity payload usable by the workspace timeline."""
        service = TaskService(mock_store)

        mock_executor = AsyncMock()
        with (
            patch("src.task.service.get_executor", return_value=mock_executor),
            patch("src.task.service.is_valid_task_type", return_value=True),
            patch("src.task.service.get_task_config", return_value=MagicMock(queue="default")),
            patch("src.task.service.publish_workspace_event", new=AsyncMock()) as publish_workspace_event,
        ):
            await service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={
                    "workspace_id": "ws-1",
                    "feature_id": "deep_research",
                    "params": {"topic": "LLM agents"},
                },
                priority=5,
            )

        first_payload = publish_workspace_event.await_args_list[0].args[2]
        assert first_payload["activity"]["id"].startswith("task:")
        assert first_payload["activity"]["kind"] == "feature_task"
        assert first_payload["activity"]["feature_id"] == "deep_research"
        assert first_payload["activity"]["summary"] == "LLM agents"

    @pytest.mark.asyncio
    async def test_submit_marks_failed_on_executor_error(self, mock_store):
        """If executor.execute raises, task should be marked FAILED."""
        service = TaskService(mock_store)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = ConnectionError("broker down")

        with (
            patch("src.task.service.get_executor", return_value=mock_executor),
            patch("src.task.service.is_valid_task_type", return_value=True),
            patch("src.task.service.get_task_config", return_value=MagicMock(queue="default")),
        ):
            with pytest.raises(ConnectionError):
                await service.submit_task(
                    user_id="user-1",
                    task_type="workspace_feature",
                    payload={},
                )

        mock_store.update_task_record.assert_called_once()


class TestCancelTaskInLocalMode:
    """TaskService.cancel_task should cancel local asyncio tasks when Celery is disabled."""

    @pytest.mark.asyncio
    async def test_cancel_uses_local_cancel_helper_when_celery_disabled(self, mock_store):
        service = TaskService(mock_store)

        record = MagicMock()
        record.user_id = "user-1"
        record.status = "running"
        record.task_type = "workspace_feature"
        record.payload = {
            "workspace_id": "ws-1",
            "feature_id": "deep_research",
            "params": {"topic": "LLM agents"},
        }
        record.created_at = datetime.now(UTC)
        record.started_at = datetime.now(UTC)
        mock_store.get_task_record = AsyncMock(return_value=record)
        mock_store.update_task_record = AsyncMock()
        mock_store.set_task_state = AsyncMock()

        with (
            patch("src.task.service.celery_settings") as mock_celery_settings,
            patch("src.task.service.cancel_local_task", return_value=True) as mock_cancel_local,
            patch("src.task.service.celery_app.control.revoke") as mock_revoke,
            patch("src.task.service.publish_workspace_event", new=AsyncMock()) as publish_workspace_event,
        ):
            mock_celery_settings.enabled = False
            cancelled = await service.cancel_task("task-1", "user-1")

        assert cancelled is True
        mock_cancel_local.assert_called_once_with("task-1")
        mock_revoke.assert_not_called()
        first_payload = publish_workspace_event.await_args_list[0].args[2]
        assert first_payload["activity"]["id"] == "task:task-1"
        assert first_payload["activity"]["status"] == "cancelled"

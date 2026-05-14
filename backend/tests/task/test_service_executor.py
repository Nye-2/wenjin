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
                task_type="execution",
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
                task_type="execution",
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
                task_type="execution",
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
                    task_type="execution",
                    payload={},
                )

        mock_store.update_task_record.assert_called_once()


class TestCancelTaskInCeleryMode:
    """TaskService.cancel_task should revoke backend task and persist cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_revokes_celery_task(self, mock_store):
        service = TaskService(mock_store)

        record = MagicMock()
        record.user_id = "user-1"
        record.status = "running"
        record.task_type = "execution"
        record.id = "task-1"
        record.progress = 42
        record.execution_id = "exec-1"
        record.payload = {
            "workspace_id": "ws-1",
            "feature_id": "deep_research",
            "params": {"topic": "LLM agents"},
        }
        record.created_at = datetime.now(UTC)
        record.started_at = datetime.now(UTC)
        mock_store.get_task_record = AsyncMock(return_value=record)
        mock_store.get_task_state = AsyncMock(
            return_value={
                "status": "running",
                "progress": 73,
                "message": "Halfway done",
                "metadata": {"runtime": {"current_phase": "drafting"}},
            }
        )
        mock_store.update_task_record = AsyncMock()
        mock_store.set_task_state = AsyncMock()

        with (
            patch("src.task.service.celery_settings") as mock_celery_settings,
            patch("src.task.service.celery_app.control.revoke") as mock_revoke,
            patch("src.task.service.publish_workspace_event", new=AsyncMock()) as publish_workspace_event,
            patch(
                "src.task.service.ExecutionService.apply_task_transition",
                new=AsyncMock(),
            ) as update_execution,
        ):
            mock_celery_settings.enabled = True
            cancelled = await service.cancel_task("task-1", "user-1")

        assert cancelled is True
        mock_revoke.assert_called_once_with("task-1", terminate=True)
        mock_store.set_task_state.assert_awaited_once_with(
            "task-1",
            "cancelled",
            progress=73,
            message="Cancelled by user",
            metadata={"runtime": {"current_phase": "drafting"}},
        )
        first_payload = publish_workspace_event.await_args_list[0].args[2]
        assert first_payload["activity"]["id"] == "task:task-1"
        assert first_payload["activity"]["status"] == "cancelled"
        assert first_payload["task"]["progress"] == 73
        assert first_payload["task"]["metadata"] == {"runtime": {"current_phase": "drafting"}}
        assert first_payload["activity"]["metadata"]["progress"] == 73
        update_execution.assert_awaited_once()
        assert update_execution.await_args.args[0] == "exec-1"
        assert update_execution.await_args.kwargs["status"] == "cancelled"
        assert update_execution.await_args.kwargs["runtime_state"] == {
            "current_phase": "drafting"
        }

    @pytest.mark.asyncio
    async def test_cancel_falls_back_to_record_progress_when_runtime_state_missing(self, mock_store):
        service = TaskService(mock_store)

        record = MagicMock()
        record.user_id = "user-1"
        record.status = "running"
        record.task_type = "execution"
        record.id = "task-2"
        record.progress = 58
        record.execution_id = "exec-2"
        record.payload = {
            "workspace_id": "ws-1",
            "feature_id": "deep_research",
            "params": {"topic": "LLM agents"},
        }
        record.created_at = datetime.now(UTC)
        record.started_at = datetime.now(UTC)
        mock_store.get_task_record = AsyncMock(return_value=record)
        mock_store.get_task_state = AsyncMock(return_value=None)
        mock_store.update_task_record = AsyncMock()
        mock_store.set_task_state = AsyncMock()

        with (
            patch("src.task.service.celery_settings") as mock_celery_settings,
            patch("src.task.service.celery_app.control.revoke") as mock_revoke,
            patch("src.task.service.publish_workspace_event", new=AsyncMock()) as publish_workspace_event,
            patch(
                "src.task.service.ExecutionService.apply_task_transition",
                new=AsyncMock(),
            ) as update_execution,
        ):
            mock_celery_settings.enabled = True
            cancelled = await service.cancel_task("task-2", "user-1")

        assert cancelled is True
        mock_revoke.assert_called_once_with("task-2", terminate=True)
        mock_store.set_task_state.assert_awaited_once_with(
            "task-2",
            "cancelled",
            progress=58,
            message="Cancelled by user",
            metadata=None,
        )
        first_payload = publish_workspace_event.await_args_list[0].args[2]
        assert first_payload["task"]["progress"] == 58
        assert first_payload["task"]["metadata"] is None
        assert first_payload["activity"]["metadata"]["progress"] == 58
        assert update_execution.await_args.kwargs["runtime_state"] is None

    @pytest.mark.asyncio
    async def test_cancel_raises_when_celery_disabled(self, mock_store):
        service = TaskService(mock_store)

        record = MagicMock()
        record.user_id = "user-1"
        record.status = "running"
        record.task_type = "execution"
        record.id = "task-3"
        record.progress = 0
        record.execution_id = None
        record.payload = {"workspace_id": "ws-1"}
        record.created_at = datetime.now(UTC)
        record.started_at = datetime.now(UTC)
        mock_store.get_task_record = AsyncMock(return_value=record)

        with patch("src.task.service.celery_settings") as mock_celery_settings:
            mock_celery_settings.enabled = False
            with pytest.raises(RuntimeError, match="CELERY_ENABLED=true"):
                await service.cancel_task("task-3", "user-1")

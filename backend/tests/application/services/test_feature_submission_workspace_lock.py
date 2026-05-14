"""Tests for FeatureSubmissionService workspace lock integration."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.results import FeatureExecutionAdvisory, FeatureTaskSubmission
from src.application.services.feature_submission_service import FeatureSubmissionService


def _make_handler(*, credit_service=None):
    """Create a FeatureSubmissionService with mocked dependencies."""
    user = MagicMock()
    user.id = "user-1"

    workspace_service = AsyncMock()
    ws = MagicMock()
    ws.user_id = "user-1"
    ws.type = MagicMock(value="thesis")
    ws.name = "Test WS"
    ws.description = ""
    ws.discipline = ""
    ws.config = {}
    workspace_service.get = AsyncMock(return_value=ws)

    if credit_service is None:
        credit_service = AsyncMock()
        credit_service.can_start_feature_task = AsyncMock(return_value=True)
        credit_service.db = AsyncMock()

    reference_service = AsyncMock()
    execution_service = AsyncMock()

    return FeatureSubmissionService(
        actor_id=str(user.id),
        workspace_service=workspace_service,
        reference_service=reference_service,
        credit_service=credit_service,
        execution_service=execution_service,
    )


def _make_feature():
    feature = MagicMock()
    feature.id = "deep_research"
    feature.name = "Deep Research"
    feature.agent = "research"
    feature.agent_label = "Research Agent"
    return feature


class TestWorkspaceLockIntegration:
    @pytest.mark.asyncio
    async def test_dispatch_uses_lock_when_redis_available(self):
        lock_acquired = False

        @asynccontextmanager
        async def mock_lock(workspace_id, timeout=None):
            nonlocal lock_acquired
            lock_acquired = True
            yield

        redis_client = MagicMock()
        redis_client.workspace_lock = mock_lock
        redis_client.client = AsyncMock()

        handler = _make_handler()
        worker = MagicMock()
        worker.id = "worker-123"

        with (
            patch(
                "src.application.services.feature_submission_service.get_workspace_feature",
                return_value=_make_feature(),
            ),
            patch("src.task.tasks.execution.execute_execution") as execute_task,
        ):
            execute_task.apply_async = MagicMock(return_value=worker)
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=redis_client,
                execution_id="exec-1",
            )

        assert lock_acquired
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "worker-123"
        assert result.execution_id == "exec-1"
        handler.execution_service.update_execution.assert_awaited_once_with(
            "exec-1",
            dispatch_mode="celery_worker",
            worker_task_id="worker-123",
        )

    @pytest.mark.asyncio
    async def test_dispatch_works_without_redis(self):
        handler = _make_handler()
        worker = MagicMock()
        worker.id = "worker-123"

        with (
            patch(
                "src.application.services.feature_submission_service.get_workspace_feature",
                return_value=_make_feature(),
            ),
            patch("src.task.tasks.execution.execute_execution") as execute_task,
        ):
            execute_task.apply_async = MagicMock(return_value=worker)
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=None,
                execution_id="exec-1",
            )

        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "worker-123"
        assert result.execution_id == "exec-1"
        handler.execution_service.update_execution.assert_awaited_once_with(
            "exec-1",
            dispatch_mode="celery_worker",
            worker_task_id="worker-123",
        )

    @pytest.mark.asyncio
    async def test_lock_failure_returns_warning(self):
        @asynccontextmanager
        async def mock_lock(workspace_id, timeout=None):
            raise RuntimeError("Could not acquire lock")
            yield  # pragma: no cover

        redis_client = MagicMock()
        redis_client.workspace_lock = mock_lock

        handler = _make_handler()

        with patch(
            "src.application.services.feature_submission_service.get_workspace_feature",
            return_value=_make_feature(),
        ):
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=redis_client,
                execution_id="exec-1",
            )

        assert isinstance(result, FeatureExecutionAdvisory)
        assert result.code == "workspace_locked"

    @pytest.mark.asyncio
    async def test_lock_backend_error_falls_back_to_unlocked_dispatch(self):
        @asynccontextmanager
        async def mock_lock(workspace_id, timeout=None):
            raise RuntimeError("Redis not connected. Call connect() first.")
            yield  # pragma: no cover

        redis_client = MagicMock()
        redis_client.workspace_lock = mock_lock

        handler = _make_handler()
        worker = MagicMock()
        worker.id = "worker-123"

        with (
            patch(
                "src.application.services.feature_submission_service.get_workspace_feature",
                return_value=_make_feature(),
            ),
            patch("src.task.tasks.execution.execute_execution") as execute_task,
        ):
            execute_task.apply_async = MagicMock(return_value=worker)
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=redis_client,
                execution_id="exec-1",
            )

        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "worker-123"
        assert result.execution_id == "exec-1"
        handler.execution_service.update_execution.assert_awaited_once_with(
            "exec-1",
            dispatch_mode="celery_worker",
            worker_task_id="worker-123",
        )

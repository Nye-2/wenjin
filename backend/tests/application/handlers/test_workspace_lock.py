"""Tests for workspace lock integration in FeatureExecutionHandler."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.handlers.feature_execution_handler import FeatureExecutionHandler
from src.application.results import FeatureExecutionAdvisory, FeatureTaskSubmission


def _make_handler(*, task_service=None, credit_service=None):
    """Create a FeatureExecutionHandler with mocked dependencies."""
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

    if task_service is None:
        task_service = AsyncMock()
        task_service.find_active_task = AsyncMock(return_value=None)
        task_service.submit_task = AsyncMock(return_value="task-123")

    if credit_service is None:
        credit_service = AsyncMock()
        credit_service.consume_for_feature = AsyncMock(return_value=None)
        credit_service.db = AsyncMock()

    literature_service = AsyncMock()

    return FeatureExecutionHandler(
        user=user,
        workspace_service=workspace_service,
        task_service=task_service,
        literature_service=literature_service,
        credit_service=credit_service,
    )


def _make_feature():
    """Create a mock feature."""
    feature = MagicMock()
    feature.id = "deep_research"
    feature.name = "Deep Research"
    feature.task_type = "deep_research"
    feature.agent = "research"
    feature.agent_label = "Research Agent"
    feature.handler_key = "deep_research"
    return feature


class TestWorkspaceLockIntegration:
    @pytest.mark.asyncio
    async def test_submit_uses_lock_when_redis_available(self):
        """When redis_client is provided, workspace_lock should be used."""
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

        with patch(
            "src.application.handlers.feature_execution_handler.get_workspace_feature",
            return_value=_make_feature(),
        ):
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=redis_client,
            )

        assert lock_acquired
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "task-123"

    @pytest.mark.asyncio
    async def test_submit_works_without_redis(self):
        """When redis_client is None, should still submit successfully."""
        handler = _make_handler()

        with patch(
            "src.application.handlers.feature_execution_handler.get_workspace_feature",
            return_value=_make_feature(),
        ):
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=None,
            )

        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "task-123"

    @pytest.mark.asyncio
    async def test_lock_failure_returns_warning(self):
        """When workspace lock cannot be acquired, return a warning."""

        @asynccontextmanager
        async def mock_lock(workspace_id, timeout=None):
            raise RuntimeError("Could not acquire lock")
            yield  # pragma: no cover

        redis_client = MagicMock()
        redis_client.workspace_lock = mock_lock

        handler = _make_handler()

        with patch(
            "src.application.handlers.feature_execution_handler.get_workspace_feature",
            return_value=_make_feature(),
        ):
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=redis_client,
            )

        assert isinstance(result, FeatureExecutionAdvisory)
        assert result.code == "workspace_locked"

    @pytest.mark.asyncio
    async def test_lock_backend_error_falls_back_to_unlocked_submit(self):
        """Non-contention lock runtime errors should fall back to unlocked submit."""

        @asynccontextmanager
        async def mock_lock(workspace_id, timeout=None):
            raise RuntimeError("Redis not connected. Call connect() first.")
            yield  # pragma: no cover

        redis_client = MagicMock()
        redis_client.workspace_lock = mock_lock

        handler = _make_handler()

        with patch(
            "src.application.handlers.feature_execution_handler.get_workspace_feature",
            return_value=_make_feature(),
        ):
            result = await handler.execute(
                workspace_id="ws-1",
                feature_id="deep_research",
                params={},
                redis_client=redis_client,
            )

        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "task-123"

"""Tests for the feature submission preflight + dispatch service."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.errors import (
    AccessDeniedError,
    InternalServiceError,
    NotFoundError,
    PaymentRequiredError,
)
from src.application.results import FeatureExecutionAdvisory, FeatureTaskSubmission
from src.application.services.feature_submission_service import (
    LITERATURE_THRESHOLD,
    FeatureSubmissionService,
)
from src.application.workspace_resolvers import resolve_workspace_type


def _make_workspace(user_id="user-1", workspace_type_value="thesis"):
    ws = MagicMock()
    ws.id = "ws-1"
    ws.user_id = user_id
    ws.name = "Test Workspace"
    ws.description = "A workspace"
    ws.discipline = "cs"
    ws.config = {}
    ws.type = MagicMock(value=workspace_type_value)
    return ws


def _make_feature(feature_id="test_feature", name="Test Feature"):
    feature = MagicMock()
    feature.id = feature_id
    feature.name = name
    feature.agent = "test_agent"
    feature.agent_label = "Agent"
    return feature


def _make_handler(actor_id: str = "user-1", **overrides):
    credit_service = overrides.get("credit_service", AsyncMock())
    if not hasattr(credit_service, "db"):
        credit_service.db = AsyncMock()
    if not hasattr(credit_service, "can_start_feature_task"):
        credit_service.can_start_feature_task = AsyncMock(return_value=True)
    return FeatureSubmissionService(
        actor_id=actor_id,
        workspace_service=overrides.get("workspace_service", AsyncMock()),
        reference_service=overrides.get("reference_service", AsyncMock()),
        credit_service=credit_service,
        execution_service=overrides.get("execution_service"),
    )


class TestResolveWorkspaceType:
    def test_enum_value(self):
        ws = MagicMock()
        ws.type = MagicMock(value="thesis")
        assert resolve_workspace_type(ws) == "thesis"

    def test_string_value(self):
        ws = MagicMock(spec=[])
        ws.type = "sci"
        assert resolve_workspace_type(ws) == "sci"

    def test_none_raises(self):
        ws = MagicMock(spec=[])
        ws.type = None
        with pytest.raises(ValueError, match="Workspace type is not configured"):
            resolve_workspace_type(ws)

    def test_missing_type_raises(self):
        ws = object()
        with pytest.raises(ValueError, match="Workspace type is not configured"):
            resolve_workspace_type(ws)


class TestFeatureSubmissionService:
    @pytest.mark.asyncio
    async def test_raises_404_for_missing_workspace(self):
        ws_service = AsyncMock()
        ws_service.get.return_value = None
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(NotFoundError) as exc_info:
            await handler.execute("ws-1", "some_feature", execution_id="exec-1")
        assert "Workspace not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_raises_403_for_non_owner(self):
        ws = _make_workspace(user_id="other-user")
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(AccessDeniedError) as exc_info:
            await handler.execute("ws-1", "some_feature", execution_id="exec-1")
        assert "Access denied" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_raises_500_when_workspace_type_missing(self):
        ws = _make_workspace()
        ws.type = None
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(InternalServiceError) as exc_info:
            await handler.execute("ws-1", "some_feature", execution_id="exec-1")
        assert "Workspace type is not configured" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_raises_404_for_unknown_feature(self, mock_get_feature):
        mock_get_feature.return_value = None
        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(NotFoundError) as exc_info:
            await handler.execute("ws-1", "unknown_feature", execution_id="exec-1")
        assert "unknown_feature" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_requires_execution_id(self, mock_get_feature):
        mock_get_feature.return_value = _make_feature()
        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(InternalServiceError, match="execution_id is required"):
            await handler.execute("ws-1", "test_feature", execution_id="")

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_literature_insufficient_returns_warning(self, mock_get_feature):
        feature = _make_feature("thesis_writing", "论文写作")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        lit_service = AsyncMock()
        lit_service.count_references.return_value = {"total": 3, "core": 0}

        handler = _make_handler(
            workspace_service=ws_service,
            reference_service=lit_service,
        )

        result = await handler.execute(
            "ws-1", "thesis_writing", {"action": "write_all"}, execution_id="exec-1"
        )
        assert isinstance(result, FeatureExecutionAdvisory)
        assert result.code == "literature_insufficient"
        assert result.context["current"] == 3
        assert result.context["recommended"] == LITERATURE_THRESHOLD

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_literature_insufficient_uppercase_action_is_normalized(
        self, mock_get_feature
    ):
        feature = _make_feature("thesis_writing", "论文写作")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        lit_service = AsyncMock()
        lit_service.count_references.return_value = {"total": 2, "core": 0}

        handler = _make_handler(
            workspace_service=ws_service,
            reference_service=lit_service,
        )

        result = await handler.execute(
            "ws-1", "thesis_writing", {"action": "WRITE_CHAPTER"}, execution_id="exec-1"
        )
        assert isinstance(result, FeatureExecutionAdvisory)
        assert result.code == "literature_insufficient"
        lit_service.count_references.assert_awaited_once_with("ws-1")

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_literature_check_skipped_for_non_writing_actions(
        self, mock_get_feature
    ):
        feature = _make_feature("thesis_writing", "论文写作")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        lit_service = AsyncMock()
        lit_service.count_references.return_value = {"total": 0, "core": 0}

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = True
        execution_service = AsyncMock()
        execution_service = AsyncMock()
        execution_service = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            reference_service=lit_service,
            credit_service=credit_service,
            execution_service=execution_service,
        )

        worker = MagicMock()
        worker.id = "worker-1"
        with patch("src.task.tasks.execution.execute_execution") as execute_task:
            execute_task.apply_async = MagicMock(return_value=worker)
            result = await handler.execute(
                "ws-1", "thesis_writing", {"action": "generate_outline"}, execution_id="exec-1"
            )

        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "worker-1"
        execution_service.update_execution.assert_awaited_once_with(
            "exec-1",
            dispatch_mode="celery_worker",
            worker_task_id="worker-1",
        )
        lit_service.count_references.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_thesis_writing_missing_action_defaults_to_write_all(
        self, mock_get_feature
    ):
        feature = _make_feature("thesis_writing", "论文写作")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        lit_service = AsyncMock()
        lit_service.count_references.return_value = {"total": 20, "core": 5}

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = True
        execution_service = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            reference_service=lit_service,
            credit_service=credit_service,
            execution_service=execution_service,
        )

        worker = MagicMock()
        worker.id = "worker-1"
        with patch("src.task.tasks.execution.execute_execution") as execute_task:
            execute_task.apply_async = MagicMock(return_value=worker)
            result = await handler.execute("ws-1", "thesis_writing", {}, execution_id="exec-1")

        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "worker-1"
        execution_service.update_execution.assert_awaited_once_with(
            "exec-1",
            dispatch_mode="celery_worker",
            worker_task_id="worker-1",
        )

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_feature_submission_blocks_when_feature_budget_exhausted(self, mock_get_feature):
        feature = _make_feature("deep_research", "深度调研")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = False
        credit_service.get_feature_billing_policy = MagicMock(
            return_value=MagicMock(free_tokens=0)
        )
        execution_service = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            credit_service=credit_service,
            execution_service=execution_service,
        )

        with pytest.raises(PaymentRequiredError) as exc_info:
            await handler.execute("ws-1", "deep_research", {"query": "agent"}, execution_id="exec-1")

        assert "Compute feature 免费额度已用尽" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_dispatch_failure_raises_internal_service_error(self, mock_get_feature):
        feature = _make_feature("deep_research", "深度调研")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = True
        execution_service = AsyncMock()
        execution_service = AsyncMock()
        execution_service = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            credit_service=credit_service,
            execution_service=execution_service,
        )

        with patch("src.task.tasks.execution.execute_execution") as execute_task:
            execute_task.apply_async.side_effect = RuntimeError("queue down")
            with pytest.raises(InternalServiceError, match="Failed to dispatch feature execution"):
                await handler.execute("ws-1", "deep_research", {"query": "agent"}, execution_id="exec-1")

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_idempotency_key_returns_cached_execution(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = True
        execution_service = AsyncMock()

        redis_client = AsyncMock()
        redis_client.client = AsyncMock()
        redis_client.client.get = AsyncMock(return_value="exec-cached")

        handler = _make_handler(
            workspace_service=ws_service,
            credit_service=credit_service,
            execution_service=execution_service,
        )

        result = await handler.execute(
            "ws-1",
            "test_feature",
            idempotency_key="key-123",
            redis_client=redis_client,
            execution_id="exec-new",
        )
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "exec-cached"
        assert result.execution_id == "exec-cached"

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_idempotency_key_stored_after_new_dispatch(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = True
        execution_service = AsyncMock()

        @asynccontextmanager
        async def _noop_lock(workspace_id, timeout=None):
            yield

        redis_client = AsyncMock()
        redis_client.workspace_lock = _noop_lock
        redis_client.client = AsyncMock()
        redis_client.client.get = AsyncMock(return_value=None)
        redis_client.client.set = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            credit_service=credit_service,
            execution_service=execution_service,
        )

        worker = MagicMock()
        worker.id = "worker-999"
        with patch("src.task.tasks.execution.execute_execution") as execute_task:
            execute_task.apply_async = MagicMock(return_value=worker)
            result = await handler.execute(
                "ws-1",
                "test_feature",
                idempotency_key="key-new",
                redis_client=redis_client,
                execution_id="exec-new",
            )
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "worker-999"
        execution_service.update_execution.assert_awaited_once_with(
            "exec-new",
            dispatch_mode="celery_worker",
            worker_task_id="worker-999",
        )
        redis_client.client.set.assert_called_once()
        key = redis_client.client.set.call_args.args[0]
        value = redis_client.client.set.call_args.args[1]
        assert "idempotency:" in key
        assert value == "exec-new"

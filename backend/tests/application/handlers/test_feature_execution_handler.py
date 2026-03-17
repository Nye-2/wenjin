"""Tests for the feature execution handler.

Verifies orchestration logic independently of HTTP routing:
- Workspace ownership enforcement
- Feature lookup
- Literature threshold guard
- Idempotent task deduplication
- Credit billing and failure compensation
- Task submission and payload construction
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.application.handlers.feature_execution_handler import (
    LITERATURE_THRESHOLD,
    FeatureExecutionHandler,
    build_task_payload,
    resolve_workspace_type,
)
from src.services.credit_service import InsufficientCreditsError
from src.task.service import ConcurrencyLimitError

# ============ Test Helpers ============


def _make_user(user_id="user-1"):
    user = MagicMock()
    user.id = user_id
    return user


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
    feature.task_type = "workspace_feature"
    feature.handler_key = f"test.{feature_id}"
    return feature


def _make_handler(user=None, **overrides):
    credit_service = overrides.get("credit_service", AsyncMock())
    if not hasattr(credit_service, "db"):
        credit_service.db = AsyncMock()
    return FeatureExecutionHandler(
        user=user or _make_user(),
        workspace_service=overrides.get("workspace_service", AsyncMock()),
        task_service=overrides.get("task_service", AsyncMock()),
        literature_service=overrides.get("literature_service", AsyncMock()),
        credit_service=credit_service,
    )


# ============ Unit Tests: resolve_workspace_type ============


class TestResolveWorkspaceType:
    def test_enum_value(self):
        ws = MagicMock()
        ws.type = MagicMock(value="thesis")
        assert resolve_workspace_type(ws) == "thesis"

    def test_string_value(self):
        ws = MagicMock(spec=[])
        ws.type = "sci"
        assert resolve_workspace_type(ws) == "sci"

    def test_none_defaults_to_thesis(self):
        ws = MagicMock(spec=[])
        ws.type = None
        assert resolve_workspace_type(ws) == "thesis"

    def test_missing_type_defaults_to_thesis(self):
        ws = object()
        assert resolve_workspace_type(ws) == "thesis"


# ============ Unit Tests: build_task_payload ============


class TestBuildTaskPayload:
    def test_canonical_fields_override_user_params(self):
        ws = _make_workspace()
        feature = _make_feature("my_feature", "My Feature")

        payload = build_task_payload(
            workspace=ws,
            workspace_id="ws-1",
            workspace_type="thesis",
            feature=feature,
            params={"workspace_id": "evil", "feature_id": "evil", "extra": "kept"},
            thread_id="t-1",
        )

        # Canonical fields override user params
        assert payload["workspace_id"] == "ws-1"
        assert payload["feature_id"] == "my_feature"
        assert payload["handler_key"] == "test.my_feature"
        assert payload["thread_id"] == "t-1"
        # User params that don't conflict are kept
        assert payload["extra"] == "kept"

    def test_includes_workspace_metadata(self):
        ws = _make_workspace()
        feature = _make_feature()

        payload = build_task_payload(
            workspace=ws,
            workspace_id="ws-1",
            workspace_type="thesis",
            feature=feature,
            params={},
            thread_id=None,
        )

        assert payload["workspace_name"] == "Test Workspace"
        assert payload["workspace_description"] == "A workspace"
        assert payload["workspace_discipline"] == "cs"
        assert payload["workspace_config"] == {}
        assert payload["params"] == {}


# ============ Unit Tests: FeatureExecutionHandler ============


class TestFeatureExecutionHandler:
    """Tests for the handler orchestration logic."""

    @pytest.mark.asyncio
    async def test_raises_404_for_missing_workspace(self):
        ws_service = AsyncMock()
        ws_service.get.return_value = None
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(HTTPException) as exc_info:
            await handler.execute("ws-1", "some_feature")
        assert exc_info.value.status_code == 404
        assert "Workspace not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_raises_403_for_non_owner(self):
        ws = _make_workspace(user_id="other-user")
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(HTTPException) as exc_info:
            await handler.execute("ws-1", "some_feature")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_raises_404_for_unknown_feature(self, mock_get_feature):
        mock_get_feature.return_value = None
        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(HTTPException) as exc_info:
            await handler.execute("ws-1", "unknown_feature")
        assert exc_info.value.status_code == 404
        assert "unknown_feature" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_literature_insufficient_returns_warning(self, mock_get_feature):
        feature = _make_feature("thesis_writing", "论文写作")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        lit_service = AsyncMock()
        lit_service.count_literature.return_value = {"total": 3, "core": 0}

        handler = _make_handler(
            workspace_service=ws_service,
            literature_service=lit_service,
        )

        result = await handler.execute(
            "ws-1", "thesis_writing", {"action": "write_all"}
        )
        assert result["status"] == "warning"
        assert result["warning"] == "literature_insufficient"
        assert result["task_id"] is None
        assert result["detail"]["current"] == 3
        assert result["detail"]["recommended"] == LITERATURE_THRESHOLD

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_literature_check_skipped_for_non_writing_actions(
        self, mock_get_feature
    ):
        """Actions other than write_chapter/write_all skip literature check."""
        feature = _make_feature("thesis_writing", "论文写作")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        lit_service = AsyncMock()
        lit_service.count_literature.return_value = {"total": 0, "core": 0}

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "task-1"

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = None

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            literature_service=lit_service,
            credit_service=credit_service,
        )

        result = await handler.execute(
            "ws-1", "thesis_writing", {"action": "generate_outline"}
        )
        assert result["task_id"] == "task-1"
        lit_service.count_literature.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_idempotent_returns_existing_task(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = "existing-task-42"

        credit_service = AsyncMock()
        credit_service.consume_for_feature = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert result["task_id"] == "existing-task-42"
        assert result["status"] == "pending"
        credit_service.consume_for_feature.assert_not_called()
        task_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_insufficient_credits_returns_warning(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None

        credit_service = AsyncMock()
        credit_service.consume_for_feature.side_effect = InsufficientCreditsError(
            current_balance=10, required=30
        )

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert result["status"] == "warning"
        assert result["warning"] == "insufficient_credits"
        assert result["detail"]["current"] == 10
        assert result["detail"]["required"] == 30
        task_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_successful_execution_submits_task(self, mock_get_feature):
        feature = _make_feature("deep_research", "深度调研")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "new-task-789"

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = None

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute(
            "ws-1", "deep_research", {"query": "test"}, "thread-1"
        )
        assert result["task_id"] == "new-task-789"
        assert result["status"] == "pending"
        assert result["feature_id"] == "deep_research"
        assert result["warning"] is None
        task_service.submit_task.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_credit_transaction_linked_to_task(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "task-999"

        tx = MagicMock()
        tx.id = "tx-1"
        tx.amount = -20

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = tx
        credit_service.db = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert result["task_id"] == "task-999"
        # Credit transaction should be linked
        assert tx.task_id == "task-999"
        credit_service.db.commit.assert_called_once()

        # Task payload should include credit info
        submit_kwargs = task_service.submit_task.call_args.kwargs
        assert submit_kwargs["payload"]["credit_transaction_id"] == "tx-1"
        assert submit_kwargs["payload"]["credit_cost"] == 20

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_refunds_on_queue_failure(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.side_effect = RuntimeError("Queue down")

        tx = MagicMock()
        tx.id = "tx-1"
        tx.amount = -30

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = tx
        credit_service.db = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        with pytest.raises(HTTPException) as exc_info:
            await handler.execute("ws-1", "test_feature")
        assert exc_info.value.status_code == 500
        credit_service.refund_failed_task.assert_called_once_with(
            user_id="user-1",
            original_transaction_id="tx-1",
            reason="任务排队失败退款",
        )

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_no_refund_when_no_credit_transaction(self, mock_get_feature):
        """When credit billing returns None (free feature), no refund on failure."""
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.side_effect = RuntimeError("Queue down")

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = None

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        with pytest.raises(HTTPException):
            await handler.execute("ws-1", "test_feature")
        credit_service.refund_failed_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_concurrency_limit_returns_warning_and_refunds(self, mock_get_feature):
        """ConcurrencyLimitError should return a warning and refund credits."""
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.side_effect = ConcurrencyLimitError(
            current=3, limit=3
        )

        tx = MagicMock()
        tx.id = "tx-1"
        tx.amount = -20

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = tx
        credit_service.db = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert result["status"] == "warning"
        assert result["warning"] == "concurrency_limit"
        assert result["detail"]["current"] == 3
        assert result["detail"]["limit"] == 3
        assert result["task_id"] is None
        credit_service.refund_failed_task.assert_called_once()


class TestIdempotencyKey:
    """Tests for Idempotency-Key based deduplication."""

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_idempotency_key_returns_cached_task(self, mock_get_feature):
        """When idempotency_key maps to an existing task, return it."""
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "new-task-1"

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = None

        # Mock Redis for idempotency key lookup
        redis_client = AsyncMock()
        redis_client.client = AsyncMock()
        redis_client.client.get = AsyncMock(return_value="cached-task-42")

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute(
            "ws-1", "test_feature",
            idempotency_key="key-123",
            redis_client=redis_client,
        )
        assert result["task_id"] == "cached-task-42"
        assert result["status"] == "pending"
        # Should NOT bill or submit new task
        credit_service.consume_for_feature.assert_not_called()
        task_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_idempotency_key_stored_after_new_task(self, mock_get_feature):
        """When idempotency_key is new, execute normally and store the mapping."""
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "new-task-999"

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = None

        @asynccontextmanager
        async def _noop_lock(workspace_id, timeout=None):
            yield

        redis_client = AsyncMock()
        redis_client.workspace_lock = _noop_lock
        redis_client.client = AsyncMock()
        redis_client.client.get = AsyncMock(return_value=None)  # No cached key
        redis_client.client.set = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute(
            "ws-1", "test_feature",
            idempotency_key="key-new",
            redis_client=redis_client,
        )
        assert result["task_id"] == "new-task-999"
        # Verify the key was stored
        redis_client.client.set.assert_called_once()
        call_args = redis_client.client.set.call_args
        key = call_args.args[0]
        value = call_args.args[1]
        assert "idempotency:" in key
        assert value == "new-task-999"

    @pytest.mark.asyncio
    @patch("src.application.handlers.feature_execution_handler.get_workspace_feature")
    async def test_no_idempotency_key_skips_check(self, mock_get_feature):
        """When no idempotency_key is provided, skip the Redis check entirely."""
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "new-task-1"

        credit_service = AsyncMock()
        credit_service.consume_for_feature.return_value = None

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert result["task_id"] == "new-task-1"

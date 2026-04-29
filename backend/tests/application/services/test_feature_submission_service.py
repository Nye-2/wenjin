"""Tests for the feature submission service.

Verifies orchestration logic independently of HTTP routing:
- Workspace ownership enforcement
- Feature lookup
- Literature threshold guard
- Idempotent task deduplication
- Token billing is settled after task completion
- Task submission and payload construction
"""

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
    build_task_payload,
)
from src.application.workspace_resolvers import resolve_workspace_type
from src.task.service import ConcurrencyLimitError

# ============ Test Helpers ============


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


def _make_handler(actor_id: str = "user-1", **overrides):
    credit_service = overrides.get("credit_service", AsyncMock())
    if not hasattr(credit_service, "db"):
        credit_service.db = AsyncMock()
    if not hasattr(credit_service, "can_start_feature_task"):
        credit_service.can_start_feature_task = AsyncMock(return_value=True)
    return FeatureSubmissionService(
        actor_id=actor_id,
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

    def test_none_raises(self):
        ws = MagicMock(spec=[])
        ws.type = None
        with pytest.raises(ValueError, match="Workspace type is not configured"):
            resolve_workspace_type(ws)

    def test_missing_type_raises(self):
        ws = object()
        with pytest.raises(ValueError, match="Workspace type is not configured"):
            resolve_workspace_type(ws)


# ============ Unit Tests: build_task_payload ============


class TestBuildTaskPayload:
    def test_canonical_fields_are_separate_from_business_params(self):
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

        assert payload["workspace_id"] == "ws-1"
        assert payload["feature_id"] == "my_feature"
        assert payload["handler_key"] == "test.my_feature"
        assert payload["thread_id"] == "t-1"
        assert payload["params"] == {
            "workspace_id": "evil",
            "feature_id": "evil",
            "extra": "kept",
        }
        assert "extra" not in payload

    def test_business_params_stay_nested_without_top_level_mirroring(self):
        ws = _make_workspace()
        feature = _make_feature("my_feature", "My Feature")

        payload = build_task_payload(
            workspace=ws,
            workspace_id="ws-1",
            workspace_type="thesis",
            feature=feature,
            params={
                "action": "write_all",
                "topic": "LLM planning",
                "context_artifact_ids": ["artifact-1"],
            },
            thread_id="t-1",
        )

        assert payload["params"]["action"] == "write_all"
        assert payload["params"]["topic"] == "LLM planning"
        assert payload["params"]["context_artifact_ids"] == ["artifact-1"]
        assert "action" not in payload
        assert "topic" not in payload
        assert "context_artifact_ids" not in payload

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
        assert payload["skill_id"] is None
        assert payload["skill_name"] is None
        assert payload["params"] == {}

    def test_resolves_canonical_skill_for_known_feature(self):
        ws = _make_workspace()
        feature = _make_feature("deep_research", "深度调研")

        payload = build_task_payload(
            workspace=ws,
            workspace_id="ws-1",
            workspace_type="thesis",
            feature=feature,
            params={"query": "agent"},
            thread_id="t-1",
        )

        assert payload["skill_id"] == "deep-research"
        assert payload["skill_name"] == "深度调研"


# ============ Unit Tests: FeatureSubmissionService ============


class TestFeatureSubmissionService:
    """Tests for the submission orchestration logic."""

    @pytest.mark.asyncio
    async def test_raises_404_for_missing_workspace(self):
        ws_service = AsyncMock()
        ws_service.get.return_value = None
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(NotFoundError) as exc_info:
            await handler.execute("ws-1", "some_feature")
        assert "Workspace not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_raises_403_for_non_owner(self):
        ws = _make_workspace(user_id="other-user")
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(AccessDeniedError) as exc_info:
            await handler.execute("ws-1", "some_feature")
        assert "Access denied" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_raises_500_when_workspace_type_missing(self):
        ws = _make_workspace()
        ws.type = None
        ws_service = AsyncMock()
        ws_service.get.return_value = ws
        handler = _make_handler(workspace_service=ws_service)

        with pytest.raises(InternalServiceError) as exc_info:
            await handler.execute("ws-1", "some_feature")
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
            await handler.execute("ws-1", "unknown_feature")
        assert "unknown_feature" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        lit_service.count_literature.return_value = {"total": 2, "core": 0}

        handler = _make_handler(
            workspace_service=ws_service,
            literature_service=lit_service,
        )

        result = await handler.execute(
            "ws-1", "thesis_writing", {"action": "WRITE_CHAPTER"}
        )
        assert isinstance(result, FeatureExecutionAdvisory)
        assert result.code == "literature_insufficient"
        lit_service.count_literature.assert_awaited_once_with("ws-1")

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "task-1"
        lit_service.count_literature.assert_not_called()

        submit_payload = task_service.submit_task.await_args.kwargs["payload"]
        assert submit_payload["skill_id"] == "framework-designer"
        assert submit_payload["skill_name"] == "大纲设计"

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
        lit_service.count_literature.return_value = {"total": 20, "core": 5}

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

        result = await handler.execute("ws-1", "thesis_writing", {})
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "task-1"

        submit_payload = task_service.submit_task.await_args.kwargs["payload"]
        assert submit_payload["params"]["action"] == "write_all"
        assert submit_payload["skill_id"] == "fullpaper-writer"
        assert submit_payload["skill_name"] == "论文撰写"
        assert "action" not in submit_payload

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "existing-task-42"
        credit_service.consume_for_feature.assert_not_called()
        task_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        credit_service.can_start_feature_task.return_value = True

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute(
            "ws-1", "deep_research", {"query": "test"}, "thread-1"
        )
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "new-task-789"
        assert result.feature_id == "deep_research"
        task_service.submit_task.assert_called_once()

        submit_payload = task_service.submit_task.await_args.kwargs["payload"]
        assert submit_payload["skill_id"] == "deep-research"
        assert submit_payload["skill_name"] == "深度调研"
        credit_service.can_start_feature_task.assert_awaited_once_with("user-1")
        credit_service.consume_for_feature.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_feature_submission_blocks_when_feature_budget_exhausted(self, mock_get_feature):
        feature = _make_feature("deep_research", "深度调研")
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None

        credit_service = AsyncMock()
        credit_service.can_start_feature_task.return_value = False
        credit_service.get_feature_billing_policy = MagicMock(
            return_value=MagicMock(
                free_tokens=0,
            )
        )

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        with pytest.raises(PaymentRequiredError) as exc_info:
            await handler.execute("ws-1", "deep_research", {"query": "agent"})

        assert "Compute feature 免费额度已用尽" in exc_info.value.message
        task_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_feature_submission_does_not_precharge_credits(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.return_value = "task-999"

        credit_service = AsyncMock()
        credit_service.consume_for_feature = AsyncMock()
        credit_service.db = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "task-999"
        credit_service.consume_for_feature.assert_not_called()

        submit_kwargs = task_service.submit_task.call_args.kwargs
        assert "credit_transaction_id" not in submit_kwargs["payload"]
        assert "credit_cost" not in submit_kwargs["payload"]

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_queue_failure_does_not_refund_without_precharge(self, mock_get_feature):
        feature = _make_feature()
        mock_get_feature.return_value = feature

        ws = _make_workspace()
        ws_service = AsyncMock()
        ws_service.get.return_value = ws

        task_service = AsyncMock()
        task_service.find_active_task.return_value = None
        task_service.submit_task.side_effect = RuntimeError("Queue down")

        credit_service = AsyncMock()
        credit_service.consume_for_feature = AsyncMock()
        credit_service.db = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        with pytest.raises(InternalServiceError) as exc_info:
            await handler.execute("ws-1", "test_feature")
        assert "Failed to queue feature task" in exc_info.value.message
        credit_service.consume_for_feature.assert_not_called()
        credit_service.refund_failed_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
    async def test_concurrency_limit_returns_warning_without_refund(self, mock_get_feature):
        """ConcurrencyLimitError should return a warning without billing side effects."""
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

        credit_service = AsyncMock()
        credit_service.consume_for_feature = AsyncMock()
        credit_service.db = AsyncMock()

        handler = _make_handler(
            workspace_service=ws_service,
            task_service=task_service,
            credit_service=credit_service,
        )

        result = await handler.execute("ws-1", "test_feature")
        assert isinstance(result, FeatureExecutionAdvisory)
        assert result.code == "concurrency_limit"
        assert result.context["current"] == 3
        assert result.context["limit"] == 3
        credit_service.consume_for_feature.assert_not_called()
        credit_service.refund_failed_task.assert_not_called()


class TestIdempotencyKey:
    """Tests for Idempotency-Key based deduplication."""

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "cached-task-42"
        # Should NOT bill or submit new task
        credit_service.consume_for_feature.assert_not_called()
        task_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "new-task-999"
        # Verify the key was stored
        redis_client.client.set.assert_called_once()
        call_args = redis_client.client.set.call_args
        key = call_args.args[0]
        value = call_args.args[1]
        assert "idempotency:" in key
        assert value == "new-task-999"

    @pytest.mark.asyncio
    @patch("src.application.services.feature_submission_service.get_workspace_feature")
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
        assert isinstance(result, FeatureTaskSubmission)
        assert result.task_id == "new-task-1"

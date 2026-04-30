"""Tests for TaskService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from pydantic import BaseModel

from src.task.service import ConcurrencyLimitError, TaskService
from src.task.store import TaskStore


@pytest_asyncio.fixture
async def task_service(test_session, mock_redis):
    """Create TaskService instance with test fixtures."""
    from tests.task.conftest import FixtureTaskRecord

    store = TaskStore(mock_redis, test_session)
    store._test_model = FixtureTaskRecord
    yield TaskService(store)


@pytest.fixture(autouse=True)
def mock_task_executor():
    """Avoid external Celery dependency for TaskService unit tests."""
    mock_executor = AsyncMock()
    with patch("src.task.service.get_executor", return_value=mock_executor):
        yield mock_executor


class TestTaskService:
    """Tests for TaskService."""

    @pytest.mark.asyncio
    async def test_submit_task(self, task_service, mock_task_executor):
        """Test submitting a task."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={"feature_id": "deep_research", "query": "machine learning"},
                priority=5,
            )

            assert task_id is not None
            assert len(task_id) == 36  # UUID format
            submitted_payload = mock_task_executor.execute.await_args.kwargs["payload"]
            assert submitted_payload["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_submit_invalid_task_type(self, task_service):
        """Test submitting invalid task type."""
        with pytest.raises(ValueError, match="Unknown task type"):
            await task_service.submit_task(
                user_id="user-1",
                task_type="invalid_type",
                payload={},
            )

    @pytest.mark.asyncio
    async def test_get_task_status(self, task_service):
        """Test getting task status."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={
                    "workspace_id": "ws-1",
                    "workspace_type": "sci",
                    "feature_id": "literature_search",
                    "query": "test",
                },
            )

            status = await task_service.get_task_status(task_id, "user-1")
            assert status is not None
            assert status["task_type"] == "workspace_feature"
            assert status["status"] in ("pending", "running")

    @pytest.mark.asyncio
    async def test_get_task_status_wrong_user(self, task_service):
        """Test getting task status with wrong user."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={"feature_id": "deep_research"},
            )

            status = await task_service.get_task_status(task_id, "user-2")
            assert status is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, task_service):
        """Test listing tasks."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            for i in range(3):
                await task_service.submit_task(
                    user_id="user-list",
                    task_type="workspace_feature",
                    payload={"feature_id": "deep_research", "index": i},
                )

            tasks = await task_service.list_tasks("user-list")
            assert len(tasks) >= 3

    @pytest.mark.asyncio
    async def test_list_tasks_filters_by_workspace(self, task_service):
        """Workspace-scoped task listing should only return matching tasks."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            await task_service.submit_task(
                user_id="user-workspace-filter",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-a", "feature_id": "deep_research"},
            )
            await task_service.submit_task(
                user_id="user-workspace-filter",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-b", "feature_id": "deep_research"},
            )

            tasks = await task_service.list_tasks(
                "user-workspace-filter",
                workspace_id="ws-a",
            )

            assert len(tasks) == 1
            assert tasks[0]["workspace_id"] == "ws-a"

    @pytest.mark.asyncio
    async def test_queue_failure_marks_record_as_failed(self, task_service):
        """When queue submission fails, the DB record must be marked failed."""
        with patch("src.task.service.get_executor") as mock_get_executor:
            from unittest.mock import AsyncMock

            mock_executor = AsyncMock()
            mock_executor.execute.side_effect = ConnectionError("broker unreachable")
            mock_get_executor.return_value = mock_executor

            with pytest.raises(ConnectionError):
                await task_service.submit_task(
                    user_id="user-fail",
                    task_type="workspace_feature",
                    payload={"feature_id": "deep_research"},
                )

        # Verify the task record exists and has failed status
        tasks = await task_service.list_tasks("user-fail")
        assert len(tasks) >= 1
        failed_task = tasks[0]
        assert failed_task["status"] == "failed"
        assert "broker unreachable" in (failed_task.get("error") or "")

    @pytest.mark.asyncio
    async def test_submit_task_enforces_concurrency_limit(self, task_service):
        """Submitting beyond max_concurrent_tasks_per_user raises ConcurrencyLimitError."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            # Submit max_concurrent_tasks_per_user tasks (default 3)
            for i in range(3):
                await task_service.submit_task(
                    user_id="user-limit",
                    task_type="workspace_feature",
                    payload={"feature_id": "deep_research", "index": i},
                )

            # 4th should fail
            with pytest.raises(ConcurrencyLimitError):
                await task_service.submit_task(
                    user_id="user-limit",
                    task_type="workspace_feature",
                    payload={"feature_id": "deep_research", "index": 3},
                )

    @pytest.mark.asyncio
    async def test_submit_task_allows_after_completion(self, task_service):
        """Completed tasks don't count toward concurrency limit."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_ids = []
            for i in range(3):
                tid = await task_service.submit_task(
                    user_id="user-limit2",
                    task_type="workspace_feature",
                    payload={"feature_id": "deep_research", "index": i},
                )
                task_ids.append(tid)

            # Complete one task
            await task_service._store.update_task_record(
                task_ids[0], status="success"
            )

            # Now should allow submitting again
            new_id = await task_service.submit_task(
                user_id="user-limit2",
                task_type="workspace_feature",
                payload={"feature_id": "deep_research", "index": 3},
            )
            assert new_id is not None

    @pytest.mark.asyncio
    async def test_get_task_status_merges_runtime_metadata_for_terminal_tasks(self, task_service):
        """Test completed tasks still expose Redis metadata while the runtime cache exists."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-1", "feature_id": "thesis_writing"},
            )

        await task_service._store.update_task_record(
            task_id,
            status="success",
            progress=100,
            result={"pdf_path": "/tmp/test.pdf"},
        )
        await task_service._store.set_task_state(
            task_id,
            status="success",
            progress=100,
            message="Completed",
            metadata={"current_phase": "export", "pdf_path": "/tmp/test.pdf"},
        )

        status = await task_service.get_task_status(task_id, "user-1")

        assert status is not None
        assert status["status"] == "success"
        assert status["metadata"] == {
            "current_phase": "export",
            "pdf_path": "/tmp/test.pdf",
        }

    @pytest.mark.asyncio
    async def test_get_task_status_falls_back_to_persisted_runtime_state(self, task_service):
        """When Redis runtime state is missing, DB-persisted runtime should still be returned."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-runtime",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-1", "feature_id": "deep_research"},
            )

        runtime = {
            "title": "Deep Research",
            "current_phase": "synthesis",
            "blocks": [{"id": "ideas", "kind": "list", "items": []}],
        }
        await task_service._store.update_task_record(
            task_id,
            status="running",
            progress=72,
            message="Generating ideas",
            runtime_state=runtime,
        )
        await task_service._store.delete_task_state(task_id)

        status = await task_service.get_task_status(task_id, "user-runtime")

        assert status is not None
        assert status["status"] == "running"
        assert status["progress"] == 72
        assert status["message"] == "Generating ideas"
        assert status["metadata"] == {"runtime": runtime}

    @pytest.mark.asyncio
    async def test_find_active_task_by_payload_returns_matching_task(self, task_service):
        """Payload-based dedupe should find the active matching internal task."""
        mock_executor = AsyncMock()

        with patch("src.task.service.get_executor", return_value=mock_executor):
            matching_task_id = await task_service.submit_task(
                user_id="user-dedupe",
                task_type="reference_preprocess",
                payload={
                    "workspace_id": "ws-1",
                    "reference_id": "reference-1",
                    "asset_id": "asset-1",
                },
            )
            await task_service.submit_task(
                user_id="user-dedupe",
                task_type="reference_preprocess",
                payload={
                    "workspace_id": "ws-1",
                    "reference_id": "reference-2",
                    "asset_id": "asset-2",
                },
            )

        found_task_id = await task_service.find_active_task_by_payload(
            user_id="user-dedupe",
            task_type="reference_preprocess",
            payload_filters={
                "workspace_id": "ws-1",
                "reference_id": "reference-1",
                "asset_id": "asset-1",
            },
        )

        assert found_task_id == matching_task_id

    @pytest.mark.asyncio
    async def test_find_active_task_by_payload_ignores_completed_tasks(self, task_service):
        """Completed tasks must not be returned by payload-based dedupe."""
        mock_executor = AsyncMock()

        with patch("src.task.service.get_executor", return_value=mock_executor):
            matching_task_id = await task_service.submit_task(
                user_id="user-dedupe-finished",
                task_type="reference_preprocess",
                payload={
                    "workspace_id": "ws-1",
                    "reference_id": "reference-1",
                    "asset_id": "asset-1",
                },
            )

        await task_service._store.update_task_record(
            matching_task_id,
            status="success",
        )

        found_task_id = await task_service.find_active_task_by_payload(
            user_id="user-dedupe-finished",
            task_type="reference_preprocess",
            payload_filters={
                "workspace_id": "ws-1",
                "reference_id": "reference-1",
                "asset_id": "asset-1",
            },
        )

        assert found_task_id is None

    def test_serialize_task_status_normalizes_non_json_values(self, task_service):
        """Task status serialization should normalize pydantic/datetime payload values."""

        class _ResultPayload(BaseModel):
            artifact: str

        record = MagicMock()
        record.id = "task-x"
        record.execution_session_id = "exec-x"
        record.task_type = "workspace_feature"
        record.status = "running"
        record.progress = 17
        record.message = "working"
        record.result = _ResultPayload(artifact="paper.md")
        record.error = None
        record.workspace_id = "ws-1"
        record.feature_id = "deep_research"
        record.thread_id = "thread-1"
        record.action = None
        record.created_at = datetime(2026, 4, 13, 10, 0, tzinfo=UTC)
        record.started_at = None
        record.completed_at = None
        record.runtime_state = None

        runtime_state = {
            "status": "success",
            "progress": "100",
            "message": "done",
            "current_step": "finalize",
            "metadata": {"finished_at": datetime(2026, 4, 13, 10, 1, tzinfo=UTC)},
        }

        status = task_service._serialize_task_status(record, runtime_state)

        assert status["status"] == "success"
        assert status["progress"] == 100
        assert status["result"] == {"artifact": "paper.md"}
        assert "2026-04-13" in str(status["metadata"]["finished_at"])

    @pytest.mark.asyncio
    async def test_find_active_task_matches_full_workspace_feature_params(self, task_service):
        """Workspace feature dedupe must not collide across different params."""
        mock_executor = AsyncMock()

        with patch("src.task.service.get_executor", return_value=mock_executor):
            first_task_id = await task_service.submit_task(
                user_id="user-feature-dedupe",
                task_type="workspace_feature",
                payload={
                    "workspace_id": "ws-1",
                    "feature_id": "literature_search",
                    "params": {"query": "agent planning", "limit": 10},
                },
            )
            second_task_id = await task_service.submit_task(
                user_id="user-feature-dedupe",
                task_type="workspace_feature",
                payload={
                    "workspace_id": "ws-1",
                    "feature_id": "literature_search",
                    "params": {"query": "multi-agent systems", "limit": 10},
                },
            )

        first_match = await task_service.find_active_task(
            user_id="user-feature-dedupe",
            task_type="workspace_feature",
            workspace_id="ws-1",
            feature_id="literature_search",
            params={"query": "agent planning", "limit": 10},
        )
        second_match = await task_service.find_active_task(
            user_id="user-feature-dedupe",
            task_type="workspace_feature",
            workspace_id="ws-1",
            feature_id="literature_search",
            params={"query": "multi-agent systems", "limit": 10},
        )
        missing_match = await task_service.find_active_task(
            user_id="user-feature-dedupe",
            task_type="workspace_feature",
            workspace_id="ws-1",
            feature_id="literature_search",
            params={"query": "unseen topic", "limit": 10},
        )

        assert first_match == first_task_id
        assert second_match == second_task_id
        assert missing_match is None

    @pytest.mark.asyncio
    async def test_find_active_task_queries_only_active_statuses(self, task_service):
        """Service should constrain dedupe query at SQL layer with active statuses."""
        expected_task = MagicMock()
        expected_task.id = "task-active"
        expected_task.payload = {"params": {"action": "research"}}
        expected_task.status = "pending"
        task_service._store.list_user_tasks = AsyncMock(return_value=[expected_task])

        matched = await task_service.find_active_task(
            user_id="user-1",
            task_type="workspace_feature",
            workspace_id="ws-1",
            feature_id="feature-1",
            action="research",
            params={"action": "research"},
        )

        assert matched == "task-active"
        task_service._store.list_user_tasks.assert_awaited_once()
        kwargs = task_service._store.list_user_tasks.await_args.kwargs
        assert kwargs["status"] == ["pending", "running"]

"""Tests for TaskService."""

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from src.task.service import ConcurrencyLimitError, TaskService
from src.task.store import TaskStore


@pytest_asyncio.fixture
async def task_service(test_session, mock_redis):
    """Create TaskService instance with test fixtures."""
    from tests.task.conftest import FixtureTaskRecord

    store = TaskStore(mock_redis, test_session)
    store._test_model = FixtureTaskRecord
    yield TaskService(store)


class TestTaskService:
    """Tests for TaskService."""

    @pytest.mark.asyncio
    async def test_submit_task(self, task_service):
        """Test submitting a task."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="deep_research",
                payload={"query": "machine learning"},
                priority=5,
            )

            assert task_id is not None
            assert len(task_id) == 36  # UUID format

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
                task_type="literature_search",
                payload={"query": "test"},
            )

            status = await task_service.get_task_status(task_id, "user-1")
            assert status is not None
            assert status["task_type"] == "literature_search"
            assert status["status"] in ("pending", "running")

    @pytest.mark.asyncio
    async def test_get_task_status_wrong_user(self, task_service):
        """Test getting task status with wrong user."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="deep_research",
                payload={},
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
                    task_type="deep_research",
                    payload={"index": i},
                )

            tasks = await task_service.list_tasks("user-list")
            assert len(tasks) >= 3

    @pytest.mark.asyncio
    async def test_queue_failure_marks_record_as_failed(self, task_service):
        """When Celery queue submission fails, the DB record must be marked failed."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task.side_effect = ConnectionError("broker unreachable")

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
                    task_type="deep_research",
                    payload={"index": i},
                )

            # 4th should fail
            with pytest.raises(ConcurrencyLimitError):
                await task_service.submit_task(
                    user_id="user-limit",
                    task_type="deep_research",
                    payload={"index": 3},
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
                    task_type="deep_research",
                    payload={"index": i},
                )
                task_ids.append(tid)

            # Complete one task
            await task_service._store.update_task_record(
                task_ids[0], status="success"
            )

            # Now should allow submitting again
            new_id = await task_service.submit_task(
                user_id="user-limit2",
                task_type="deep_research",
                payload={"index": 3},
            )
            assert new_id is not None

    @pytest.mark.asyncio
    async def test_get_task_status_merges_runtime_metadata_for_terminal_tasks(self, task_service):
        """Test completed tasks still expose Redis metadata while the runtime cache exists."""
        with patch("src.task.service.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock()

            task_id = await task_service.submit_task(
                user_id="user-1",
                task_type="thesis_generation",
                payload={"workspace_id": "ws-1"},
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

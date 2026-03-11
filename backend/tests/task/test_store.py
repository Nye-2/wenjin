"""Tests for TaskStore."""

import pytest
import pytest_asyncio

from src.task.store import TaskStore


@pytest_asyncio.fixture
async def task_store(test_session, mock_redis):
    """Create TaskStore instance with test fixtures."""
    # Import here to avoid circular imports
    from tests.task.conftest import FixtureTaskRecord

    store = TaskStore(mock_redis, test_session)
    # Store reference to test model for queries
    store._test_model = FixtureTaskRecord
    yield store


class TestTaskStoreRedis:
    """Tests for TaskStore Redis operations."""

    @pytest.mark.asyncio
    async def test_set_and_get_task_state(self, task_store):
        """Test setting and getting task state."""
        await task_store.set_task_state(
            "test-task-redis-1",
            status="running",
            progress=30,
            message="Processing...",
        )

        state = await task_store.get_task_state("test-task-redis-1")
        assert state is not None
        assert state["status"] == "running"
        assert state["progress"] == 30

    @pytest.mark.asyncio
    async def test_delete_task_state(self, task_store):
        """Test deleting task state."""
        await task_store.set_task_state("test-task-delete", status="pending")
        await task_store.delete_task_state("test-task-delete")

        state = await task_store.get_task_state("test-task-delete")
        assert state is None


class TestTaskStorePostgres:
    """Tests for TaskStore PostgreSQL operations (using SQLite in tests)."""

    @pytest.mark.asyncio
    async def test_create_task_record(self, task_store):
        """Test creating a task record."""
        record = await task_store.create_task_record(
            task_id="test-task-pg-1",
            user_id="user-1",
            task_type="deep_research",
            priority=5,
            payload={"query": "test"},
        )

        assert record.id == "test-task-pg-1"
        assert record.user_id == "user-1"
        assert record.task_type == "deep_research"
        assert record.status == "pending"

    @pytest.mark.asyncio
    async def test_get_task_record(self, task_store):
        """Test getting a task record."""
        await task_store.create_task_record(
            task_id="test-task-pg-2",
            user_id="user-1",
            task_type="literature_search",
            priority=5,
            payload={},
        )

        record = await task_store.get_task_record("test-task-pg-2")
        assert record is not None
        assert record.task_type == "literature_search"

    @pytest.mark.asyncio
    async def test_update_task_record(self, task_store):
        """Test updating a task record."""
        await task_store.create_task_record(
            task_id="test-task-pg-3",
            user_id="user-1",
            task_type="deep_research",
            priority=5,
            payload={},
        )

        updated = await task_store.update_task_record(
            "test-task-pg-3",
            status="running",
            progress=50,
        )

        assert updated.status == "running"
        assert updated.progress == 50

    @pytest.mark.asyncio
    async def test_list_user_tasks(self, task_store):
        """Test listing user tasks."""
        for i in range(3):
            await task_store.create_task_record(
                task_id=f"test-task-list-{i}",
                user_id="user-list",
                task_type="deep_research",
                priority=5,
                payload={},
            )

        tasks = await task_store.list_user_tasks("user-list")
        assert len(tasks) == 3

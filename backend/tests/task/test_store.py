"""Tests for TaskStore."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from src.dataservice.task_api import TaskDataService
from src.task.store import TaskStore


class _TestTaskDataServiceClient:
    def __init__(self, session, record_model) -> None:
        self._service = TaskDataService(
            session,
            autocommit=True,
            record_model=record_model,
        )
        self.execution_updates: list[tuple[str, object]] = []

    async def create_task_record(self, command):
        return await self._service.create_task_record(**command.model_dump())

    async def create_task_record_guarded(self, command):
        values = command.model_dump()
        return await self._service.create_task_record_guarded(**values)

    async def get_task_record(self, task_id: str):
        return await self._service.get_task_record(task_id)

    async def update_task_record(self, task_id: str, command):
        return await self._service.update_task_record(
            task_id,
            **command.model_dump(exclude_unset=True),
        )

    async def list_user_task_records(
        self,
        *,
        user_id: str,
        status=None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
        feature_id: str | None = None,
        action: str | None = None,
    ):
        return await self._service.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
            workspace_id=workspace_id,
            feature_id=feature_id,
            action=action,
        )

    async def count_active_task_records(self, *, user_id: str, active_statuses: list[str]):
        return await self._service.count_active_tasks(
            user_id=user_id,
            active_statuses=active_statuses,
        )

    async def mark_task_record_started(self, task_id: str, command):
        return await self._service.mark_task_started(
            task_id=task_id,
            started_at=command.started_at,
        )

    async def persist_task_record_runtime_state(self, task_id: str, command):
        return await self._service.persist_runtime_state(
            task_id=task_id,
            runtime_state=command.runtime_state,
        )

    async def mark_task_record_completed(self, task_id: str, command):
        return await self._service.mark_task_completed(
            task_id=task_id,
            **command.model_dump(),
        )

    async def update_execution(self, execution_id: str, command):
        self.execution_updates.append((execution_id, command))
        return None


@pytest_asyncio.fixture
async def task_store(test_session, mock_redis):
    """Create TaskStore instance with test fixtures."""
    # Import here to avoid circular imports
    from tests.task.conftest import FixtureTaskRecord

    store = TaskStore(
        mock_redis,
        test_session,
        dataservice=_TestTaskDataServiceClient(test_session, FixtureTaskRecord),
    )
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

    @pytest.mark.asyncio
    async def test_task_state_metadata_roundtrip(self, task_store):
        """Test task metadata is stored and restored from Redis."""
        metadata = {
            "current_phase": "draft",
            "sections_completed": 2,
        }

        await task_store.set_task_state(
            "test-task-metadata",
            status="running",
            progress=60,
            message="Writing sections",
            metadata=metadata,
        )

        state = await task_store.get_task_state("test-task-metadata")
        assert state is not None
        assert state["metadata"] == metadata


class TestTaskStorePostgres:
    """Tests for TaskStore PostgreSQL operations (using SQLite in tests)."""

    @pytest.mark.asyncio
    async def test_create_task_record(self, task_store):
        """Test creating a task record."""
        record = await task_store.create_task_record(
            task_id="test-task-pg-1",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={"feature_id": "deep_research", "query": "test"},
        )

        assert record.id == "test-task-pg-1"
        assert record.user_id == "user-1"
        assert record.task_type == "execution"
        assert record.status == "pending"

    @pytest.mark.asyncio
    async def test_create_task_record_guarded_enforces_limit(self, task_store):
        """Guarded creation should atomically reject submissions beyond the active-task limit."""
        for index in range(2):
            record, active_count = await task_store.create_task_record_guarded(
                task_id=f"guarded-task-{index}",
                user_id="guarded-user",
                task_type="execution",
                priority=5,
                payload={"feature_id": "deep_research", "index": index},
                concurrency_limit=2,
            )
            assert record is not None
            assert active_count == index

        blocked_record, blocked_count = await task_store.create_task_record_guarded(
            task_id="guarded-task-blocked",
            user_id="guarded-user",
            task_type="execution",
            priority=5,
            payload={"feature_id": "deep_research", "index": 2},
            concurrency_limit=2,
        )

        assert blocked_record is None
        assert blocked_count == 2

    @pytest.mark.asyncio
    async def test_get_task_record(self, task_store):
        """Test getting a task record."""
        await task_store.create_task_record(
            task_id="test-task-pg-2",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={"workspace_id": "ws-1", "feature_id": "literature_search"},
        )

        record = await task_store.get_task_record("test-task-pg-2")
        assert record is not None
        assert record.task_type == "execution"

    @pytest.mark.asyncio
    async def test_update_task_record(self, task_store):
        """Test updating a task record."""
        await task_store.create_task_record(
            task_id="test-task-pg-3",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={"feature_id": "deep_research"},
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
                task_type="execution",
                priority=5,
                payload={"feature_id": "deep_research"},
            )

        tasks = await task_store.list_user_tasks("user-list")
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_user_tasks_supports_multi_status_filter(self, task_store):
        """List API should accept a status list and filter in SQL."""
        await task_store.create_task_record(
            task_id="test-task-status-1",
            user_id="user-status-list",
            task_type="execution",
            priority=5,
            payload={"feature_id": "deep_research"},
        )
        await task_store.create_task_record(
            task_id="test-task-status-2",
            user_id="user-status-list",
            task_type="execution",
            priority=5,
            payload={"feature_id": "deep_research"},
        )
        await task_store.update_task_record("test-task-status-2", status="success")

        active = await task_store.list_user_tasks(
            "user-status-list",
            status=["pending", "running"],
        )

        assert len(active) == 1
        assert active[0].id == "test-task-status-1"

    @pytest.mark.asyncio
    async def test_count_active_tasks(self, task_store):
        """Test counting active (pending/running) tasks for a user."""
        for i in range(3):
            await task_store.create_task_record(
                task_id=f"test-active-{i}",
                user_id="user-active",
                task_type="execution",
                priority=5,
                payload={"feature_id": "deep_research"},
            )
        # First task is completed
        await task_store.update_task_record("test-active-0", status="success")

        count = await task_store.count_active_tasks("user-active")
        assert count == 2  # only pending/running count

    @pytest.mark.asyncio
    async def test_count_active_tasks_empty(self, task_store):
        """No tasks means count is 0."""
        count = await task_store.count_active_tasks("nonexistent-user")
        assert count == 0

    @pytest.mark.asyncio
    async def test_mark_task_completed_preserves_runtime_progress_and_metadata(self, task_store):
        """Test terminal task state keeps the latest runtime details."""
        await task_store.create_task_record(
            task_id="test-task-complete",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={},
        )
        await task_store.set_task_state(
            "test-task-complete",
            status="running",
            progress=80,
            message="Compiling draft",
            metadata={"current_phase": "compile"},
        )

        await task_store.mark_task_completed(
            "test-task-complete",
            success=False,
            error="Compilation failed",
        )

        record = await task_store.get_task_record("test-task-complete")
        state = await task_store.get_task_state("test-task-complete")

        assert record is not None
        assert record.progress == 80
        assert record.message == "Compilation failed"
        assert state is not None
        assert state["progress"] == 80
        assert state["metadata"] == {"current_phase": "compile"}

    @pytest.mark.asyncio
    async def test_mark_task_completed_publishes_canonical_task_activity(
        self,
        task_store,
        monkeypatch: pytest.MonkeyPatch,
    ):
        publish_workspace_event = AsyncMock()
        monkeypatch.setattr("src.task.store.publish_workspace_event", publish_workspace_event)

        await task_store.create_task_record(
            task_id="test-task-event",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={
                "workspace_id": "ws-1",
                "feature_id": "deep_research",
                "params": {"topic": "LLM agents"},
            },
        )
        await task_store.set_task_state(
            "test-task-event",
            status="running",
            progress=55,
            message="Collecting papers",
        )

        await task_store.mark_task_completed(
            "test-task-event",
            success=True,
            result={"refresh_targets": ["artifacts"]},
        )

        first_payload = publish_workspace_event.await_args_list[0].args[2]
        second_payload = publish_workspace_event.await_args_list[1].args[2]
        assert first_payload["activity"]["id"] == "task:test-task-event"
        assert first_payload["activity"]["status"] == "success"
        assert first_payload["activity"]["summary"] == "Collecting papers"
        assert second_payload["refresh_targets"] == ["dashboard", "artifacts"]

    @pytest.mark.asyncio
    async def test_mark_task_completed_derives_artifact_followup_next_actions(
        self,
        task_store,
        monkeypatch: pytest.MonkeyPatch,
    ):
        publish_workspace_event = AsyncMock()
        transition_kwargs: dict[str, object] = {}
        compute_touch = AsyncMock()

        class _FakeExecutionService:
            def __init__(self, db, **kwargs) -> None:
                self.db = db
                self.kwargs = kwargs

            async def apply_task_transition(self, execution_id: str, **kwargs):
                transition_kwargs["execution_id"] = execution_id
                transition_kwargs.update(kwargs)
                return None

        class _FakeComputeSessionService:
            def __init__(self, *args, **kwargs) -> None:
                self.args = args
                self.kwargs = kwargs

            async def touch_session_by_execution(self, execution_id: str):
                await compute_touch(execution_id)

        monkeypatch.setattr("src.task.store.publish_workspace_event", publish_workspace_event)
        monkeypatch.setattr("src.task.store.ExecutionService", _FakeExecutionService)
        monkeypatch.setattr(
            "src.compute.session_service.ComputeSessionService",
            _FakeComputeSessionService,
        )

        await task_store.create_task_record(
            task_id="test-task-followup-actions",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={
                "workspace_id": "ws-1",
                "feature_id": "framework_outline",
                "execution_id": "exec-1",
                "skill_id": "framework-designer",
                "params": {"topic": "LLM planning"},
            },
        )

        await task_store.mark_task_completed(
            "test-task-followup-actions",
            success=True,
            result={
                "artifact_ids": ["artifact-current"],
                "artifacts": [{"id": "artifact-current", "title": "LLM Framework"}],
            },
        )

        next_actions = transition_kwargs["next_actions"]
        assert transition_kwargs["execution_id"] == "exec-1"
        assert isinstance(next_actions, list)
        assert {
            (item.get("action"), item.get("artifact_id"), item.get("title"))
            for item in next_actions
            if isinstance(item, dict)
        } >= {
            ("open_artifact", "artifact-current", "LLM Framework"),
        }
        assert {
            (
                item.get("action"),
                item.get("feature_id"),
                item.get("source_artifact_id"),
                tuple(item.get("context_artifact_ids") or []),
                item.get("topic"),
                item.get("skill_id"),
            )
            for item in next_actions
            if isinstance(item, dict)
        } >= {
            (
                "rerun_from_artifact",
                "framework_outline",
                "artifact-current",
                ("artifact-current",),
                "LLM planning",
                "framework-designer",
            ),
        }
        compute_touch.assert_awaited_once_with("exec-1")

    @pytest.mark.asyncio
    async def test_mark_task_started_publishes_running_activity(
        self,
        task_store,
        monkeypatch: pytest.MonkeyPatch,
    ):
        publish_workspace_event = AsyncMock()
        monkeypatch.setattr("src.task.store.publish_workspace_event", publish_workspace_event)

        await task_store.create_task_record(
            task_id="test-task-started",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={
                "workspace_id": "ws-1",
                "feature_id": "framework_outline",
                "thread_id": "thread-1",
            },
        )

        await task_store.mark_task_started("test-task-started", worker_id="worker-1")

        payload = publish_workspace_event.await_args.args[2]
        assert payload["task"]["status"] == "running"
        assert payload["activity"]["id"] == "task:test-task-started"
        assert payload["activity"]["status"] == "running"
        assert payload["activity"]["feature_id"] == "framework_outline"

    @pytest.mark.asyncio
    async def test_persist_runtime_state_writes_runtime_to_record(self, task_store):
        """Stage-bound runtime state should be persisted on the task record."""
        await task_store.create_task_record(
            task_id="test-task-runtime",
            user_id="user-1",
            task_type="execution",
            priority=5,
            payload={},
        )

        runtime = {
            "title": "Deep Research",
            "current_phase": "discovery",
            "blocks": [{"id": "papers", "kind": "list", "items": []}],
        }
        await task_store.persist_runtime_state(
            "test-task-runtime",
            {"runtime": runtime},
        )

        record = await task_store.get_task_record("test-task-runtime")
        assert record is not None
        assert record.runtime_state == runtime

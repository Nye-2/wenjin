"""Task service for task management operations."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from src.config.app_config import celery_settings
from src.config.task_config import task_settings
from src.task import celery_app
from src.task.executor import cancel_local_task, get_executor
from src.task.registry import TaskStatus, get_task_config, is_valid_task_type
from src.task.store import TaskStore
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)


class ConcurrencyLimitError(Exception):
    """Raised when a user exceeds the maximum concurrent task limit."""

    def __init__(self, current: int, limit: int) -> None:
        self.current = current
        self.limit = limit
        super().__init__(
            f"Concurrent task limit reached: {current}/{limit} active tasks"
        )


class TaskService:
    """Service for task management."""

    def __init__(self, store: TaskStore):
        self._store = store

    def _serialize_task_status(self, record, runtime_state: dict | None = None) -> dict:
        """Merge persisted task data with runtime state."""
        status = runtime_state.get("status", record.status) if runtime_state else record.status
        progress = runtime_state.get("progress", record.progress) if runtime_state else record.progress
        message = runtime_state.get("message", record.message) if runtime_state else record.message
        persisted_runtime = getattr(record, "runtime_state", None)
        if runtime_state and runtime_state.get("metadata") is not None:
            metadata = runtime_state.get("metadata")
        elif persisted_runtime is not None:
            metadata = {"runtime": persisted_runtime}
        else:
            metadata = None

        return {
            "task_id": record.id,
            "task_type": record.task_type,
            "status": status,
            "progress": progress,
            "message": message,
            "result": record.result,
            "error": record.error,
            "metadata": metadata,
            "created_at": record.created_at.isoformat(),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

    @staticmethod
    def _workspace_id_from_payload(payload: dict | None) -> str | None:
        """Extract workspace id from a task payload if present."""
        if not isinstance(payload, dict):
            return None
        workspace_id = payload.get("workspace_id")
        return str(workspace_id) if workspace_id else None

    async def submit_task(
        self,
        user_id: str,
        task_type: str,
        payload: dict,
        priority: int = 5,
    ) -> str:
        """Submit a new task.

        Args:
            user_id: User submitting the task
            task_type: Type of task (must be registered)
            payload: Task-specific parameters
            priority: Task priority (1-10, lower = higher priority)

        Returns:
            Task ID

        Raises:
            ValueError: If task_type is invalid
        """
        if not is_valid_task_type(task_type):
            raise ValueError(f"Unknown task type: {task_type}")

        # Enforce per-user concurrency limit
        # NOTE: TOCTOU window exists between count and insert. For strict
        # guarantees under high concurrency, consider a Redis atomic counter
        # or PostgreSQL advisory lock. Current DB-based check is sufficient
        # for the expected low-concurrency per-user workload.
        active_count = await self._store.count_active_tasks(user_id)
        limit = task_settings.max_concurrent_tasks_per_user
        if active_count >= limit:
            raise ConcurrencyLimitError(current=active_count, limit=limit)

        # Validate priority
        priority = max(1, min(10, priority))

        # Generate task ID
        task_id = str(uuid4())

        # Create database record
        await self._store.create_task_record(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            priority=priority,
            payload=payload,
        )

        # Get task config
        config = get_task_config(task_type)

        # Submit via executor (Celery or local depending on config)
        try:
            executor = get_executor()
            await executor.execute(
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                queue=config.queue if config else "default",
                priority=10 - priority,  # Celery uses inverse priority
            )
        except Exception as exc:
            logger.error(
                "Task submission failed for task %s: %s", task_id, exc
            )
            await self._store.update_task_record(
                task_id,
                status=TaskStatus.FAILED.value,
                error=f"Task submission failed: {exc}",
            )
            raise

        logger.info(f"Task submitted: {task_id} type={task_type} user={user_id}")

        workspace_id = self._workspace_id_from_payload(payload)
        await publish_workspace_event(
            workspace_id,
            "task.updated",
            {
                "task": {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": TaskStatus.PENDING.value,
                    "progress": 0,
                    "message": None,
                    "feature_id": payload.get("feature_id") if isinstance(payload, dict) else None,
                    "thread_id": payload.get("thread_id") if isinstance(payload, dict) else None,
                    "metadata": None,
                }
            },
        )
        await publish_workspace_event(
            workspace_id,
            "workspace.refresh",
            {"refresh_targets": ["activity", "dashboard"]},
        )

        return task_id

    async def find_active_task(
        self,
        user_id: str,
        task_type: str,
        workspace_id: str,
        feature_id: str,
        action: str | None = None,
    ) -> str | None:
        """Find an active (pending/running) task for the same context.

        Returns task_id if found, None otherwise.
        """
        records = await self._store.list_user_tasks(
            user_id=user_id,
            task_type=task_type,
            status=None,
            limit=50,
        )
        active_statuses = {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}
        for record in records:
            if record.status not in active_statuses:
                continue
            payload = record.payload or {}
            if (
                payload.get("workspace_id") == workspace_id
                and payload.get("feature_id") == feature_id
            ):
                payload_action = (payload.get("params") or {}).get("action")
                if payload_action == action:
                    return record.id
        return None

    async def get_task_status(self, task_id: str, user_id: str) -> dict | None:
        """Get task status.

        Args:
            task_id: Task ID
            user_id: User ID (for access control)

        Returns:
            Task status dict or None if not found/not authorized
        """
        # Check database record
        record = await self._store.get_task_record(task_id)
        if not record:
            return None

        # Access control
        if record.user_id != user_id:
            return None

        runtime_state = await self._store.get_task_state(task_id)
        return self._serialize_task_status(record, runtime_state)

    async def list_tasks(
        self,
        user_id: str,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List tasks for a user."""
        records = await self._store.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
        )
        serialized: list[dict] = []
        for record in records:
            runtime_state = await self._store.get_task_state(record.id)
            serialized.append(self._serialize_task_status(record, runtime_state))
        return serialized

    async def list_task_records(
        self,
        user_id: str,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list:
        """List persisted task records for a user."""
        return await self._store.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
        )

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """Cancel a task.

        Args:
            task_id: Task ID
            user_id: User ID (for access control)

        Returns:
            True if cancelled, False if not found/not authorized
        """
        record = await self._store.get_task_record(task_id)
        if not record or record.user_id != user_id:
            return False

        # Can only cancel pending or running tasks
        if record.status not in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value):
            return False

        # Cancel backend task
        if celery_settings.enabled:
            celery_app.control.revoke(task_id, terminate=True)
        else:
            if not cancel_local_task(task_id):
                logger.warning("Local task %s not found or already finished", task_id)
                return False

        # Update database
        await self._store.update_task_record(
            task_id,
            status=TaskStatus.CANCELLED.value,
            completed_at=datetime.now(UTC),
        )
        await self._store.set_task_state(task_id, TaskStatus.CANCELLED.value, message="Cancelled by user")

        payload = record.payload if isinstance(record.payload, dict) else {}
        workspace_id = self._workspace_id_from_payload(payload)
        await publish_workspace_event(
            workspace_id,
            "task.updated",
            {
                "task": {
                    "task_id": task_id,
                    "task_type": record.task_type,
                    "status": TaskStatus.CANCELLED.value,
                    "progress": 0,
                    "message": "Cancelled by user",
                    "feature_id": payload.get("feature_id"),
                    "thread_id": payload.get("thread_id"),
                    "metadata": None,
                }
            },
        )
        await publish_workspace_event(
            workspace_id,
            "workspace.refresh",
            {"refresh_targets": ["activity", "dashboard"]},
        )

        logger.info(f"Task cancelled: {task_id}")

        return True

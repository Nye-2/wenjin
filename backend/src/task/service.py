"""Task service for task management operations."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TypeAlias, cast
from uuid import uuid4

from src.config.app_config import celery_settings
from src.config.task_config import task_settings
from src.services.workspace_activity_contracts import (
    build_task_activity_item,
    serialize_activity_item,
)
from src.task import celery_app
from src.task.executor import cancel_local_task, get_executor
from src.task.registry import TaskStatus, get_task_config, is_valid_task_type
from src.task.store import TaskStore
from src.task.workspace_feature_params import coerce_workspace_feature_params
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)

JsonObject: TypeAlias = dict[str, Any]


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

    def _serialize_task_status(
        self,
        record: Any,
        runtime_state: JsonObject | None = None,
    ) -> JsonObject:
        """Merge persisted task data with runtime state."""
        status = runtime_state.get("status", record.status) if runtime_state else record.status
        progress = runtime_state.get("progress", record.progress) if runtime_state else record.progress
        message = runtime_state.get("message", record.message) if runtime_state else record.message
        current_step = runtime_state.get("current_step") if runtime_state else None
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
            "current_step": current_step,
            "result": record.result,
            "error": record.error,
            "metadata": metadata,
            "workspace_id": record.workspace_id,
            "feature_id": record.feature_id,
            "thread_id": record.thread_id,
            "action": record.action,
            "created_at": record.created_at.isoformat(),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

    @staticmethod
    def _workspace_id_from_payload(payload: JsonObject | None) -> str | None:
        """Extract workspace id from a task payload if present."""
        if not isinstance(payload, dict):
            return None
        workspace_id = payload.get("workspace_id")
        return str(workspace_id) if workspace_id else None

    @classmethod
    def _normalize_params(cls, value: Any) -> Any:
        """Normalize nested params for stable equality checks."""
        if isinstance(value, Mapping):
            return {
                str(key): cls._normalize_params(item)
                for key, item in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, tuple):
            return [cls._normalize_params(item) for item in value]
        if isinstance(value, list):
            return [cls._normalize_params(item) for item in value]
        return value

    async def submit_task(
        self,
        user_id: str,
        task_type: str,
        payload: JsonObject,
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

        # Validate priority
        priority = max(1, min(10, priority))

        # Generate task ID
        task_id = str(uuid4())

        limit = task_settings.max_concurrent_tasks_per_user
        record, active_count = await self._store.create_task_record_guarded(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            priority=priority,
            payload=payload,
            concurrency_limit=limit,
        )
        if record is None:
            raise ConcurrencyLimitError(current=active_count, limit=limit)

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
            }
            | (
                {
                    "activity": serialize_activity_item(
                        build_task_activity_item(
                            task_id=task_id,
                            workspace_id=workspace_id,
                            task_type=task_type,
                            payload=payload if isinstance(payload, dict) else None,
                            status=TaskStatus.PENDING.value,
                            progress=0,
                            message=None,
                            error=None,
                            occurred_at=record.created_at,
                            created_at=record.created_at,
                        )
                    )
                }
                if workspace_id
                else {}
            ),
        )
        await publish_workspace_event(
            workspace_id,
            "workspace.refresh",
            {"refresh_targets": ["dashboard"]},
        )

        return task_id

    async def find_active_task(
        self,
        user_id: str,
        task_type: str,
        workspace_id: str,
        feature_id: str,
        action: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str | None:
        """Find an active (pending/running) task for the same context.

        Returns task_id if found, None otherwise.
        """
        records = await self._store.list_user_tasks(
            user_id=user_id,
            task_type=task_type,
            status=None,
            limit=50,
            workspace_id=workspace_id,
            feature_id=feature_id,
            action=action,
        )
        active_statuses = {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}
        for record in records:
            if record.status not in active_statuses:
                continue
            payload = record.payload or {}
            if not isinstance(payload, dict):
                continue
            payload_params = coerce_workspace_feature_params(payload)
            if params is not None:
                if self._normalize_params(payload_params) == self._normalize_params(params):
                    return record.id
                continue
            payload_action = payload_params.get("action")
            if payload_action == action:
                return record.id
        return None

    async def find_active_task_by_payload(
        self,
        *,
        user_id: str,
        task_type: str,
        payload_filters: JsonObject,
        limit: int = 50,
    ) -> str | None:
        """Find an active task whose payload matches the provided key/value filters."""
        records = await self._store.list_user_tasks(
            user_id=user_id,
            task_type=task_type,
            status=None,
            limit=limit,
        )
        active_statuses = {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}
        for record in records:
            if record.status not in active_statuses:
                continue
            payload = record.payload or {}
            if not isinstance(payload, dict):
                continue
            if all(payload.get(key) == value for key, value in payload_filters.items()):
                return record.id
        return None

    async def get_task_status(
        self,
        task_id: str,
        user_id: str,
    ) -> JsonObject | None:
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
        workspace_id: str | None = None,
        feature_id: str | None = None,
        action: str | None = None,
    ) -> list[JsonObject]:
        """List tasks for a user."""
        records = await self._store.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
            workspace_id=workspace_id,
            feature_id=feature_id,
            action=action,
        )
        serialized: list[JsonObject] = []
        for record in records:
            runtime_state = await self._store.get_task_state(record.id)
            serialized.append(self._serialize_task_status(record, runtime_state))
        return serialized

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
            cast(Any, celery_app).control.revoke(task_id, terminate=True)
        else:
            if not cancel_local_task(task_id):
                logger.warning("Local task %s not found or already finished", task_id)
                return False

        cancelled_at = datetime.now(UTC)
        # Update database
        await self._store.update_task_record(
            task_id,
            status=TaskStatus.CANCELLED.value,
            completed_at=cancelled_at,
        )
        await self._store.set_task_state(task_id, TaskStatus.CANCELLED.value, message="Cancelled by user")

        # Attempt credit refund if credits were consumed for this task
        await self._refund_cancelled_task(user_id, record)

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
            }
            | (
                {
                    "activity": serialize_activity_item(
                        build_task_activity_item(
                            task_id=task_id,
                            workspace_id=workspace_id,
                            task_type=record.task_type,
                            payload=payload,
                            status=TaskStatus.CANCELLED.value,
                            progress=0,
                            message="Cancelled by user",
                            error=None,
                            occurred_at=cancelled_at,
                            created_at=record.created_at,
                            started_at=record.started_at,
                            completed_at=cancelled_at,
                        )
                    )
                }
                if workspace_id
                else {}
            ),
        )
        await publish_workspace_event(
            workspace_id,
            "workspace.refresh",
            {"refresh_targets": ["dashboard"]},
        )

        logger.info(f"Task cancelled: {task_id}")

        return True

    async def _refund_cancelled_task(self, user_id: str, record: Any) -> None:
        """Refund credits consumed for a cancelled task."""
        payload = record.payload if isinstance(record.payload, dict) else {}
        credit_transaction_id = payload.get("credit_transaction_id")
        if not credit_transaction_id:
            return

        try:
            from src.database import get_db_session
            from src.services.credit_service import CreditService

            async with get_db_session() as db:
                credit_service = CreditService(db)
                await credit_service.refund_consumption(
                    user_id=user_id,
                    original_transaction_id=str(credit_transaction_id),
                    reason="任务取消退款",
                    task_id=record.id,
                )
                logger.info(
                    "Refunded credits for cancelled task %s (tx %s)",
                    record.id,
                    credit_transaction_id,
                )
        except Exception:
            logger.warning(
                "Failed to refund credits for cancelled task %s",
                record.id,
                exc_info=True,
            )

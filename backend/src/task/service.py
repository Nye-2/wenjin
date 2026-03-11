"""Task service for task management operations."""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from celery.result import AsyncResult

from src.config.task_config import task_settings
from src.task import celery_app
from src.task.registry import get_task_config, is_valid_task_type
from src.task.store import TaskStore

logger = logging.getLogger(__name__)


class TaskService:
    """Service for task management."""

    def __init__(self, store: TaskStore):
        self._store = store

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

        # Submit to Celery
        celery_app.send_task(
            "src.task.tasks.execute_task",
            args=[task_id, task_type, payload],
            queue=config.queue if config else "default",
            priority=10 - priority,  # Celery uses inverse priority
            task_id=task_id,
        )

        logger.info(f"Task submitted: {task_id} type={task_type} user={user_id}")

        return task_id

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

        # Get runtime state from Redis for running tasks
        if record.status in ("pending", "running"):
            runtime_state = await self._store.get_task_state(task_id)
            if runtime_state:
                return {
                    "task_id": task_id,
                    "task_type": record.task_type,
                    "status": runtime_state.get("status", record.status),
                    "progress": runtime_state.get("progress", 0),
                    "message": runtime_state.get("message", ""),
                    "created_at": record.created_at.isoformat(),
                    "started_at": record.started_at.isoformat() if record.started_at else None,
                }

        return {
            "task_id": task_id,
            "task_type": record.task_type,
            "status": record.status,
            "progress": record.progress,
            "message": record.message,
            "result": record.result,
            "error": record.error,
            "created_at": record.created_at.isoformat(),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

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
        return [
            {
                "task_id": r.id,
                "task_type": r.task_type,
                "status": r.status,
                "progress": r.progress,
                "message": r.message,
                "created_at": r.created_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in records
        ]

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
        if record.status not in ("pending", "running"):
            return False

        # Revoke Celery task
        celery_app.control.revoke(task_id, terminate=True)

        # Update database
        await self._store.update_task_record(
            task_id,
            status="cancelled",
            completed_at=datetime.now(timezone.utc),
        )
        await self._store.set_task_state(task_id, "cancelled", message="Cancelled by user")

        logger.info(f"Task cancelled: {task_id}")

        return True

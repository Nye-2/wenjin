"""Progress tracking for tasks."""

import json
import logging
from datetime import datetime, timezone

from src.task.registry import TaskStatus

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Tracks and broadcasts task progress."""

    def __init__(self, redis_client, task_id: str):
        self._redis = redis_client
        self._task_id = task_id

    def _channel_name(self) -> str:
        """Redis pub/sub channel for this task."""
        return f"task_progress:{self._task_id}"

    async def update(
        self,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Update progress and broadcast to subscribers.

        Args:
            progress: Progress percentage (0-100)
            message: Human-readable status message
            current_step: Identifier for current step
        """
        progress = max(0, min(100, progress))

        # Update Redis state
        from src.task.store import TaskStore
        from src.database import get_db_session
        async with get_db_session() as db:
            store = TaskStore(self._redis, db)
            await store.set_task_state(
                self._task_id,
                status=TaskStatus.RUNNING.value,
                progress=progress,
                message=message,
                current_step=current_step,
                metadata=metadata,
            )
            await store.update_task_record(
                self._task_id,
                status=TaskStatus.RUNNING.value,
                progress=progress,
                message=message,
            )

        # Broadcast to SSE subscribers
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "running",
            "progress": progress,
            "message": message,
            "current_step": current_step,
            "metadata": metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)

        logger.debug(f"Task {self._task_id}: {progress}% - {message}")

    async def complete(self, message: str = "Task completed", metadata: dict | None = None) -> None:
        """Mark task as completed."""
        # Update state and broadcast in one operation
        from src.task.store import TaskStore
        from src.database import get_db_session

        async with get_db_session() as db:
            store = TaskStore(self._redis, db)
            runtime_state = await store.get_task_state(self._task_id)
            resolved_metadata = (
                metadata
                if metadata is not None
                else runtime_state.get("metadata") if runtime_state else None
            )
            await store.set_task_state(
                self._task_id,
                status=TaskStatus.SUCCESS.value,
                progress=100,
                message=message,
                metadata=resolved_metadata,
            )
            await store.update_task_record(
                self._task_id,
                status=TaskStatus.SUCCESS.value,
                progress=100,
                message=message,
            )

        # Broadcast completion (single broadcast)
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": TaskStatus.SUCCESS.value,
            "progress": 100,
            "message": message,
            "metadata": resolved_metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)

    async def fail(self, error: str, metadata: dict | None = None) -> None:
        """Mark task as failed."""
        from src.task.store import TaskStore
        from src.database import get_db_session

        async with get_db_session() as db:
            store = TaskStore(self._redis, db)
            runtime_state = await store.get_task_state(self._task_id)
            final_progress = runtime_state.get("progress", 0) if runtime_state else 0
            resolved_metadata = (
                metadata
                if metadata is not None
                else runtime_state.get("metadata") if runtime_state else None
            )
            await store.set_task_state(
                self._task_id,
                status=TaskStatus.FAILED.value,
                progress=final_progress,
                message=error,
                metadata=resolved_metadata,
            )
            await store.update_task_record(
                self._task_id,
                status=TaskStatus.FAILED.value,
                progress=final_progress,
                message=error,
            )

        event_data = json.dumps({
            "task_id": self._task_id,
            "status": TaskStatus.FAILED.value,
            "progress": final_progress,
            "message": error,
            "metadata": resolved_metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)


def get_progress_tracker(task_id: str) -> ProgressTracker:
    """Get a progress tracker for a task."""
    from src.academic.cache.redis_client import redis_client
    return ProgressTracker(redis_client, task_id)

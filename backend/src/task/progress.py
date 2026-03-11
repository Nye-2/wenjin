"""Progress tracking for tasks."""

import json
import logging
from datetime import datetime, timezone

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
        from src.academic.cache.redis_client import redis_client

        async with get_db_session() as db:
            store = TaskStore(redis_client, db)
            await store.set_task_state(
                self._task_id,
                status="running",
                progress=progress,
                message=message,
                current_step=current_step,
            )

        # Broadcast to SSE subscribers
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "running",
            "progress": progress,
            "message": message,
            "current_step": current_step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)

        logger.debug(f"Task {self._task_id}: {progress}% - {message}")

    async def complete(self, message: str = "Task completed") -> None:
        """Mark task as completed."""
        await self.update(100, message)

        # Broadcast completion
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "success",
            "progress": 100,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)

    async def fail(self, error: str) -> None:
        """Mark task as failed."""
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": "failed",
            "progress": 0,
            "message": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._redis.client.publish(self._channel_name(), event_data)


def get_progress_tracker(task_id: str) -> ProgressTracker:
    """Get a progress tracker for a task."""
    from src.academic.cache.redis_client import redis_client
    return ProgressTracker(redis_client, task_id)

"""Progress tracking for tasks.

Write strategy (Phase 3 optimization):
- update(): Redis + Pub/Sub only (no DB write by default)
- update(stage_transition=True): Redis + Pub/Sub + DB flush
- complete(): Redis + Pub/Sub only (mark_task_completed handles DB)
- fail(): Redis + Pub/Sub only (mark_task_completed handles DB)
"""

import json
import logging
from datetime import UTC, datetime

from src.config.task_config import task_settings
from src.task.registry import TaskStatus

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Tracks and broadcasts task progress.

    High-frequency updates write only to Redis and Pub/Sub.
    DB writes happen only on stage transitions (explicit opt-in) or
    via ``TaskStore.mark_task_completed`` for terminal states.
    """

    def __init__(self, redis_client, task_id: str):
        self._redis = redis_client
        self._task_id = task_id

    def _task_key(self) -> str:
        return f"task:{self._task_id}"

    def _channel_name(self) -> str:
        """Redis pub/sub channel for this task."""
        return f"task_progress:{self._task_id}"

    async def _set_redis_state(
        self,
        status: str,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
        metadata: dict | None = None,
        *,
        now: str | None = None,
    ) -> None:
        """Write task state to Redis hash."""
        key = self._task_key()
        ts = now or datetime.now(UTC).isoformat()
        data = {
            "status": status,
            "progress": str(progress),
            "message": message or "",
            "current_step": current_step or "",
            "updated_at": ts,
        }
        if metadata is not None:
            data["metadata"] = json.dumps(metadata, ensure_ascii=False)
        await self._redis.client.hset(key, mapping=data)
        await self._redis.client.expire(key, task_settings.task_redis_ttl)

    async def _publish_event(
        self,
        status: str,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
        metadata: dict | None = None,
        *,
        now: str | None = None,
    ) -> None:
        """Publish progress event to Pub/Sub subscribers."""
        ts = now or datetime.now(UTC).isoformat()
        event_data = json.dumps({
            "task_id": self._task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "current_step": current_step,
            "metadata": metadata,
            "timestamp": ts,
        })
        await self._redis.client.publish(self._channel_name(), event_data)

    async def update(
        self,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
        metadata: dict | None = None,
        *,
        stage_transition: bool = False,
    ) -> None:
        """Update progress and broadcast to subscribers.

        By default writes **only** to Redis + Pub/Sub.  Set
        ``stage_transition=True`` to also flush the current progress to
        the database (for stage boundaries that should survive a crash).

        Args:
            progress: Progress percentage (0-100)
            message: Human-readable status message
            current_step: Identifier for current step
            metadata: Optional metadata dict
            stage_transition: If True, also write to DB
        """
        progress = max(0, min(100, progress))
        ts = datetime.now(UTC).isoformat()

        # Redis + Pub/Sub (always)
        await self._set_redis_state(
            status=TaskStatus.RUNNING.value,
            progress=progress,
            message=message,
            current_step=current_step,
            metadata=metadata,
            now=ts,
        )
        await self._publish_event(
            status=TaskStatus.RUNNING.value,
            progress=progress,
            message=message,
            current_step=current_step,
            metadata=metadata,
            now=ts,
        )

        # DB flush (only on stage transitions)
        if stage_transition:
            from src.database import get_db_session
            from src.task.store import TaskStore

            async with get_db_session() as db:
                store = TaskStore(self._redis, db)
                await store.update_task_record(
                    self._task_id,
                    status=TaskStatus.RUNNING.value,
                    progress=progress,
                    message=message,
                )

        logger.debug(f"Task {self._task_id}: {progress}% - {message}")

    async def complete(self, message: str = "Task completed", metadata: dict | None = None) -> None:
        """Mark task as completed in Redis + Pub/Sub.

        DB update is handled by ``TaskStore.mark_task_completed()``.
        """
        ts = datetime.now(UTC).isoformat()
        await self._set_redis_state(
            status=TaskStatus.SUCCESS.value,
            progress=100,
            message=message,
            metadata=metadata,
            now=ts,
        )
        await self._publish_event(
            status=TaskStatus.SUCCESS.value,
            progress=100,
            message=message,
            metadata=metadata,
            now=ts,
        )

    async def fail(self, error: str, metadata: dict | None = None) -> None:
        """Mark task as failed in Redis + Pub/Sub.

        DB update is handled by ``TaskStore.mark_task_completed()``.
        """
        # Preserve the current progress from Redis
        state = await self._redis.client.hgetall(self._task_key())
        final_progress = int(state.get("progress", 0)) if state else 0
        ts = datetime.now(UTC).isoformat()

        await self._set_redis_state(
            status=TaskStatus.FAILED.value,
            progress=final_progress,
            message=error,
            metadata=metadata,
            now=ts,
        )
        await self._publish_event(
            status=TaskStatus.FAILED.value,
            progress=final_progress,
            message=error,
            metadata=metadata,
            now=ts,
        )


def get_progress_tracker(task_id: str) -> ProgressTracker:
    """Get a progress tracker for a task."""
    from src.academic.cache.redis_client import redis_client
    return ProgressTracker(redis_client, task_id)

"""Progress tracking for tasks.

Write strategy (Phase 3 optimization):
- update(): Redis + Pub/Sub only (no DB write by default)
- update(stage_transition=True): Redis + Pub/Sub + DB flush
- complete(): Redis + Pub/Sub only (mark_task_completed handles DB)
- fail(): Redis + Pub/Sub only (mark_task_completed handles DB)
"""

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from src.config.task_config import task_settings
from src.services.workspace_activity_contracts import (
    build_task_activity_item,
    serialize_activity_item,
)
from src.task.registry import TaskStatus

logger = logging.getLogger(__name__)

_CURRENT_PROGRESS_TRACKER: ContextVar["ProgressTracker | None"] = ContextVar(
    "current_progress_tracker",
    default=None,
)
_CURRENT_RUNTIME_STATE: ContextVar[dict[str, Any] | None] = ContextVar(
    "current_runtime_state",
    default=None,
)


class ProgressTracker:
    """Tracks and broadcasts task progress.

    High-frequency updates write only to Redis and Pub/Sub.
    DB writes happen only on stage transitions (explicit opt-in) or
    via ``TaskStore.mark_task_completed`` for terminal states.
    """

    def __init__(
        self,
        redis_client: Any,
        task_id: str,
        *,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        task_type: str | None = None,
        feature_id: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._task_id = task_id
        self._workspace_id = workspace_id
        self._thread_id = thread_id
        self._task_type = task_type
        self._feature_id = feature_id

    def _task_key(self) -> str:
        return f"task:{self._task_id}"

    def _channel_name(self) -> str:
        """Redis pub/sub channel for this task."""
        return f"task_progress:{self._task_id}"

    def _build_activity_payload(
        self,
        *,
        status: str,
        progress: int,
        message: str | None,
        metadata: dict[str, Any] | None,
        occurred_at: str,
    ) -> dict[str, object] | None:
        if not self._workspace_id:
            return None

        payload: dict[str, object] = {}
        if self._feature_id:
            payload["feature_id"] = self._feature_id
        if self._thread_id:
            payload["thread_id"] = self._thread_id

        return serialize_activity_item(
            build_task_activity_item(
                task_id=self._task_id,
                workspace_id=self._workspace_id,
                task_type=self._task_type,
                payload=payload,
                status=status,
                progress=progress,
                message=message,
                error=None,
                occurred_at=occurred_at,
            )
        )

    async def _set_redis_state(
        self,
        status: str,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
        metadata: dict[str, Any] | None = None,
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
        metadata: dict[str, Any] | None = None,
        *,
        now: str | None = None,
    ) -> None:
        """Publish progress event to Pub/Sub subscribers."""
        ts = now or datetime.now(UTC).isoformat()
        event_payload = {
            "task_id": self._task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "current_step": current_step,
            "metadata": metadata,
            "timestamp": ts,
        }
        event_data = json.dumps(event_payload)
        await self._redis.client.publish(self._channel_name(), event_data)

        if self._workspace_id and status == TaskStatus.RUNNING.value:
            from src.workspace_events import publish_workspace_event

            await publish_workspace_event(
                self._workspace_id,
                "task.updated",
                {
                    "task": {
                        "task_id": self._task_id,
                        "task_type": self._task_type,
                        "status": status,
                        "progress": progress,
                        "message": message,
                        "current_step": current_step,
                        "feature_id": self._feature_id,
                        "thread_id": self._thread_id,
                        "metadata": metadata,
                    }
                }
                | {
                    "activity": self._build_activity_payload(
                        status=status,
                        progress=progress,
                        message=message,
                        metadata=metadata,
                        occurred_at=ts,
                    )
                },
            )

    async def update(
        self,
        progress: int,
        message: str | None = None,
        current_step: str | None = None,
        metadata: dict[str, Any] | None = None,
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
                await store.persist_runtime_state(self._task_id, metadata)

        logger.debug(f"Task {self._task_id}: {progress}% - {message}")

    async def complete(self, message: str = "Task completed", metadata: dict[str, Any] | None = None) -> None:
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

    async def fail(self, error: str, metadata: dict[str, Any] | None = None) -> None:
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


def bind_progress_tracker(progress: ProgressTracker) -> Token[ProgressTracker | None]:
    """Bind the current progress tracker for nested service/graph helpers."""
    return _CURRENT_PROGRESS_TRACKER.set(progress)


def reset_progress_tracker(token: Token[ProgressTracker | None]) -> None:
    """Reset the current bound progress tracker."""
    _CURRENT_PROGRESS_TRACKER.reset(token)


def bind_runtime_state(runtime: dict[str, Any]) -> Token[dict[str, Any] | None]:
    """Bind the current mutable runtime state for nested helpers."""
    return _CURRENT_RUNTIME_STATE.set(runtime)


def reset_runtime_state(token: Token[dict[str, Any] | None]) -> None:
    """Reset the current bound runtime state."""
    _CURRENT_RUNTIME_STATE.reset(token)


def get_runtime_state() -> dict[str, Any] | None:
    """Return the currently bound runtime state."""
    return _CURRENT_RUNTIME_STATE.get()


async def emit_runtime_update(
    *,
    progress_value: int,
    message: str,
    current_phase: str | None = None,
    runtime: dict[str, Any] | None = None,
    stage_transition: bool = False,
) -> None:
    """Emit a structured runtime update using the currently bound tracker."""
    tracker = _CURRENT_PROGRESS_TRACKER.get()
    if tracker is None:
        return

    metadata = {"runtime": runtime} if runtime is not None else None
    await tracker.update(
        progress_value,
        message,
        current_step=current_phase,
        metadata=metadata,
        stage_transition=stage_transition,
    )


def get_progress_tracker(task_id: str) -> ProgressTracker:
    """Get a progress tracker for a task."""
    from src.academic.cache.redis_client import redis_client
    return ProgressTracker(redis_client, task_id)

"""Startup reconciliation helpers for interrupted task state."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from src.academic.cache.redis_client import redis_client
from src.config.app_config import celery_settings
from src.database import async_session_factory
from src.database.models.task import TaskRecord
from src.task.registry import TaskStatus
from src.task.store import TaskStore

logger = logging.getLogger(__name__)

_LOCAL_EXECUTOR_INTERRUPTED_MESSAGE = (
    "Task interrupted because the gateway restarted before LocalExecutor completion."
)


async def reconcile_interrupted_tasks() -> int:
    """Fail orphaned local-executor tasks after process restart."""
    if celery_settings.enabled:
        return 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskRecord).where(
                TaskRecord.status.in_(
                    [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]
                )
            )
        )
        records = list(result.scalars().all())
        if not records:
            return 0

        now = datetime.now(UTC)
        for record in records:
            record.status = TaskStatus.FAILED.value
            record.error = _LOCAL_EXECUTOR_INTERRUPTED_MESSAGE
            record.message = _LOCAL_EXECUTOR_INTERRUPTED_MESSAGE
            record.completed_at = now

        await session.commit()

        store = TaskStore(redis_client, session)

        for record in records:
            try:
                await store.set_task_state(
                    record.id,
                    TaskStatus.FAILED.value,
                    progress=record.progress,
                    message=_LOCAL_EXECUTOR_INTERRUPTED_MESSAGE,
                )
            except Exception:
                logger.warning(
                    "Failed to update Redis runtime state for interrupted task %s",
                    record.id,
                    exc_info=True,
                )

        logger.warning(
            "Marked %s interrupted LocalExecutor task(s) as failed during startup",
            len(records),
        )
        return len(records)

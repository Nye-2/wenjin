"""Startup reconciliation helpers for interrupted execution/task state."""

from __future__ import annotations

import logging

from src.config.app_config import celery_settings

logger = logging.getLogger(__name__)


async def reconcile_interrupted_tasks() -> int:
    """Reconcile interrupted execution state after process restarts.

    Execution runs are execution-first, so startup recovery must ensure no
    stale `pending` / `running` / `cancelling` rows survive a restart forever.
    """
    if not celery_settings.enabled:
        logger.warning(
            "Task runtime is configured without Celery, which is unsupported in the "
            "current architecture; skipping interrupted-task reconciliation.",
        )
        return 0

    from src.database import get_db_session
    from src.services.execution_service import ExecutionService

    async with get_db_session() as db:
        reconciled = await ExecutionService(db).reconcile_interrupted_executions()
    return reconciled

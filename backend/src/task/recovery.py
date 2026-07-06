"""Startup reconciliation helpers for interrupted execution/task state."""

from __future__ import annotations

import logging

from src.config.app_config import celery_settings

logger = logging.getLogger(__name__)


async def reconcile_interrupted_tasks() -> int:
    """Reconcile interrupted execution state after process restarts.

    Execution runs are execution-first, so startup recovery must ensure no
    stale missing-lease or expired-lease execution rows survive a restart forever.
    """
    if not celery_settings.enabled:
        logger.warning(
            "Task runtime is configured without Celery, which is unsupported in the "
            "current architecture; skipping interrupted-task reconciliation.",
        )
        return 0

    from src.services.execution_service import ExecutionService

    return await ExecutionService().reconcile_interrupted_executions()

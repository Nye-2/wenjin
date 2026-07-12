"""Startup reconciliation helpers for auxiliary task state."""

from __future__ import annotations

import logging

from src.config.app_config import celery_settings

logger = logging.getLogger(__name__)


async def reconcile_interrupted_tasks() -> int:
    """Leave durable Mission recovery to the Mission reconciler."""
    if not celery_settings.enabled:
        logger.warning(
            "Task runtime is configured without Celery, which is unsupported in the current architecture; skipping interrupted-task reconciliation.",
        )
        return 0

    return 0

"""Startup reconciliation helpers for interrupted task state."""

from __future__ import annotations

import logging

from src.config.app_config import celery_settings

logger = logging.getLogger(__name__)


async def reconcile_interrupted_tasks() -> int:
    """No-op reconciliation in Celery-only task architecture."""
    if not celery_settings.enabled:
        logger.warning(
            "Task runtime is configured without Celery, which is unsupported in the "
            "current architecture; skipping interrupted-task reconciliation.",
        )
    return 0

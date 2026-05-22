"""Celery beat task -- scans enabled periodic credit grant rules.

Runs every 5 minutes. For each enabled `periodic` rule, checks its cron schedule
against last_triggered_at to decide whether it's due. If due, applies target_filter
to find users, batch-grants the rule.amount to each, updates last_triggered_at.
"""

from __future__ import annotations

import asyncio
import logging

from src.dataservice_client.provider import dataservice_client
from src.task.celery_app import celery_app

logger = logging.getLogger(__name__)

LOCK_KEY = "celery:lock:credit_periodic"
_LOCK_TTL = 240  # seconds — must be less than beat interval (300s)


async def _process_periodic_rules() -> dict[str, int]:
    from src.academic.cache.redis_client import redis_client

    # Distributed lock to prevent concurrent beat runs from double-granting.
    if not redis_client.is_connected:
        try:
            await redis_client.connect()
        except Exception:
            logger.warning("Redis unavailable; running without distributed lock")
    lock = None
    if redis_client.is_connected:
        lock = redis_client.client.lock(LOCK_KEY, timeout=_LOCK_TTL)
        if not await lock.acquire(blocking=False):
            logger.info("another worker holds the periodic credit lock; skipping")
            return {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}

    try:
        return await _process_periodic_rules_inner()
    finally:
        if lock is not None:
            try:
                if await lock.owned():
                    lock.release()
            except Exception:
                pass


async def _process_periodic_rules_inner() -> dict[str, int]:
    async with dataservice_client() as client:
        summary = await client.process_credit_periodic_grant_rules()
    return summary.model_dump()


@celery_app.task(name="credit_periodic.process_credit_grant_rules")
def process_credit_grant_rules() -> dict[str, int]:
    return asyncio.run(_process_periodic_rules())

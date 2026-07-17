"""Celery beat driver for bounded DataService periodic-credit grant pages."""

from __future__ import annotations

import asyncio
import logging

from src.academic.cache.redis_client import RedisClient
from src.dataservice_client.contracts.credit import CreditPeriodicGrantPageRequest
from src.dataservice_client.provider import dataservice_client
from src.task.celery_app import celery_app

logger = logging.getLogger(__name__)

LOCK_KEY = "celery:lock:credit_periodic"
_LOCK_TTL = 240  # seconds — must be less than beat interval (300s)
_BATCH_SIZE = 100


async def _process_periodic_rules() -> dict[str, int]:
    # Distributed lock to prevent concurrent beat runs from double-granting.
    redis_client = RedisClient()
    try:
        await redis_client.connect()
    except Exception:
        logger.warning(
            "Redis unavailable; DataService row locks remain authoritative"
        )
    lock = None
    if redis_client.is_connected:
        lock = redis_client.client.lock(LOCK_KEY, timeout=_LOCK_TTL)

    try:
        if lock is not None and not await lock.acquire(blocking=False):
            logger.info("another worker holds the periodic credit lock; skipping")
            return {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
        return await _process_periodic_rules_inner()
    finally:
        if lock is not None:
            try:
                if await lock.owned():
                    await lock.release()
            except Exception:
                logger.warning("Failed to release periodic credit lock", exc_info=True)
        await redis_client.disconnect()


async def _process_periodic_rules_inner() -> dict[str, int]:
    summary = {
        "rules_evaluated": 0,
        "rules_fired": 0,
        "users_granted": 0,
    }
    cursor: str | None = None
    async with dataservice_client() as client:
        while True:
            page = await client.process_credit_periodic_grant_page(
                CreditPeriodicGrantPageRequest(
                    cursor=cursor,
                    batch_size=_BATCH_SIZE,
                )
            )
            summary["rules_evaluated"] += page.rules_evaluated
            summary["rules_fired"] += page.rules_fired
            summary["users_granted"] += page.users_granted
            if page.next_cursor is None:
                return summary
            if page.next_cursor == cursor:
                raise RuntimeError("periodic credit cursor did not advance")
            cursor = page.next_cursor


@celery_app.task(
    name="credit_periodic.process_credit_grant_rules",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def process_credit_grant_rules() -> dict[str, int]:
    return asyncio.run(_process_periodic_rules())

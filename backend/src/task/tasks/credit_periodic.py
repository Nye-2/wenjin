"""Celery beat task -- scans enabled periodic credit grant rules.

Runs every 5 minutes. For each enabled `periodic` rule, checks its cron schedule
against last_triggered_at to decide whether it's due. If due, applies target_filter
to find users, batch-grants the rule.amount to each, updates last_triggered_at.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from croniter import croniter

from src.database import get_db_session
from src.dataservice.credit_api import CreditDataService
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
    now = datetime.now(UTC)
    summary: dict[str, int] = {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
    async with get_db_session() as db:
        credit_data = CreditDataService(db, autocommit=False)
        rules = await credit_data.list_enabled_periodic_grant_rules()

        for rule in rules:
            summary["rules_evaluated"] += 1
            cron_expr = rule.config.get("cron")
            if not cron_expr:
                logger.warning("rule %s missing cron in config; skipping", rule.id)
                continue

            base = rule.last_triggered_at or (now - timedelta(days=30))
            try:
                itr = croniter(cron_expr, base)
                next_fire = itr.get_next(datetime).replace(tzinfo=UTC)
            except Exception:
                logger.exception("rule %s invalid cron %r; skipping", rule.id, cron_expr)
                continue

            if next_fire > now:
                continue  # not yet due

            summary["users_granted"] += await credit_data.apply_periodic_grant_rule(
                rule=rule,
                now=now,
            )
            summary["rules_fired"] += 1

        await db.commit()
    return summary


@celery_app.task(name="credit_periodic.process_credit_grant_rules")
def process_credit_grant_rules() -> dict[str, int]:
    return asyncio.run(_process_periodic_rules())

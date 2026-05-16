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
from sqlalchemy import select

from src.database import (
    CreditGrantRule, CreditGrantRuleType, CreditTransaction, CreditTransactionType,
    User, get_db_session,
)
from src.task.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _process_periodic_rules() -> dict[str, int]:
    now = datetime.now(UTC)
    summary: dict[str, int] = {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
    async with get_db_session() as db:
        result = await db.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == CreditGrantRuleType.PERIODIC)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
        )
        rules = list(result.scalars().all())

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

            tf = rule.config.get("target_filter", {})
            user_stmt = select(User)
            active_within_days = tf.get("active_within_days")
            if active_within_days is not None:
                threshold = now - timedelta(days=int(active_within_days))
                user_stmt = user_stmt.where(User.last_login >= threshold)
            role = tf.get("role")
            if role == "user":
                user_stmt = user_stmt.where(User.is_superuser == False)  # noqa: E712
            elif role == "admin":
                user_stmt = user_stmt.where(User.is_superuser == True)  # noqa: E712

            user_result = await db.execute(user_stmt)
            users = list(user_result.scalars().all())

            for user in users:
                user.credits = (user.credits or 0) + rule.amount
                user.total_credits_earned = (user.total_credits_earned or 0) + rule.amount
                db.add(CreditTransaction(
                    user_id=user.id,
                    transaction_type=CreditTransactionType.ADMIN_GRANT,
                    amount=rule.amount,
                    balance_after=user.credits,
                    description=f"周期发放（rule {rule.id[:8]}***）",
                ))
                summary["users_granted"] += 1

            rule.last_triggered_at = now
            summary["rules_fired"] += 1

        await db.commit()
    return summary


@celery_app.task(name="credit_periodic.process_credit_grant_rules")
def process_credit_grant_rules() -> dict[str, int]:
    return asyncio.run(_process_periodic_rules())

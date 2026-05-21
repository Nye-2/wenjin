"""Credit command/query service."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.credit import CreditTransactionType
from src.database.models.credit_grant_rule import CreditGrantRuleType
from src.dataservice.domains.credit.repository import CreditRepository


class DataServiceCreditService:
    """DataService-owned credit persistence operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = CreditRepository(session)

    async def list_grant_rules(self) -> list[Any]:
        return await self.repository.list_grant_rules()

    async def get_grant_rule(self, rule_id: str) -> Any | None:
        return await self.repository.get_grant_rule(rule_id)

    async def create_grant_rule(
        self,
        *,
        name: str,
        rule_type: CreditGrantRuleType,
        amount: int,
        config: dict[str, Any],
        description: str | None,
        admin_id: str,
    ) -> Any:
        rule = self.repository.create_grant_rule(
            {
                "name": name,
                "rule_type": rule_type,
                "amount": amount,
                "description": description,
                "config": dict(config),
                "enabled": True,
                "created_by_admin_id": admin_id,
            }
        )
        await self._finish(rule)
        return rule

    async def update_grant_rule(
        self,
        *,
        rule_id: str,
        name: str,
        amount: int,
        config: dict[str, Any],
        description: str | None,
    ) -> Any | None:
        rule = await self.repository.get_grant_rule(rule_id)
        if rule is None:
            return None
        rule.name = name
        rule.amount = amount
        rule.description = description
        rule.config = dict(config)
        await self._finish(rule)
        return rule

    async def toggle_grant_rule(self, rule_id: str) -> Any | None:
        rule = await self.repository.get_grant_rule(rule_id)
        if rule is None:
            return None
        rule.enabled = not bool(rule.enabled)
        await self._finish(rule)
        return rule

    async def delete_grant_rule(self, rule_id: str) -> Any | None:
        rule = await self.repository.get_grant_rule(rule_id)
        if rule is None:
            return None
        await self.repository.delete_grant_rule(rule)
        await self._finish()
        return rule

    async def get_active_grant_rule(self, rule_type: CreditGrantRuleType) -> Any | None:
        return await self.repository.get_active_grant_rule(rule_type)

    async def list_enabled_periodic_grant_rules(self) -> list[Any]:
        return await self.repository.list_enabled_grant_rules(
            CreditGrantRuleType.PERIODIC
        )

    async def apply_registration_bonus_from_rule(self, *, user_id: str, rule: Any) -> Any:
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise ValueError("user not found")
        amount = int(rule.amount)
        user.credits = int(user.credits or 0) + amount
        user.total_credits_earned = int(user.total_credits_earned or 0) + amount
        tx = self.repository.create_credit_transaction(
            {
                "user_id": user_id,
                "transaction_type": CreditTransactionType.REGISTRATION_BONUS,
                "amount": amount,
                "balance_after": user.credits,
                "description": f"注册奖励 (rule {str(rule.id)[:8]}***)",
            }
        )
        await self._finish(tx)
        return tx

    async def apply_periodic_grant_rule(self, *, rule: Any, now: Any) -> int:
        target_filter = rule.config.get("target_filter", {}) if isinstance(rule.config, dict) else {}
        active_since = None
        active_within_days = target_filter.get("active_within_days")
        if active_within_days is not None:
            active_since = now - timedelta(days=int(active_within_days))
        users = await self.repository.list_users_for_periodic_credit_filter(
            active_since=active_since,
            role=target_filter.get("role"),
        )
        amount = int(rule.amount)
        for user in users:
            user.credits = int(user.credits or 0) + amount
            user.total_credits_earned = int(user.total_credits_earned or 0) + amount
            self.repository.create_credit_transaction(
                {
                    "user_id": user.id,
                    "transaction_type": CreditTransactionType.ADMIN_GRANT,
                    "amount": amount,
                    "balance_after": user.credits,
                    "description": f"周期发放（rule {str(rule.id)[:8]}***）",
                }
            )
        rule.last_triggered_at = now
        await self._finish()
        return len(users)

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()

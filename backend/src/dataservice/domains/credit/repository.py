"""Credit repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.credit import CreditTransaction, CreditTransactionType
from src.database.models.credit_grant_rule import CreditGrantRule, CreditGrantRuleType
from src.database.models.user import User


class CreditRepository:
    """DataService-owned persistence operations for credit tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_grant_rules(self) -> list[CreditGrantRule]:
        result = await self.session.execute(
            select(CreditGrantRule).order_by(CreditGrantRule.created_at)
        )
        return list(result.scalars().all())

    async def get_grant_rule(self, rule_id: str) -> CreditGrantRule | None:
        result = await self.session.execute(
            select(CreditGrantRule).where(CreditGrantRule.id == rule_id)
        )
        return result.scalars().first()

    def create_grant_rule(self, values: dict[str, Any]) -> CreditGrantRule:
        rule = CreditGrantRule(**values)
        self.session.add(rule)
        return rule

    async def delete_grant_rule(self, rule: CreditGrantRule) -> None:
        await self.session.delete(rule)

    async def get_active_grant_rule(
        self,
        rule_type: CreditGrantRuleType,
    ) -> CreditGrantRule | None:
        result = await self.session.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == rule_type)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
            .order_by(CreditGrantRule.created_at)
        )
        return result.scalars().first()

    async def list_enabled_grant_rules(
        self,
        rule_type: CreditGrantRuleType,
    ) -> list[CreditGrantRule]:
        result = await self.session.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == rule_type)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_user_for_update(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_users_for_periodic_credit_filter(
        self,
        *,
        active_since: Any | None,
        role: str | None,
    ) -> list[User]:
        stmt = select(User)
        if active_since is not None:
            stmt = stmt.where(User.last_login >= active_since)
        if role == "user":
            stmt = stmt.where(User.is_superuser == False)  # noqa: E712
        elif role == "admin":
            stmt = stmt.where(User.is_superuser == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def create_credit_transaction(self, values: dict[str, Any]) -> CreditTransaction:
        tx = CreditTransaction(**values)
        self.session.add(tx)
        return tx


__all__ = [
    "CreditGrantRuleType",
    "CreditRepository",
    "CreditTransactionType",
]

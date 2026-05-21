"""Public in-process credit API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.credit import CreditTransactionType
from src.database.models.credit_grant_rule import CreditGrantRuleType
from src.dataservice.domains.credit.service import DataServiceCreditService


class CreditDataService:
    """Credit API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceCreditService(session, autocommit=autocommit)

    async def list_grant_rules(self) -> list[Any]:
        return await self._domain.list_grant_rules()

    async def get_grant_rule(self, rule_id: str) -> Any | None:
        return await self._domain.get_grant_rule(rule_id)

    async def create_grant_rule(self, **kwargs: Any) -> Any:
        return await self._domain.create_grant_rule(**kwargs)

    async def update_grant_rule(self, **kwargs: Any) -> Any | None:
        return await self._domain.update_grant_rule(**kwargs)

    async def toggle_grant_rule(self, rule_id: str) -> Any | None:
        return await self._domain.toggle_grant_rule(rule_id)

    async def delete_grant_rule(self, rule_id: str) -> Any | None:
        return await self._domain.delete_grant_rule(rule_id)

    async def get_active_grant_rule(self, rule_type: CreditGrantRuleType) -> Any | None:
        return await self._domain.get_active_grant_rule(rule_type)

    async def list_enabled_periodic_grant_rules(self) -> list[Any]:
        return await self._domain.list_enabled_periodic_grant_rules()

    async def apply_registration_bonus_from_rule(self, *, user_id: str, rule: Any) -> Any:
        return await self._domain.apply_registration_bonus_from_rule(
            user_id=user_id,
            rule=rule,
        )

    async def apply_periodic_grant_rule(self, *, rule: Any, now: Any) -> int:
        return await self._domain.apply_periodic_grant_rule(rule=rule, now=now)


__all__ = [
    "CreditDataService",
    "CreditGrantRuleType",
    "CreditTransactionType",
]

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

    async def get_balance(self, user_id: str) -> int | None:
        return await self._domain.get_balance(user_id)

    async def get_credit_summary(self, user_id: str) -> dict[str, int] | None:
        return await self._domain.get_credit_summary(user_id)

    async def get_admin_credit_summary(self) -> dict[str, int]:
        return await self._domain.get_admin_credit_summary()

    async def get_thread_token_usage_summary(self) -> dict[str, int]:
        return await self._domain.get_thread_token_usage_summary()

    async def aggregate_credit_consumption_stats(self, **kwargs: Any) -> dict[str, Any]:
        return await self._domain.aggregate_credit_consumption_stats(**kwargs)

    async def get_credit_history(self, **kwargs: Any) -> tuple[list[Any], int]:
        return await self._domain.get_credit_history(**kwargs)

    async def get_consumed_tokens(self, **kwargs: Any) -> int:
        return await self._domain.get_consumed_tokens(**kwargs)

    async def get_user_for_update(self, user_id: str) -> Any | None:
        return await self._domain.get_user_for_update(user_id)

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

    async def process_periodic_grant_rules(self, *, now: Any | None = None) -> dict[str, int]:
        return await self._domain.process_periodic_grant_rules(now=now)

    async def record_consumption(self, **kwargs: Any) -> tuple[Any, int]:
        return await self._domain.record_consumption(**kwargs)

    async def admin_adjust(self, **kwargs: Any) -> Any:
        return await self._domain.admin_adjust(**kwargs)

    async def create_redeem_code(self, **kwargs: Any) -> Any:
        return await self._domain.create_redeem_code(**kwargs)

    async def list_redeem_codes(self, **kwargs: Any) -> list[Any]:
        return await self._domain.list_redeem_codes(**kwargs)

    async def disable_redeem_code(self, code_id: str) -> Any | None:
        return await self._domain.disable_redeem_code(code_id)

    async def redeem_code(self, *, code: str, user_id: str) -> Any:
        return await self._domain.redeem_code(code=code, user_id=user_id)

    async def record_referral(self, **kwargs: Any) -> Any:
        return await self._domain.record_referral(**kwargs)

    async def get_referral_by_referee(self, referee_user_id: str) -> Any | None:
        return await self._domain.get_referral_by_referee(referee_user_id)

    async def apply_referee_signup_bonus(self, *, referee_user_id: str) -> Any | None:
        return await self._domain.apply_referee_signup_bonus(referee_user_id=referee_user_id)

    async def apply_referrer_first_task_bonus(self, *, referee_user_id: str) -> Any | None:
        return await self._domain.apply_referrer_first_task_bonus(referee_user_id=referee_user_id)


__all__ = [
    "CreditDataService",
    "CreditGrantRuleType",
    "CreditTransactionType",
]

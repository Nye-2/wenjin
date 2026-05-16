"""CreditGrantRuleService — admin CRUD with discriminated-union config validation."""

from __future__ import annotations

from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import CreditGrantRule, CreditGrantRuleType


class RegistrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReferralConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: Literal["on_signup", "on_first_task"] = "on_first_task"


class ReferredConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: Literal["on_signup"] = "on_signup"


class TargetFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_within_days: int | None = None
    role: Literal["user", "admin"] | None = None


class PeriodicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cron: str
    target_filter: TargetFilter = TargetFilter()

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not croniter.is_valid(self.cron):
            raise ValueError(f"invalid cron expression: {self.cron!r}")


CONFIG_MODELS: dict[CreditGrantRuleType, type[BaseModel]] = {
    CreditGrantRuleType.REGISTRATION_BONUS: RegistrationConfig,
    CreditGrantRuleType.REFERRAL_REFERRER: ReferralConfig,
    CreditGrantRuleType.REFERRAL_REFERRED: ReferredConfig,
    CreditGrantRuleType.PERIODIC: PeriodicConfig,
}


def _validated_config(rule_type: CreditGrantRuleType, raw: dict[str, Any]) -> dict[str, Any]:
    model_cls = CONFIG_MODELS[rule_type]
    try:
        model = model_cls(**raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(f"config invalid for {rule_type}: {e}") from e
    return model.model_dump()


class CreditGrantRuleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[CreditGrantRule]:
        result = await self.db.execute(select(CreditGrantRule).order_by(CreditGrantRule.created_at))
        return list(result.scalars().all())

    async def get(self, rule_id: str) -> CreditGrantRule | None:
        result = await self.db.execute(select(CreditGrantRule).where(CreditGrantRule.id == rule_id))
        return result.scalars().first()

    async def create(
        self, *, name: str, rule_type: CreditGrantRuleType, amount: int,
        config: dict[str, Any], description: str | None = None, admin_id: str,
    ) -> CreditGrantRule:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule_type, config or {})

        rule = CreditGrantRule(
            name=name, rule_type=rule_type, amount=amount,
            description=description, config=config, enabled=True,
            created_by_admin_id=admin_id,
        )
        self.db.add(rule)

        from src.database import AdminLog
        self.db.add(AdminLog(
            action="credit_rule_create", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule.id, "rule_type": rule_type.value, "amount": amount},
        ))
        await self.db.commit()
        return rule

    async def update(
        self, *, rule_id: str, name: str, amount: int, config: dict[str, Any],
        description: str | None, admin_id: str,
    ) -> CreditGrantRule:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule.rule_type, config or {})
        rule.name = name
        rule.amount = amount
        rule.description = description
        rule.config = config

        from src.database import AdminLog
        self.db.add(AdminLog(
            action="credit_rule_update", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule_id, "amount_after": amount},
        ))
        await self.db.commit()
        return rule

    async def toggle(self, rule_id: str, admin_id: str) -> CreditGrantRule:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        previous = rule.enabled
        rule.enabled = not previous

        from src.database import AdminLog
        self.db.add(AdminLog(
            action="credit_rule_toggle", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule_id, "enabled_before": previous, "enabled_after": rule.enabled},
        ))
        await self.db.commit()
        return rule

    async def delete(self, rule_id: str, admin_id: str) -> None:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        await self.db.delete(rule)

        from src.database import AdminLog
        self.db.add(AdminLog(
            action="credit_rule_delete", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule_id, "rule_type": rule.rule_type.value},
        ))
        await self.db.commit()

    async def get_active_rule(self, rule_type: CreditGrantRuleType) -> CreditGrantRule | None:
        """Returns the first enabled rule of the given type, or None."""
        result = await self.db.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == rule_type)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
            .order_by(CreditGrantRule.created_at)
        )
        return result.scalars().first()

    async def apply_registration_bonus(self, user_id: str) -> CreditTransaction | None:
        """Apply the active registration_bonus rule's amount to a freshly-registered user."""
        rule = await self.get_active_rule(CreditGrantRuleType.REGISTRATION_BONUS)
        if rule is None:
            return None
        from src.database import CreditTransaction, CreditTransactionType, User
        from sqlalchemy import select
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user is None:
            raise ValueError("user not found")
        user.credits = (user.credits or 0) + rule.amount
        user.total_credits_earned = (user.total_credits_earned or 0) + rule.amount
        txn = CreditTransaction(
            user_id=user_id, transaction_type=CreditTransactionType.REGISTRATION_BONUS,
            amount=rule.amount, balance_after=user.credits,
            description=f"注册奖励 (rule {rule.id[:8]}***)",
        )
        self.db.add(txn)
        return txn


# Forward reference resolved at runtime
from src.database import CreditTransaction  # noqa: E402

"""CreditGrantRuleService — admin CRUD with discriminated-union config validation."""

from __future__ import annotations

from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.catalog_api import CatalogDataService
from src.dataservice.credit_api import CreditDataService, CreditGrantRuleType


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
        self._credit = CreditDataService(db, autocommit=False)

    async def _record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        details: dict[str, Any],
    ) -> None:
        await CatalogDataService(self.db, autocommit=False).record_admin_log(
            action=action,
            admin_id=admin_id,
            target_user_id=None,
            details=details,
        )

    async def list_all(self) -> list[Any]:
        return await self._credit.list_grant_rules()

    async def get(self, rule_id: str) -> Any | None:
        return await self._credit.get_grant_rule(rule_id)

    async def create(
        self, *, name: str, rule_type: CreditGrantRuleType, amount: int,
        config: dict[str, Any], description: str | None = None, admin_id: str,
    ) -> Any:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule_type, config or {})

        rule = await self._credit.create_grant_rule(
            name=name,
            rule_type=rule_type,
            amount=amount,
            description=description,
            config=config,
            admin_id=admin_id,
        )

        await self._record_admin_log(
            action="credit_rule_create",
            admin_id=admin_id,
            details={"rule_id": rule.id, "rule_type": rule_type.value, "amount": amount},
        )
        await self.db.commit()
        return rule

    async def update(
        self, *, rule_id: str, name: str, amount: int, config: dict[str, Any],
        description: str | None, admin_id: str,
    ) -> Any:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule.rule_type, config or {})
        rule = await self._credit.update_grant_rule(
            rule_id=rule_id,
            name=name,
            amount=amount,
            config=config,
            description=description,
        )
        if rule is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="credit_rule_update",
            admin_id=admin_id,
            details={"rule_id": rule_id, "amount_after": amount},
        )
        await self.db.commit()
        return rule

    async def toggle(self, rule_id: str, admin_id: str) -> Any:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        previous = rule.enabled
        rule = await self._credit.toggle_grant_rule(rule_id)
        if rule is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="credit_rule_toggle",
            admin_id=admin_id,
            details={"rule_id": rule_id, "enabled_before": previous, "enabled_after": rule.enabled},
        )
        await self.db.commit()
        return rule

    async def delete(self, rule_id: str, admin_id: str) -> None:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        rule_type = rule.rule_type.value
        deleted = await self._credit.delete_grant_rule(rule_id)
        if deleted is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="credit_rule_delete",
            admin_id=admin_id,
            details={"rule_id": rule_id, "rule_type": rule_type},
        )
        await self.db.commit()

    async def get_active_rule(self, rule_type: CreditGrantRuleType) -> Any | None:
        """Returns the first enabled rule of the given type, or None."""
        return await self._credit.get_active_grant_rule(rule_type)

    async def apply_registration_bonus(self, user_id: str) -> Any | None:
        """Apply the active registration_bonus rule's amount to a freshly-registered user."""
        rule = await self.get_active_rule(CreditGrantRuleType.REGISTRATION_BONUS)
        if rule is None:
            return None
        return await self._credit.apply_registration_bonus_from_rule(
            user_id=user_id,
            rule=rule,
        )

"""CreditGrantRuleService — admin CRUD with discriminated-union config validation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, ValidationError

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.audit import AuditLogCreatePayload
from src.dataservice_client.contracts.credit import (
    CreditGrantRuleCreatePayload,
    CreditGrantRuleUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client


class CreditGrantRuleType(StrEnum):
    REGISTRATION_BONUS = "registration_bonus"
    REFERRAL_REFERRER = "referral_referrer"
    REFERRAL_REFERRED = "referral_referred"
    PERIODIC = "periodic"


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


CONFIG_MODELS: dict[str, type[BaseModel]] = {
    CreditGrantRuleType.REGISTRATION_BONUS.value: RegistrationConfig,
    CreditGrantRuleType.REFERRAL_REFERRER.value: ReferralConfig,
    CreditGrantRuleType.REFERRAL_REFERRED.value: ReferredConfig,
    CreditGrantRuleType.PERIODIC.value: PeriodicConfig,
}


def _rule_type_value(rule_type: Any) -> str:
    return str(rule_type.value if hasattr(rule_type, "value") else rule_type)


def _validated_config(rule_type: Any, raw: dict[str, Any]) -> dict[str, Any]:
    rule_type_value = _rule_type_value(rule_type)
    model_cls = CONFIG_MODELS[rule_type_value]
    try:
        model = model_cls(**raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(f"config invalid for {rule_type_value}: {e}") from e
    return model.model_dump()


class CreditGrantRuleService:
    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def _record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        details: dict[str, Any],
    ) -> None:
        async with self._client() as client:
            await client.create_audit_log(
                AuditLogCreatePayload(
                    action=action,
                    user_id=admin_id,
                    target_type="credit_grant_rule",
                    payload=details,
                )
            )

    async def list_all(self) -> list[Any]:
        async with self._client() as client:
            return await client.list_credit_grant_rules()

    async def get(self, rule_id: str) -> Any | None:
        async with self._client() as client:
            return await client.get_credit_grant_rule(rule_id)

    async def create(
        self,
        *,
        name: str,
        rule_type: CreditGrantRuleType,
        amount: int,
        config: dict[str, Any],
        description: str | None = None,
        admin_id: str,
    ) -> Any:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule_type, config or {})

        rule_type_value = _rule_type_value(rule_type)
        async with self._client() as client:
            rule = await client.create_credit_grant_rule(
                CreditGrantRuleCreatePayload(
                    name=name,
                    rule_type=rule_type_value,
                    amount=amount,
                    description=description,
                    config=config,
                    admin_id=admin_id,
                )
            )
        if rule is None:
            raise RuntimeError("DataService did not return created credit grant rule")

        await self._record_admin_log(
            action="credit_rule_create",
            admin_id=admin_id,
            details={"rule_id": rule.id, "rule_type": rule_type_value, "amount": amount},
        )
        return rule

    async def update(
        self,
        *,
        rule_id: str,
        name: str,
        amount: int,
        config: dict[str, Any],
        description: str | None,
        admin_id: str,
    ) -> Any:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule.rule_type, config or {})
        async with self._client() as client:
            rule = await client.update_credit_grant_rule(
                rule_id,
                CreditGrantRuleUpdatePayload(
                    name=name,
                    amount=amount,
                    config=config,
                    description=description,
                ),
            )
        if rule is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="credit_rule_update",
            admin_id=admin_id,
            details={"rule_id": rule_id, "amount_after": amount},
        )
        return rule

    async def toggle(self, rule_id: str, admin_id: str) -> Any:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        previous = rule.enabled
        async with self._client() as client:
            rule = await client.toggle_credit_grant_rule(rule_id)
        if rule is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="credit_rule_toggle",
            admin_id=admin_id,
            details={"rule_id": rule_id, "enabled_before": previous, "enabled_after": rule.enabled},
        )
        return rule

    async def delete(self, rule_id: str, admin_id: str) -> None:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        rule_type = _rule_type_value(rule.rule_type)
        async with self._client() as client:
            deleted = await client.delete_credit_grant_rule(rule_id)
        if not deleted:
            raise ValueError("not found")

        await self._record_admin_log(
            action="credit_rule_delete",
            admin_id=admin_id,
            details={"rule_id": rule_id, "rule_type": rule_type},
        )

    async def get_active_rule(self, rule_type: CreditGrantRuleType) -> Any | None:
        """Returns the first enabled rule of the given type, or None."""
        async with self._client() as client:
            return await client.get_active_credit_grant_rule(_rule_type_value(rule_type))

    async def apply_registration_bonus(self, user_id: str) -> Any | None:
        """Apply the active registration_bonus rule's amount to a freshly-registered user."""
        async with self._client() as client:
            return await client.apply_credit_registration_bonus(user_id)

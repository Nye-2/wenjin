"""Pricing policy domain service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.policies import calculate_model_usage_credits
from src.database.models.pricing_policy import PricingPolicyKind
from src.dataservice.domains.pricing.contracts import (
    CapabilityPricingPolicyConfig,
    GlobalCreditPolicyConfig,
    ModelUsagePolicyConfig,
    PricingPolicyCreateCommand,
    PricingPolicyRecord,
    PricingPolicyUpdateCommand,
    PricingSimulationRequest,
    PricingSimulationResult,
    SandboxPricingPolicyConfig,
    ToolPricingPolicyConfig,
)
from src.dataservice.domains.pricing.repository import PricingPolicyRepository


class DataServicePricingPolicyService:
    """DataService-owned pricing policy operations and simulator."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = PricingPolicyRepository(session)

    async def list_policies(
        self,
        *,
        policy_kind: str | PricingPolicyKind | None = None,
        enabled_only: bool = False,
    ) -> list[PricingPolicyRecord]:
        rows = await self.repository.list_policies(
            policy_kind=_enum_value(policy_kind) if policy_kind is not None else None,
            enabled_only=enabled_only,
        )
        return [self.to_record(row) for row in rows]

    async def get_policy(self, policy_id_or_key: str) -> PricingPolicyRecord | None:
        row = await self.repository.get_policy(policy_id_or_key)
        return self.to_record(row) if row is not None else None

    async def create_policy(
        self,
        command: PricingPolicyCreateCommand,
        *,
        admin_id: str | None = None,
    ) -> PricingPolicyRecord:
        kind = _coerce_kind(command.policy_kind)
        config = _validated_config(kind, command.config)
        row = await self.repository.create_policy(
            {
                "policy_key": command.policy_key,
                "policy_kind": kind,
                "name": command.name,
                "enabled": command.enabled,
                "version": 1,
                "config_json": config,
                "created_by_admin_id": admin_id,
                "updated_by_admin_id": admin_id,
            }
        )
        await self._finish(row)
        return self.to_record(row)

    async def update_policy(
        self,
        policy_id_or_key: str,
        command: PricingPolicyUpdateCommand,
        *,
        admin_id: str | None = None,
    ) -> PricingPolicyRecord | None:
        row = await self.repository.get_policy(policy_id_or_key)
        if row is None:
            return None
        if command.name is not None:
            row.name = command.name
        if command.enabled is not None:
            row.enabled = command.enabled
        if command.config is not None:
            row.config_json = _validated_config(row.policy_kind, command.config)
        row.updated_by_admin_id = admin_id
        row.version = int(getattr(row, "version", 1) or 1) + 1
        await self._finish(row)
        return self.to_record(row)

    async def disable_policy(
        self,
        policy_id_or_key: str,
        *,
        admin_id: str | None = None,
    ) -> PricingPolicyRecord | None:
        return await self.update_policy(
            policy_id_or_key,
            PricingPolicyUpdateCommand(enabled=False),
            admin_id=admin_id,
        )

    def simulate(self, request: PricingSimulationRequest) -> PricingSimulationResult:
        if request.policy_kind == "model_usage":
            return self._simulate_model_usage(request)
        return PricingSimulationResult(
            charge_credits=0,
            breakdown={"policy_kind": request.policy_kind},
        )

    def _simulate_model_usage(self, request: PricingSimulationRequest) -> PricingSimulationResult:
        policy = request.model_usage_policy or ModelUsagePolicyConfig()
        charge = calculate_model_usage_credits(
            model_policy=policy.model_dump(mode="json", exclude_none=True),
            global_policy=request.global_policy.model_dump(mode="json"),
            token_usage={
                "input_tokens": request.prompt_tokens,
                "output_tokens": request.completion_tokens,
                "total_tokens": request.prompt_tokens + request.completion_tokens,
            },
            surface=request.surface,
        )
        charge_credits = charge.credits_to_charge
        raw_cost_cny = charge.raw_cost_cny
        revenue_cny = charge_credits / request.global_policy.credits_per_cny
        return PricingSimulationResult(
            charge_credits=charge_credits,
            raw_cost_cny=raw_cost_cny,
            margin_cny=revenue_cny - raw_cost_cny,
            breakdown=charge.breakdown(),
        )

    def to_record(self, row: Any) -> PricingPolicyRecord:
        return PricingPolicyRecord(
            id=str(row.id) if getattr(row, "id", None) is not None else None,
            policy_key=row.policy_key,
            policy_kind=_enum_value(row.policy_kind),
            name=row.name,
            enabled=bool(row.enabled),
            version=int(getattr(row, "version", 1) or 1),
            config=dict(getattr(row, "config_json", {}) or {}),
            created_by_admin_id=getattr(row, "created_by_admin_id", None),
            updated_by_admin_id=getattr(row, "updated_by_admin_id", None),
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None and hasattr(self.session, "refresh"):
                await self.session.refresh(record)
            return
        await self.session.flush()
        if record is not None and hasattr(self.session, "refresh"):
            await self.session.refresh(record)


def pricing_result_to_dict(result: PricingSimulationResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _validated_config(kind: str | PricingPolicyKind, config: dict[str, Any]) -> dict[str, Any]:
    kind_value = _enum_value(kind)
    validators = {
        PricingPolicyKind.GLOBAL_CREDIT.value: GlobalCreditPolicyConfig,
        PricingPolicyKind.MODEL_USAGE.value: ModelUsagePolicyConfig,
        PricingPolicyKind.CAPABILITY.value: CapabilityPricingPolicyConfig,
        PricingPolicyKind.TOOL.value: ToolPricingPolicyConfig,
        PricingPolicyKind.SANDBOX.value: SandboxPricingPolicyConfig,
    }
    validator = validators[kind_value]
    return validator.model_validate(config).model_dump(mode="json", exclude_none=True)


def _coerce_kind(value: str | PricingPolicyKind) -> PricingPolicyKind:
    if isinstance(value, PricingPolicyKind):
        return value
    return PricingPolicyKind(str(value))


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value

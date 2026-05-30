"""Gateway facade for pricing policy management."""

from __future__ import annotations

from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.pricing import (
    PricingPolicyCreatePayload,
    PricingPolicyPayload,
    PricingPolicyUpdatePayload,
    PricingSimulationRequestPayload,
)


class PricingPolicyService:
    def __init__(self, *, dataservice: AsyncDataServiceClient) -> None:
        self.dataservice = dataservice

    async def list_policies(
        self,
        *,
        policy_kind: str | None = None,
        enabled_only: bool = False,
    ) -> list[PricingPolicyPayload]:
        return await self.dataservice.list_pricing_policies(
            policy_kind=policy_kind,
            enabled_only=enabled_only,
        )

    async def create_policy(
        self,
        command: PricingPolicyCreatePayload,
        *,
        admin_id: str,
    ) -> PricingPolicyPayload:
        payload = command.model_copy(update={"admin_id": admin_id})
        return await self.dataservice.create_pricing_policy(payload)

    async def update_policy(
        self,
        policy_id_or_key: str,
        command: PricingPolicyUpdatePayload,
        *,
        admin_id: str,
    ) -> PricingPolicyPayload | None:
        payload = command.model_copy(update={"admin_id": admin_id})
        return await self.dataservice.update_pricing_policy(policy_id_or_key, payload)

    async def disable_policy(
        self,
        policy_id_or_key: str,
        *,
        admin_id: str,
    ) -> PricingPolicyPayload | None:
        return await self.dataservice.disable_pricing_policy(policy_id_or_key, admin_id=admin_id)

    async def simulate(self, command: PricingSimulationRequestPayload) -> dict[str, Any]:
        return await self.dataservice.simulate_pricing(command)

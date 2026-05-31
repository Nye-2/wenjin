"""Pricing DataService client methods."""

from __future__ import annotations

from typing import Any

from src.dataservice_client.contracts.pricing import (
    PricingPolicyCreatePayload,
    PricingPolicyPayload,
    PricingPolicyUpdatePayload,
    PricingSimulationRequestPayload,
)


class PricingDataServiceClientMixin:
    """Typed DataService methods for this domain."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def simulate_pricing(self, command: PricingSimulationRequestPayload) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/internal/v1/pricing-policies/simulate",
            json=command.model_dump(mode="json"),
        )
        return dict(payload["data"])

    async def list_pricing_policies(
        self,
        *,
        policy_kind: str | None = None,
        enabled_only: bool = False,
    ) -> list[PricingPolicyPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/pricing-policies",
            params={"policy_kind": policy_kind, "enabled_only": enabled_only},
        )
        return [PricingPolicyPayload.model_validate(item) for item in payload["data"]]

    async def get_pricing_policy(self, policy_id_or_key: str) -> PricingPolicyPayload | None:
        payload = await self._request("GET", f"/internal/v1/pricing-policies/{policy_id_or_key}")
        data = payload.get("data")
        return PricingPolicyPayload.model_validate(data) if data is not None else None

    async def create_pricing_policy(self, command: PricingPolicyCreatePayload) -> PricingPolicyPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/pricing-policies",
            json=command.model_dump(mode="json", exclude_none=True),
        )
        return PricingPolicyPayload.model_validate(payload["data"])

    async def update_pricing_policy(
        self,
        policy_id_or_key: str,
        command: PricingPolicyUpdatePayload,
    ) -> PricingPolicyPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/pricing-policies/{policy_id_or_key}",
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return PricingPolicyPayload.model_validate(data) if data is not None else None

    async def disable_pricing_policy(
        self,
        policy_id_or_key: str,
        *,
        admin_id: str | None = None,
    ) -> PricingPolicyPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/pricing-policies/{policy_id_or_key}/disable",
            json={"admin_id": admin_id},
        )
        data = payload.get("data")
        return PricingPolicyPayload.model_validate(data) if data is not None else None

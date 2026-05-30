"""Tests for gateway pricing policy service."""

from __future__ import annotations

from typing import Any

import pytest

from src.dataservice_client.contracts.pricing import (
    PricingPolicyCreatePayload,
    PricingPolicyPayload,
    PricingPolicyUpdatePayload,
    PricingSimulationRequestPayload,
)
from src.services.pricing_policy_service import PricingPolicyService


class _FakeDataService:
    def __init__(self) -> None:
        self.simulation: Any = None
        self.created: Any = None
        self.updated: Any = None
        self.disabled: str | None = None

    async def list_pricing_policies(self, *, policy_kind: str | None = None, enabled_only: bool = False):
        return [
            PricingPolicyPayload(
                id="policy-1",
                policy_key="model-standard",
                policy_kind="model_usage",
                name="Model standard",
                enabled=True,
                version=1,
                config={"tokens_per_credit": 1000},
            )
        ]

    async def create_pricing_policy(self, command):
        self.created = command
        return PricingPolicyPayload(
            id="policy-1",
            policy_key=command.policy_key,
            policy_kind=command.policy_kind,
            name=command.name,
            enabled=True,
            version=1,
            config=command.config,
        )

    async def update_pricing_policy(self, policy_id_or_key: str, command):
        self.updated = (policy_id_or_key, command)
        return PricingPolicyPayload(
            id="policy-1",
            policy_key=policy_id_or_key,
            policy_kind="model_usage",
            name=command.name or "Model standard",
            enabled=True,
            version=2,
            config=command.config or {"tokens_per_credit": 1000},
        )

    async def disable_pricing_policy(self, policy_id_or_key: str, *, admin_id: str | None = None):
        self.disabled = policy_id_or_key
        return PricingPolicyPayload(
            id="policy-1",
            policy_key=policy_id_or_key,
            policy_kind="model_usage",
            name="Model standard",
            enabled=False,
            version=2,
            config={"tokens_per_credit": 1000},
        )

    async def simulate_pricing(self, command):
        self.simulation = command
        return {
            "charge_credits": 3,
            "raw_cost_cny": 0.2,
            "margin_cny": 0.1,
            "breakdown": {"weighted_tokens": 3000},
        }


@pytest.mark.asyncio
async def test_gateway_pricing_service_delegates_simulation() -> None:
    dataservice = _FakeDataService()
    service = PricingPolicyService(dataservice=dataservice)  # type: ignore[arg-type]

    result = await service.simulate(
        PricingSimulationRequestPayload(
            policy_kind="model_usage",
            prompt_tokens=1000,
            completion_tokens=500,
        )
    )

    assert result["charge_credits"] == 3
    assert dataservice.simulation.policy_kind == "model_usage"


@pytest.mark.asyncio
async def test_gateway_pricing_service_delegates_crud() -> None:
    dataservice = _FakeDataService()
    service = PricingPolicyService(dataservice=dataservice)  # type: ignore[arg-type]

    policies = await service.list_policies(policy_kind="model_usage", enabled_only=True)
    created = await service.create_policy(
        PricingPolicyCreatePayload(
            policy_key="model-standard",
            policy_kind="model_usage",
            name="Model standard",
            config={"tokens_per_credit": 1000},
        ),
        admin_id="admin-1",
    )
    updated = await service.update_policy(
        "model-standard",
        PricingPolicyUpdatePayload(name="Model v2"),
        admin_id="admin-2",
    )
    disabled = await service.disable_policy("model-standard", admin_id="admin-3")

    assert policies[0].policy_key == "model-standard"
    assert created.policy_key == "model-standard"
    assert dataservice.created.admin_id == "admin-1"
    assert updated is not None and updated.version == 2
    _policy_id, update_command = dataservice.updated
    assert update_command.admin_id == "admin-2"
    assert disabled is not None and disabled.enabled is False
    assert dataservice.disabled == "model-standard"

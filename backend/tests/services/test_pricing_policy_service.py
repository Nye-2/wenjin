"""Tests for gateway pricing policy service."""

from __future__ import annotations

from typing import Any

import pytest

from src.dataservice_client.contracts.pricing import PricingSimulationRequestPayload
from src.services.pricing_policy_service import PricingPolicyService


class _FakeDataService:
    def __init__(self) -> None:
        self.simulation: Any = None

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

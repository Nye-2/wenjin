"""Gateway facade for pricing policy management."""

from __future__ import annotations

from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.pricing import PricingSimulationRequestPayload


class PricingPolicyService:
    def __init__(self, *, dataservice: AsyncDataServiceClient) -> None:
        self.dataservice = dataservice

    async def simulate(self, command: PricingSimulationRequestPayload) -> dict[str, Any]:
        return await self.dataservice.simulate_pricing(command)

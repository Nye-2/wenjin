"""Admin pricing policy endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.pricing import PricingSimulationRequestPayload
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.deps.core import get_dataservice_client
from src.services.pricing_policy_service import PricingPolicyService

router = APIRouter(prefix="/admin/pricing", tags=["admin", "pricing"])


async def _service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> PricingPolicyService:
    return PricingPolicyService(dataservice=dataservice)


@router.post("/simulate")
async def simulate_pricing(
    payload: dict[str, Any] = Body(...),
    service: PricingPolicyService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    return await service.simulate(PricingSimulationRequestPayload.model_validate(payload))

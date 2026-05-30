"""Pricing policy endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.pricing.contracts import PricingSimulationRequest
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.pricing import PricingSimulationRequestPayload

router = APIRouter(
    prefix="/internal/v1/pricing-policies",
    tags=["pricing-policies"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/simulate")
async def simulate_pricing(
    payload: PricingSimulationRequestPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    result = service.simulate(PricingSimulationRequest.model_validate(payload.model_dump(mode="json")))
    return envelope_ok(result.model_dump(mode="json"))

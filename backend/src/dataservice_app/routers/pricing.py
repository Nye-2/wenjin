"""Pricing policy endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.pricing.contracts import (
    PricingPolicyCreateCommand,
    PricingPolicyUpdateCommand,
    PricingSimulationRequest,
)
from src.dataservice.domains.pricing.service import DataServicePricingPolicyService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.pricing import PricingSimulationRequestPayload

router = APIRouter(
    prefix="/internal/v1/pricing-policies",
    tags=["pricing-policies"],
    dependencies=[Depends(require_internal_token)],
)


class PricingPolicyDisablePayload(BaseModel):
    admin_id: str | None = None


@router.get("")
async def list_pricing_policies(
    policy_kind: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    records = await service.list_policies(policy_kind=policy_kind, enabled_only=enabled_only)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/{policy_id_or_key}")
async def get_pricing_policy(
    policy_id_or_key: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    record = await service.get_policy(policy_id_or_key)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("")
async def create_pricing_policy(
    payload: dict,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    data = dict(payload)
    admin_id = data.pop("admin_id", None)
    record = await service.create_policy(
        PricingPolicyCreateCommand.model_validate(data),
        admin_id=admin_id,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.patch("/{policy_id_or_key}")
async def update_pricing_policy(
    policy_id_or_key: str,
    payload: dict,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    data = dict(payload)
    admin_id = data.pop("admin_id", None)
    record = await service.update_policy(
        policy_id_or_key,
        PricingPolicyUpdateCommand.model_validate(data),
        admin_id=admin_id,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/{policy_id_or_key}/disable")
async def disable_pricing_policy(
    policy_id_or_key: str,
    payload: PricingPolicyDisablePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    record = await service.disable_policy(policy_id_or_key, admin_id=payload.admin_id)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/simulate")
async def simulate_pricing(
    payload: PricingSimulationRequestPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServicePricingPolicyService(uow.required_session, autocommit=False)
    result = service.simulate(PricingSimulationRequest.model_validate(payload.model_dump(mode="json")))
    return envelope_ok(result.model_dump(mode="json"))

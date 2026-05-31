"""Admin pricing policy endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.pricing import (
    PricingPolicyCreatePayload,
    PricingPolicyUpdatePayload,
    PricingSimulationRequestPayload,
)
from src.dataservice_client.errors import DataServiceClientError
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.deps.core import get_dataservice_client
from src.gateway.error_mapping import dataservice_client_to_http_exception
from src.services.pricing_policy_service import PricingPolicyService

router = APIRouter(prefix="/admin/pricing", tags=["admin", "pricing"])
policies_router = APIRouter(prefix="/admin/pricing-policies", tags=["admin", "pricing"])


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
    try:
        return await service.simulate(PricingSimulationRequestPayload.model_validate(payload))
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc


@policies_router.get("")
async def list_pricing_policies(
    policy_kind: str | None = None,
    enabled_only: bool = False,
    service: PricingPolicyService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        policies = await service.list_policies(policy_kind=policy_kind, enabled_only=enabled_only)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    return {"items": [policy.model_dump(mode="json") for policy in policies], "total": len(policies)}


@policies_router.post("")
async def create_pricing_policy(
    payload: dict[str, Any] = Body(...),
    service: PricingPolicyService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        policy = await service.create_policy(
            PricingPolicyCreatePayload.model_validate(payload),
            admin_id=admin.id,
        )
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    return policy.model_dump(mode="json")


@policies_router.patch("/{policy_id_or_key}")
async def update_pricing_policy(
    policy_id_or_key: str,
    payload: dict[str, Any] = Body(...),
    service: PricingPolicyService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any] | None:
    try:
        policy = await service.update_policy(
            policy_id_or_key,
            PricingPolicyUpdatePayload.model_validate(payload),
            admin_id=admin.id,
        )
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    return policy.model_dump(mode="json") if policy else None


@policies_router.post("/{policy_id_or_key}/disable")
async def disable_pricing_policy(
    policy_id_or_key: str,
    service: PricingPolicyService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any] | None:
    try:
        policy = await service.disable_policy(policy_id_or_key, admin_id=admin.id)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    return policy.model_dump(mode="json") if policy else None

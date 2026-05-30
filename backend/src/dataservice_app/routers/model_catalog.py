"""Model catalog endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.model_catalog.service import DataServiceModelCatalogService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.model_catalog import (
    ModelCatalogCreatePayload,
    ModelCatalogHealthPayload,
    ModelCatalogUpdatePayload,
)

router = APIRouter(
    prefix="/internal/v1/model-catalog",
    tags=["model-catalog"],
    dependencies=[Depends(require_internal_token)],
)


class ModelCatalogDefaultPayload(BaseModel):
    admin_id: str | None = None


@router.get("/models")
async def list_models(
    category: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    records = await service.list_models(category=category, enabled_only=enabled_only)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/models/runtime")
async def list_runtime_models(
    category: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    records = await service.list_runtime_models(category=category)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/models/{model_id}")
async def get_model(
    model_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    record = await service.get_model(model_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/models")
async def create_model(
    payload: ModelCatalogCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    data = payload.model_dump(mode="json", exclude_none=True)
    admin_id = data.pop("admin_id", None)
    record = await service.create_model(data, admin_id=admin_id)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.patch("/models/{model_id}")
async def update_model(
    model_id: str,
    payload: ModelCatalogUpdatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    data = payload.model_dump(mode="json", exclude_none=True)
    admin_id = data.pop("admin_id", None)
    record = await service.update_model(model_id, data, admin_id=admin_id)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/models/{model_id}/default")
async def set_default_model(
    model_id: str,
    payload: ModelCatalogDefaultPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    record = await service.set_default_model(model_id, admin_id=payload.admin_id)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/models/{model_id}/health")
async def update_model_health(
    model_id: str,
    payload: ModelCatalogHealthPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceModelCatalogService(uow.required_session, autocommit=False)
    record = await service.update_health(
        model_id,
        status=payload.status,
        error_message=payload.error_message,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)

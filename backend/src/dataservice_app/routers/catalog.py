"""Catalog endpoints for DataService internal API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.catalog.service import DataServiceCatalogService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/catalog",
    tags=["catalog"],
    dependencies=[Depends(require_internal_token)],
)


class CatalogUpsertPayload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    source_path: str | None = None


@router.get("/capabilities")
async def list_capabilities(
    workspace_type: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    records = await service.list_capabilities(
        workspace_type=workspace_type,
        enabled_only=enabled_only,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/capabilities/{workspace_type}/{capability_id}")
async def get_capability(
    workspace_type: str,
    capability_id: str,
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    record = await service.get_capability(
        capability_id=capability_id,
        workspace_type=workspace_type,
        enabled_only=enabled_only,
    )
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.put("/capabilities/{workspace_type}/{capability_id}")
async def upsert_capability(
    workspace_type: str,
    capability_id: str,
    payload: CatalogUpsertPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    data = dict(payload.data)
    data["id"] = capability_id
    data["workspace_type"] = workspace_type
    record = await service.upsert_capability(
        data,
        checksum=payload.checksum,
        source_path=payload.source_path,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/skills")
async def list_skills(
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    records = await service.list_skills(enabled_only=enabled_only)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    record = await service.get_skill(skill_id, enabled_only=enabled_only)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.put("/skills/{skill_id}")
async def upsert_skill(
    skill_id: str,
    payload: CatalogUpsertPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    data = dict(payload.data)
    data["id"] = skill_id
    record = await service.upsert_skill(
        data,
        checksum=payload.checksum,
        source_path=payload.source_path,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))

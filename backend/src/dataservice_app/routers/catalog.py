"""Catalog endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.catalog.seed_loader import DataServiceCatalogSeedLoader
from src.dataservice.domains.catalog.service import DataServiceCatalogService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload,
    CatalogEnabledPayload,
    CatalogSeedLoadPayload,
    CatalogUpsertPayload,
)

router = APIRouter(
    prefix="/internal/v1/catalog",
    tags=["catalog"],
    dependencies=[Depends(require_internal_token)],
)


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


@router.get("/capabilities/exists")
async def has_capabilities(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    return envelope_ok({"exists": await service.has_capabilities()})


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


@router.delete("/capabilities/{workspace_type}/{capability_id}")
async def delete_capability(
    workspace_type: str,
    capability_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    deleted = await service.delete_capability(
        capability_id=capability_id,
        workspace_type=workspace_type,
    )
    await uow.commit()
    return envelope_ok({"deleted": deleted})


@router.patch("/capabilities/{workspace_type}/{capability_id}/enabled")
async def set_capability_enabled(
    workspace_type: str,
    capability_id: str,
    payload: CatalogEnabledPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    record = await service.set_capability_enabled(
        capability_id=capability_id,
        workspace_type=workspace_type,
        enabled=payload.enabled,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/capabilities/seed-load")
async def load_capability_seed_items(
    payload: CatalogSeedLoadPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    loader = DataServiceCatalogSeedLoader(service, payload.seed_root)
    result = await loader.load_capability_items(
        seed_root=payload.seed_root,
        seed_items=[item.model_dump(mode="json") for item in payload.items],
        overwrite=payload.overwrite,
    )
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/skills")
async def list_skills(
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    records = await service.list_skills(enabled_only=enabled_only)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/skills/exists")
async def has_skills(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    return envelope_ok({"exists": await service.has_skills()})


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


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    deleted = await service.delete_skill(skill_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})


@router.patch("/skills/{skill_id}/enabled")
async def set_skill_enabled(
    skill_id: str,
    payload: CatalogEnabledPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    record = await service.set_skill_enabled(skill_id=skill_id, enabled=payload.enabled)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/skills/seed-load")
async def load_skill_seed_items(
    payload: CatalogSeedLoadPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    loader = DataServiceCatalogSeedLoader(service, payload.seed_root)
    result = await loader.load_skill_items(
        seed_root=payload.seed_root,
        seed_items=[item.model_dump(mode="json") for item in payload.items],
        overwrite=payload.overwrite,
    )
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/admin-logs")
async def record_admin_log(
    payload: AdminLogCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    record = await service.record_admin_log(**payload.model_dump())
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/admin-logs")
async def list_admin_logs(
    action: str | None = Query(default=None),
    target_user_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    records, total = await service.list_admin_logs(
        action=action,
        target_user_id=target_user_id,
        offset=offset,
        limit=limit,
    )
    return envelope_ok(
        {
            "items": [record.model_dump(mode="json") for record in records],
            "total": total,
        }
    )

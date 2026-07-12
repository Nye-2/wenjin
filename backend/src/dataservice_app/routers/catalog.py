"""Internal Mission policy catalog API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.catalog.service import MissionCatalogService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.catalog import CatalogSeedLoadPayload

router = APIRouter(
    prefix="/internal/v1/catalog",
    tags=["internal-catalog"],
    dependencies=[Depends(require_internal_token)],
)


def _policy(row):
    return {"id": row.id, "workspace_type": row.workspace_type, "schema_version": row.schema_version, "enabled": row.enabled, "policy_json": row.policy_json, "content_hash": row.content_hash, "source_path": row.source_path}


def _skill(row):
    return {"id": row.id, "schema_version": row.schema_version, "enabled": row.enabled, "skill_json": row.skill_json, "content_hash": row.content_hash, "source_path": row.source_path}


@router.get("/mission-policies")
async def list_mission_policies(workspace_type: str | None = None, enabled_only: bool = Query(False), uow: DataServiceUnitOfWork = Depends(get_uow)):
    service = MissionCatalogService(uow.required_session, autocommit=False)
    return envelope_ok([_policy(item) for item in await service.list_policies(workspace_type=workspace_type, enabled_only=enabled_only)])


@router.get("/mission-policies/exists")
async def has_mission_policies(uow: DataServiceUnitOfWork = Depends(get_uow)):
    return envelope_ok({"exists": await MissionCatalogService(uow.required_session, autocommit=False).has_policies()})


@router.get("/mission-policies/{workspace_type}/{policy_id}")
async def get_mission_policy(workspace_type: str, policy_id: str, uow: DataServiceUnitOfWork = Depends(get_uow)):
    row = await MissionCatalogService(uow.required_session, autocommit=False).get_policy(
        policy_id=policy_id,
        workspace_type=workspace_type,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Mission policy not found")
    return envelope_ok(_policy(row))


@router.post("/mission-policies/seed-load")
async def load_mission_policies(payload: CatalogSeedLoadPayload, uow: DataServiceUnitOfWork = Depends(get_uow)):
    loaded = await MissionCatalogService(uow.required_session, autocommit=False).load_policies([item.model_dump(mode="json") for item in payload.items], overwrite=payload.overwrite)
    await uow.commit()
    return envelope_ok({"loaded": loaded})


@router.get("/worker-skills")
async def list_worker_skills(enabled_only: bool = Query(False), uow: DataServiceUnitOfWork = Depends(get_uow)):
    service = MissionCatalogService(uow.required_session, autocommit=False)
    return envelope_ok([_skill(item) for item in await service.list_skills(enabled_only=enabled_only)])


@router.get("/worker-skills/exists")
async def has_worker_skills(uow: DataServiceUnitOfWork = Depends(get_uow)):
    return envelope_ok({"exists": await MissionCatalogService(uow.required_session, autocommit=False).has_skills()})


@router.get("/worker-skills/{skill_id}")
async def get_worker_skill(skill_id: str, uow: DataServiceUnitOfWork = Depends(get_uow)):
    row = await MissionCatalogService(uow.required_session, autocommit=False).get_skill(skill_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Worker skill not found")
    return envelope_ok(_skill(row))


@router.post("/worker-skills/seed-load")
async def load_worker_skills(payload: CatalogSeedLoadPayload, uow: DataServiceUnitOfWork = Depends(get_uow)):
    loaded = await MissionCatalogService(uow.required_session, autocommit=False).load_skills([item.model_dump(mode="json") for item in payload.items], overwrite=payload.overwrite)
    await uow.commit()
    return envelope_ok({"loaded": loaded})

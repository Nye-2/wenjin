"""Workspace asset endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.asset.contracts import (
    WorkspaceAssetCreateCommand,
    WorkspaceAssetUpdateCommand,
)
from src.dataservice.domains.asset.service import WorkspaceAssetService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/assets",
    tags=["asset"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("")
async def register_asset(
    command: WorkspaceAssetCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.register_asset(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("")
async def list_assets(
    workspace_id: str = Query(),
    asset_kind: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    records = await service.list_assets(
        workspace_id=workspace_id,
        asset_kind=asset_kind,
        source_kind=source_kind,
        source_id=source_id,
        include_deleted=include_deleted,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/{asset_id}")
async def get_asset(
    asset_id: str,
    include_deleted: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.get_asset(asset_id, include_deleted=include_deleted)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: str,
    command: WorkspaceAssetUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.update_asset(asset_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.delete("/{asset_id}")
async def mark_deleted(
    asset_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.mark_deleted(asset_id)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/{asset_id}/download")
async def resolve_download(
    asset_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.resolve_download(asset_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)

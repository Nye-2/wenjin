"""Workspace asset endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.asset.contracts import (
    WorkspaceArtifactCreateCommand,
    WorkspaceArtifactUpdateCommand,
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


@router.post("/artifacts")
async def create_workspace_artifact(
    command: WorkspaceArtifactCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.create_workspace_artifact(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/artifacts")
async def list_workspace_artifacts(
    workspace_id: str = Query(),
    artifact_type: str | None = Query(default=None),
    artifact_types: list[str] | None = Query(default=None),
    status: str | None = Query(default=None),
    created_by_skill: str | None = Query(default=None),
    created_by_skills: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    records = await service.list_workspace_artifacts(
        workspace_id=workspace_id,
        artifact_type=artifact_type,
        artifact_types=artifact_types,
        status=status,
        created_by_skill=created_by_skill,
        created_by_skills=created_by_skills,
        limit=limit,
        offset=offset,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/artifacts/count")
async def count_workspace_artifacts(
    workspace_id: str | None = Query(default=None),
    artifact_type: str | None = Query(default=None),
    created_by_skill: str | None = Query(default=None),
    created_by_skills: list[str] | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    count = await service.count_workspace_artifacts(
        workspace_id=workspace_id,
        artifact_type=artifact_type,
        created_by_skill=created_by_skill,
        created_by_skills=created_by_skills,
    )
    return envelope_ok({"count": count})


@router.get("/artifacts/latest")
async def find_latest_workspace_artifact(
    workspace_id: str = Query(),
    artifact_type: str = Query(),
    title: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.find_latest_workspace_artifact(
        workspace_id=workspace_id,
        artifact_type=artifact_type,
        title=title,
    )
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/artifacts/versions")
async def list_workspace_artifact_versions(
    workspace_id: str = Query(),
    artifact_type: str = Query(),
    title: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    records = await service.list_workspace_artifact_versions(
        workspace_id=workspace_id,
        artifact_type=artifact_type,
        title=title,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/artifacts/{artifact_id}")
async def get_workspace_artifact(
    artifact_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.get_workspace_artifact(artifact_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/artifacts/{artifact_id}/lineage")
async def get_workspace_artifact_lineage(
    artifact_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    records = await service.get_workspace_artifact_lineage(artifact_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.patch("/artifacts/{artifact_id}")
async def update_workspace_artifact(
    artifact_id: str,
    command: WorkspaceArtifactUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    record = await service.update_workspace_artifact(artifact_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.delete("/artifacts/{artifact_id}")
async def delete_workspace_artifact(
    artifact_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceAssetService(uow.required_session, autocommit=False)
    deleted = await service.delete_workspace_artifact(artifact_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})


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

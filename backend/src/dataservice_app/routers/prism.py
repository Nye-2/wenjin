"""Prism endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.prism.contracts import (
    PrismFileVersionCreateCommand,
    PrismPrimaryProjectCommand,
)
from src.dataservice.domains.prism.service import PrismDataDomainService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/prism",
    tags=["prism"],
    dependencies=[Depends(require_internal_token)],
)


@router.put("/workspaces/{workspace_id}/primary")
async def ensure_primary_project(
    workspace_id: str,
    command: PrismPrimaryProjectCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    normalized = command.model_copy(update={"workspace_id": workspace_id})
    record = await service.ensure_primary_project(normalized)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/primary")
async def get_primary_project(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_primary_project(workspace_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/workspaces/{workspace_id}/surface")
async def get_surface(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_surface(workspace_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/files/{file_id}/versions")
async def append_file_version(
    file_id: str,
    command: PrismFileVersionCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    normalized = command.model_copy(update={"file_id": file_id})
    record = await service.append_file_version(normalized)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)

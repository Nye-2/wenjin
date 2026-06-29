"""Hidden workspace memory endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.workspace_memory.contracts import (
    WorkspaceMemoryMergeCommand,
    WorkspaceMemoryRewriteCommand,
)
from src.dataservice.workspace_memory_api import WorkspaceMemoryDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/workspace-memory",
    tags=["workspace-memory"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/workspaces/{workspace_id}")
async def get_workspace_memory(
    workspace_id: str,
    ensure: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceMemoryDataService(uow.required_session, autocommit=False)
    record = (
        await service.ensure_document(workspace_id=workspace_id, created_by="dataservice")
        if ensure
        else await service.get_document(workspace_id)
    )
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.put("/workspaces/{workspace_id}")
async def rewrite_workspace_memory(
    workspace_id: str,
    command: WorkspaceMemoryRewriteCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceMemoryDataService(uow.required_session, autocommit=False)
    record = await service.rewrite_document(command.model_copy(update={"workspace_id": workspace_id}))
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/merge")
async def merge_workspace_memory(
    workspace_id: str,
    command: WorkspaceMemoryMergeCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceMemoryDataService(uow.required_session, autocommit=False)
    record = await service.merge_items(command.model_copy(update={"workspace_id": workspace_id}))
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/revisions")
async def list_workspace_memory_revisions(
    workspace_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = WorkspaceMemoryDataService(uow.required_session, autocommit=False)
    records = await service.list_revisions(workspace_id=workspace_id, limit=limit)
    return envelope_ok([record.model_dump(mode="json") for record in records])

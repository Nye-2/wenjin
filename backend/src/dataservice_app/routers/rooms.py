"""Workspace rooms endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.rooms.contracts import (
    DecisionSetCommand,
    WorkspaceTaskCreateCommand,
    WorkspaceTaskUpdateCommand,
)
from src.dataservice.rooms_api import RoomsDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/rooms",
    tags=["rooms"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/workspaces/{workspace_id}/decisions")
async def list_active_decisions(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    records = await service.list_active_decisions(workspace_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.post("/decisions")
async def set_decision(
    command: DecisionSetCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    record = await service.set_decision(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.delete("/decisions/{decision_id}")
async def delete_decision(
    decision_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    deleted = await service.delete_decision(decision_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})


@router.get("/workspaces/{workspace_id}/tasks")
async def list_workspace_tasks(
    workspace_id: str,
    status: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    records = await service.list_workspace_tasks(workspace_id=workspace_id, status=status)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.post("/tasks")
async def create_workspace_task(
    command: WorkspaceTaskCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    record = await service.create_workspace_task(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.put("/workspaces/{workspace_id}/tasks/{task_id}")
async def update_workspace_task(
    workspace_id: str,
    task_id: str,
    command: WorkspaceTaskUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    record = await service.update_workspace_task(
        workspace_id=workspace_id,
        task_id=task_id,
        command=command,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.delete("/workspaces/{workspace_id}/tasks/{task_id}")
async def delete_workspace_task(
    workspace_id: str,
    task_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = RoomsDataService(uow.required_session, autocommit=False)
    deleted = await service.soft_delete_workspace_task(workspace_id=workspace_id, task_id=task_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})

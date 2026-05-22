"""Workspace endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.workspace.contracts import WorkspaceCreateCommand, WorkspaceUpdateCommand
from src.dataservice.domains.workspace.projection import workspace_to_record
from src.dataservice.domains.workspace.service import DataServiceWorkspaceService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/workspaces",
    tags=["workspace"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("")
async def create_workspace(
    command: WorkspaceCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    workspace = await service.create_workspace(command)
    await uow.commit()
    await uow.required_session.refresh(workspace)
    return envelope_ok(workspace_to_record(workspace).model_dump(mode="json"))


@router.get("")
async def list_workspaces(
    member_user_id: str = Query(min_length=1),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    workspaces = await service.list_workspaces_for_member(member_user_id)
    return envelope_ok([workspace_to_record(workspace).model_dump(mode="json") for workspace in workspaces])


@router.get("/stats/member/{user_id}")
async def get_workspace_stats_for_member(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    stats = await service.get_workspace_stats_for_member(user_id)
    return envelope_ok(stats.model_dump(mode="json"))


@router.get("/stats/admin")
async def get_admin_workspace_stats(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    stats = await service.get_admin_workspace_stats()
    return envelope_ok(stats.model_dump(mode="json"))


@router.get("/stats/member-counts")
async def count_workspaces_by_member_ids(
    user_id: list[str] = Query(default_factory=list),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    counts = await service.count_workspaces_by_member_ids(user_id)
    return envelope_ok(counts)


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    workspace = await service.get_workspace(workspace_id)
    return envelope_ok(workspace_to_record(workspace).model_dump(mode="json") if workspace else None)


@router.get("/{workspace_id}/members/{user_id}/active")
async def has_active_membership(
    workspace_id: str,
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    return envelope_ok(
        {
            "has_active_membership": await service.user_has_active_membership(
                workspace_id=workspace_id,
                user_id=user_id,
            )
        }
    )


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    command: WorkspaceUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    workspace = await service.update_workspace(workspace_id, command)
    if workspace is not None:
        await uow.commit()
        await uow.required_session.refresh(workspace)
    return envelope_ok(workspace_to_record(workspace).model_dump(mode="json") if workspace else None)


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceWorkspaceService(uow.required_session, autocommit=False)
    deleted = await service.delete_workspace(workspace_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})

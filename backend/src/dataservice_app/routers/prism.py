"""Prism endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.prism.contracts import (
    PrismFileContentUpdateCommand,
    PrismFileRestoreCommand,
    PrismFileVersionCreateCommand,
    PrismPrimaryProjectCommand,
    PrismProtectedScopeUpsertCommand,
    PrismWorkspaceFileUpsertCommand,
)
from src.dataservice.domains.prism.service import PrismDataDomainService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.prism import PrismProtectedScopeUpsertPayload

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


@router.post("/workspaces/{workspace_id}/files")
async def upsert_workspace_file(
    workspace_id: str,
    command: PrismWorkspaceFileUpsertCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.upsert_workspace_file(workspace_id=workspace_id, command=command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/files/{file_id}")
async def get_workspace_file(
    workspace_id: str,
    file_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_workspace_file_content(workspace_id=workspace_id, file_id=file_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.put("/workspaces/{workspace_id}/files/{file_id}")
async def update_workspace_file_content(
    workspace_id: str,
    file_id: str,
    command: PrismFileContentUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.append_file_content(
        workspace_id=workspace_id,
        file_id=file_id,
        command=command,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/files/{file_id}/restore")
async def restore_workspace_file_version(
    workspace_id: str,
    file_id: str,
    command: PrismFileRestoreCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.restore_file_version(
        workspace_id=workspace_id,
        file_id=file_id,
        command=command,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.delete("/workspaces/{workspace_id}/files/{file_id}")
async def delete_workspace_file(
    workspace_id: str,
    file_id: str,
    expected_current_hash: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    record = await service.soft_delete_workspace_file(
        workspace_id=workspace_id,
        file_id=file_id,
        expected_current_hash=expected_current_hash,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.put("/workspaces/{workspace_id}/latex-protected-scope")
async def upsert_latex_protected_scope(
    workspace_id: str,
    command: PrismProtectedScopeUpsertPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    project = await service.get_primary_project(workspace_id)
    if project is None or str(project.adapter_ref_id or "") != command.latex_project_id:
        return envelope_ok(None)
    record = await service.upsert_protected_scope(
        PrismProtectedScopeUpsertCommand(
            workspace_id=workspace_id,
            project_id=project.id,
            file_path=command.file_path,
            section_key=command.section_key,
            scope=command.scope,
            reason=command.reason,
            source=command.source,
            metadata_json=command.metadata_json,
        )
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/projects/{project_id}/protected-scopes")
async def list_protected_scopes(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = PrismDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_protected_scopes(project_id, limit=limit)
    return envelope_ok([record.model_dump(mode="json") for record in records])


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

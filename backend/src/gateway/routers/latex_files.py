"""User-owned LaTeX file operations; agent writes use MissionCommitRuntime."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.prism import PrismProtectedScopeUpsertPayload
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.contracts.latex import (
    LatexCreateFolderRequest,
    LatexFileContentResponse,
    LatexFileItem,
    LatexFileOrderRequest,
    LatexProtectedSectionRequest,
    LatexProtectedSectionResponse,
    LatexRenamePathRequest,
    LatexTreeResponse,
    LatexWriteFileRequest,
)
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.latex_helpers import _not_found
from src.services.latex import LatexProjectService

router = APIRouter(prefix="/prism/latex-adapter", tags=["latex"])


async def _owned_project(
    project_id: str,
    *,
    user_id: str,
    dataservice: AsyncDataServiceClient,
):
    project = await LatexProjectService(dataservice=dataservice).get_owned(project_id, user_id)
    if project is None:
        raise _not_found()
    return project


@router.get("/projects/{project_id}/tree", response_model=LatexTreeResponse)
async def get_project_tree(
    project_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexTreeResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    return LatexTreeResponse(
        items=[
            LatexFileItem(
                path=item["path"],
                type=cast(Literal["file", "dir"], item["type"]),
            )
            for item in service.build_tree(project)
        ],
        file_order=dict(project.file_order or {}),
    )


@router.get("/projects/{project_id}/file", response_model=LatexFileContentResponse)
async def read_project_file(
    project_id: str,
    path: str = Query(...),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexFileContentResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    try:
        return LatexFileContentResponse(content=service.read_text_file(project, path))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/projects/{project_id}/file")
async def write_project_file(
    project_id: str,
    request: LatexWriteFileRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, bool]:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    try:
        await service.write_text_file(project, request.path, request.content)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/projects/{project_id}/file-order")
async def save_project_file_order(
    project_id: str,
    request: LatexFileOrderRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, bool]:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    await service.update_file_order(project, request.folder, request.order)
    return {"ok": True}


@router.post(
    "/projects/{project_id}/protected-sections",
    response_model=LatexProtectedSectionResponse,
)
async def protect_project_section(
    project_id: str,
    request: LatexProtectedSectionRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexProtectedSectionResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    workspace_id = str(getattr(project, "workspace_id", "") or "").strip()
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Protected sections require a workspace-owned Prism project",
        )
    try:
        service.read_text_file(project, request.path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    section_key = str(request.section_key or "").strip()
    reason = request.reason or "user_manual_protect"
    protected = await dataservice.upsert_latex_prism_protected_scope(
        PrismProtectedScopeUpsertPayload(
            workspace_id=workspace_id,
            latex_project_id=str(project.id),
            file_path=request.path,
            section_key=section_key,
            scope=request.scope,
            reason=reason,
            source="manual_edit",
        )
    )
    if protected is None:
        raise HTTPException(status_code=409, detail="Workspace Prism project is unavailable")
    return LatexProtectedSectionResponse(
        ok=True,
        protected=True,
        path=request.path,
        section_key=section_key,
        scope=request.scope,
        reason=reason,
    )


@router.post("/projects/{project_id}/folder")
async def create_project_folder(
    project_id: str,
    request: LatexCreateFolderRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, object]:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    try:
        path = await service.create_folder(project, request.path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "path": path}


@router.post("/projects/{project_id}/rename")
async def rename_project_path(
    project_id: str,
    request: LatexRenamePathRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, object]:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    try:
        path = await service.rename_path(project, from_path=request.from_path, to_path=request.to_path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "path": path}


@router.delete("/projects/{project_id}/path")
async def delete_project_path(
    project_id: str,
    path: str = Query(...),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, object]:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    try:
        await service.delete_path(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "path": path}


@router.get("/projects/{project_id}/blob")
async def read_project_blob(
    project_id: str,
    path: str = Query(...),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> Response:
    service = LatexProjectService(dataservice=dataservice)
    project = await _owned_project(project_id, user_id=str(current_user.id), dataservice=dataservice)
    try:
        blob_file, media_type = service.resolve_blob_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=blob_file, media_type=media_type)

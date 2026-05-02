"""LaTeX file and folder endpoints."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.latex import (
    LatexCreateFolderRequest,
    LatexFileChangeActionRequest,
    LatexFileChangeApplyRequest,
    LatexFileChangeApplyResponse,
    LatexFileChangeDiscardResponse,
    LatexFileChangePreviewResponse,
    LatexFileChangeRevertRequest,
    LatexFileChangeRevertResponse,
    LatexFileChangeUndoPayload,
    LatexFileContentResponse,
    LatexFileItem,
    LatexFileOrderRequest,
    LatexRenamePathRequest,
    LatexTreeResponse,
    LatexWriteFileRequest,
)
from src.gateway.deps.core import get_db
from src.gateway.routers.latex_helpers import (
    _compute_file_change_revert_signature,
    _compute_file_change_signature,
    _find_file_change,
    _not_found,
    _pending_content_from_change,
    _preview_file_change_payload,
    _read_project_metadata,
    _record_latex_reference_usage,
    _remove_file_change,
)
from src.services.latex import LatexProjectService
from src.services.latex.rewrite_diff import compute_content_hash

router = APIRouter(prefix="/latex", tags=["latex"])


@router.get("/projects/{project_id}/tree", response_model=LatexTreeResponse)
async def get_project_tree(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexTreeResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    items = [LatexFileItem(**item) for item in service.build_tree(project)]
    return LatexTreeResponse(items=items, file_order=dict(project.file_order or {}))


@router.get("/projects/{project_id}/file", response_model=LatexFileContentResponse)
async def read_project_file(
    project_id: str,
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFileContentResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    try:
        content = service.read_text_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LatexFileContentResponse(content=content)


@router.put("/projects/{project_id}/file")
async def write_project_file(
    project_id: str,
    request: LatexWriteFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    try:
        await service.write_text_file(project, request.path, request.content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/projects/{project_id}/file-order")
async def save_project_file_order(
    project_id: str,
    request: LatexFileOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    await service.update_file_order(project, request.folder, request.order)
    return {"ok": True}


@router.post(
    "/projects/{project_id}/file-changes/preview",
    response_model=LatexFileChangePreviewResponse,
)
async def preview_project_file_change(
    project_id: str,
    request: LatexFileChangeActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFileChangePreviewResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    _llm_config, metadata = _read_project_metadata(project)
    change = _find_file_change(metadata, request.logical_key)
    path = str(change.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File change path missing")
    pending_content = _pending_content_from_change(change)
    try:
        current_content = service.read_text_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _preview_file_change_payload(
        logical_key=request.logical_key,
        path=path,
        reason=str(change.get("reason") or "feature_proposal"),
        current_content=current_content,
        pending_content=pending_content,
    )


@router.post(
    "/projects/{project_id}/file-changes/apply",
    response_model=LatexFileChangeApplyResponse,
)
async def apply_project_file_change(
    project_id: str,
    request: LatexFileChangeApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFileChangeApplyResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    llm_config, metadata = _read_project_metadata(project)
    change = _find_file_change(metadata, request.logical_key)
    path = str(change.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File change path missing")
    pending_content = _pending_content_from_change(change)

    try:
        current_content = service.read_text_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    current_hash = compute_content_hash(current_content)
    pending_hash = compute_content_hash(pending_content)
    expected_signature = _compute_file_change_signature(
        logical_key=request.logical_key,
        path=path,
        current_hash=current_hash,
        pending_hash=pending_hash,
    )
    if not hmac.compare_digest(expected_signature, request.change_signature):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_file_change_signature",
                "message": "File change preview is stale. Re-generate preview before applying.",
                "current_hash": current_hash,
            },
        )

    try:
        await service.write_text_file(project, path, pending_content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    applied_hash = compute_content_hash(pending_content)
    metadata["managed_files"][request.logical_key] = {
        "path": path,
        "content_hash": applied_hash,
        "protected": False,
    }
    _remove_file_change(metadata, request.logical_key)

    previous_hash = compute_content_hash(current_content)
    revert_signature = _compute_file_change_revert_signature(
        logical_key=request.logical_key,
        path=path,
        previous_hash=previous_hash,
        applied_hash=applied_hash,
    )
    metadata["applied_file_changes"][request.logical_key] = {
        "logical_key": request.logical_key,
        "path": path,
        "previous_content": current_content,
        "previous_hash": previous_hash,
        "applied_hash": applied_hash,
        "revert_signature": revert_signature,
    }
    llm_config["metadata"] = metadata
    await service.update_llm_config(project, llm_config)
    await _record_latex_reference_usage(
        db,
        workspace_id=str(llm_config.get("workspace_id") or ""),
        latex_project_id=str(project.id),
        path=path,
        content=pending_content,
    )

    undo = LatexFileChangeUndoPayload(
        logical_key=request.logical_key,
        path=path,
        previous_hash=previous_hash,
        applied_hash=applied_hash,
        revert_signature=revert_signature,
    )
    return LatexFileChangeApplyResponse(
        ok=True,
        applied=True,
        logical_key=request.logical_key,
        path=path,
        file_hash=applied_hash,
        undo=undo,
    )


@router.post(
    "/projects/{project_id}/file-changes/discard",
    response_model=LatexFileChangeDiscardResponse,
)
async def discard_project_file_change(
    project_id: str,
    request: LatexFileChangeActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFileChangeDiscardResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    llm_config, metadata = _read_project_metadata(project)
    change = _find_file_change(metadata, request.logical_key)
    path = str(change.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File change path missing")

    try:
        current_content = service.read_text_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    metadata["managed_files"][request.logical_key] = {
        "path": path,
        "content_hash": compute_content_hash(current_content),
        "protected": True,
    }
    _remove_file_change(metadata, request.logical_key)
    llm_config["metadata"] = metadata
    await service.update_llm_config(project, llm_config)
    return LatexFileChangeDiscardResponse(
        ok=True,
        discarded=True,
        logical_key=request.logical_key,
        path=path,
    )


@router.post(
    "/projects/{project_id}/file-changes/revert",
    response_model=LatexFileChangeRevertResponse,
)
async def revert_project_file_change(
    project_id: str,
    request: LatexFileChangeRevertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFileChangeRevertResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    llm_config, metadata = _read_project_metadata(project)
    applied = metadata["applied_file_changes"].get(request.logical_key)
    if not isinstance(applied, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Applied file change not found")

    path = str(applied.get("path") or "").strip()
    previous_content = applied.get("previous_content")
    previous_hash = str(applied.get("previous_hash") or "")
    applied_hash = str(applied.get("applied_hash") or "")
    if not path or not isinstance(previous_content, str) or not previous_hash or not applied_hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Applied file change is incomplete")

    expected_signature = _compute_file_change_revert_signature(
        logical_key=request.logical_key,
        path=path,
        previous_hash=previous_hash,
        applied_hash=applied_hash,
    )
    if not hmac.compare_digest(expected_signature, request.revert_signature):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_file_change_revert_signature",
                "message": "Invalid file change revert signature.",
            },
        )

    try:
        current_content = service.read_text_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    current_hash = compute_content_hash(current_content)
    if current_hash != applied_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "file_change_revert_hash_mismatch",
                "message": "File changed after applying this change; cannot auto-revert.",
                "current_hash": current_hash,
            },
        )

    try:
        await service.write_text_file(project, path, previous_content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    metadata["managed_files"][request.logical_key] = {
        "path": path,
        "content_hash": previous_hash,
        "protected": True,
    }
    metadata["applied_file_changes"].pop(request.logical_key, None)
    llm_config["metadata"] = metadata
    await service.update_llm_config(project, llm_config)
    return LatexFileChangeRevertResponse(
        ok=True,
        reverted=True,
        logical_key=request.logical_key,
        path=path,
        file_hash=previous_hash,
    )


@router.post("/projects/{project_id}/folder")
async def create_project_folder(
    project_id: str,
    request: LatexCreateFolderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    try:
        path = await service.create_folder(project, request.path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return {"ok": True, "path": path}


@router.post("/projects/{project_id}/rename")
async def rename_project_path(
    project_id: str,
    request: LatexRenamePathRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    try:
        path = await service.rename_path(
            project,
            from_path=request.from_path,
            to_path=request.to_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"ok": True, "path": path}


@router.delete("/projects/{project_id}/path")
async def delete_project_path(
    project_id: str,
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    try:
        await service.delete_path(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "path": path}


@router.get("/projects/{project_id}/blob")
async def read_project_blob(
    project_id: str,
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    try:
        blob_file, media_type = service.resolve_blob_file(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(path=blob_file, media_type=media_type)

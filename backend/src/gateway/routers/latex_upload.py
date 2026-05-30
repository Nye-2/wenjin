"""LaTeX upload endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from src.database import User
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.latex import LatexUploadResponse
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.latex_helpers import (
    _collect_archive_upload_payload,
    _is_reserved_upload_path,
    _normalize_upload_relative_path,
    _not_found,
    _read_upload_bytes_with_limit,
    _sorted_folder_paths,
)
from src.services.latex import LatexProjectService

router = APIRouter(prefix="/prism/latex-adapter", tags=["latex"])

_MAX_UPLOAD_ARCHIVE_BYTES = 256 * 1024 * 1024
_MAX_UPLOAD_FILES = 5000
_MAX_UPLOAD_FILE_BYTES = 128 * 1024 * 1024
_MAX_UPLOAD_TOTAL_BYTES = 512 * 1024 * 1024


@router.post("/projects/{project_id}/upload", response_model=LatexUploadResponse)
async def upload_project_files(
    project_id: str,
    files: list[UploadFile] | None = File(default=None),
    folders: list[str] | None = Form(default=None),
    base_path: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexUploadResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    upload_files = files or []
    if len(upload_files) > _MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Too many files in one upload batch (max {_MAX_UPLOAD_FILES})",
        )

    pending_files: dict[str, bytes] = {}
    pending_folders: set[str] = set()
    skipped_paths: list[str] = []
    total_upload_bytes = 0

    for folder in folders or []:
        try:
            relative_folder = _normalize_upload_relative_path(folder, base_path)
            if not relative_folder:
                continue
            if _is_reserved_upload_path(relative_folder):
                skipped_paths.append(relative_folder)
                continue
            pending_folders.add(relative_folder)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    for upload in upload_files:
        try:
            relative_path = _normalize_upload_relative_path(upload.filename, base_path)
            if not relative_path:
                continue
            if _is_reserved_upload_path(relative_path):
                skipped_paths.append(relative_path)
                continue
            content = await _read_upload_bytes_with_limit(
                upload,
                max_size_bytes=_MAX_UPLOAD_FILE_BYTES,
                error_label="Uploaded file",
            )
            total_upload_bytes += len(content)
            if total_upload_bytes > _MAX_UPLOAD_TOTAL_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        "Upload batch too large. Maximum total size is "
                        f"{_MAX_UPLOAD_TOTAL_BYTES // (1024 * 1024)}MB"
                    ),
                )
            pending_files[relative_path] = content
            parent = Path(relative_path).parent.as_posix()
            if parent not in {"", "."}:
                pending_folders.add(parent)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    saved_files, created_folders = await service.save_uploads(
        project,
        files=list(pending_files.items()),
        folders=_sorted_folder_paths(pending_folders),
    )

    return LatexUploadResponse(
        ok=True,
        files=saved_files,
        folders=created_folders,
        skipped=list(dict.fromkeys(skipped_paths)),
    )


@router.post("/projects/{project_id}/upload-archive", response_model=LatexUploadResponse)
async def upload_project_archive(
    project_id: str,
    archive: UploadFile = File(...),
    base_path: str | None = Form(default=None),
    strip_root: bool = Form(default=True),
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexUploadResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    try:
        archive_bytes = await _read_upload_bytes_with_limit(
            archive,
            max_size_bytes=_MAX_UPLOAD_ARCHIVE_BYTES,
        )
        archive_files, archive_folders, skipped = _collect_archive_upload_payload(
            archive_bytes,
            base_path=base_path,
            strip_root=strip_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        saved_files, created_folders = await service.save_uploads(
            project,
            files=archive_files,
            folders=archive_folders,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return LatexUploadResponse(
        ok=True,
        files=saved_files,
        folders=created_folders,
        skipped=skipped,
    )

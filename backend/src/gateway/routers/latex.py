"""LaTeX module router."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import logging
import mimetypes
import os
import zipfile
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User, WorkspaceReference
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.core import get_db
from src.gateway.contracts.latex import (
    LatexCompileRequest,
    LatexCompileResponse,
    LatexCreateFolderRequest,
    LatexCreateProjectRequest,
    LatexDiffPayload,
    LatexFeedbackAnchorPayload,
    LatexFeedbackItemPayload,
    LatexFeedbackListResponse,
    LatexFeedbackMapRequest,
    LatexFeedbackMapResponse,
    LatexFeedbackRewriteApplyRequest,
    LatexFeedbackRewriteApplyResponse,
    LatexFeedbackRewriteCandidatePayload,
    LatexFeedbackRewritePreviewResponse,
    LatexFeedbackRewriteRequest,
    LatexFeedbackRewriteResponse,
    LatexFeedbackRewriteRevertRequest,
    LatexFeedbackRewriteRevertResponse,
    LatexFeedbackRewriteUndoPayload,
    LatexFeedbackSaveRequest,
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
    LatexProjectListResponse,
    LatexProjectResponse,
    LatexRenamePathRequest,
    LatexTemplateListResponse,
    LatexTemplateResponse,
    LatexTreeResponse,
    LatexUpdateProjectRequest,
    LatexUploadResponse,
    LatexWriteFileRequest,
    RewriteProfile,
    RewriteRiskLevel,
    _MAX_REWRITE_CANDIDATES,
    _REWRITE_CANDIDATE_TIMEOUT_SECONDS,
    _REWRITE_PROFILE_GUIDANCE,
    _REWRITE_PROFILE_ORDER,
    get_default_latex_engine,
)
from src.services.latex import (
    LatexCompileService,
    LatexProjectService,
    LatexTemplateService,
)
from src.services.latex.engine_config import get_supported_latex_engines
from src.services.latex.feedback_revision_service import (
    build_feedback_anchor,
    resolve_feedback_range,
    resolve_section_by_offset,
    rewrite_with_feedback,
)
from src.services.latex.paths import is_reserved_project_path, normalize_relative_path
from src.services.latex.project_service import (
    LatexTemplateError,
    LatexTemplateNotFoundError,
)
from src.services.latex.rewrite_diff import (
    build_latex_rewrite_diff,
    compute_content_hash,
    compute_range_hash,
)
from src.services.latex.rewrite_guard import (
    LatexStructureValidationError,
    validate_latex_document_structure,
    validate_rewrite_segment,
)
from src.services.references import ReferenceUsageService
from src.services.references.utils import extract_citation_keys_from_text
from src.gateway.routers.latex_helpers import (
    _build_rewrite_candidate,
    _candidate_risk_level,
    _collect_archive_upload_payload,
    _common_upload_root_prefix,
    _compute_candidate_signature,
    _compute_file_change_revert_signature,
    _compute_file_change_signature,
    _compute_revert_signature,
    _find_file_change,
    _generate_rewrite_candidates,
    _is_reserved_upload_path,
    _normalize_upload_relative_path,
    _not_found,
    _pending_content_from_change,
    _preview_file_change_payload,
    _profiled_comment,
    _read_feedback_items_from_project,
    _read_project_metadata,
    _read_upload_bytes_with_limit,
    _record_latex_reference_usage,
    _remove_file_change,
    _rewrite_compile_guard_enabled,
    _rewrite_signature_secret,
    _sorted_folder_paths,
    _write_feedback_items_to_project,
)


router = APIRouter(prefix="/latex", tags=["latex"])
logger = logging.getLogger(__name__)

_MAX_UPLOAD_ARCHIVE_BYTES = 256 * 1024 * 1024
_MAX_UPLOAD_FILES = 5000
_MAX_UPLOAD_FILE_BYTES = 128 * 1024 * 1024
_MAX_UPLOAD_TOTAL_BYTES = 512 * 1024 * 1024

@router.get("/health")
async def latex_health() -> dict[str, str]:
    """Module health endpoint."""
    return {"status": "ok", "module": "latex"}


@router.get("/projects", response_model=LatexProjectListResponse)
async def list_projects(
    include_trashed: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexProjectListResponse:
    service = LatexProjectService(db)
    projects = await service.list_by_user(str(current_user.id), include_trashed=include_trashed)
    return LatexProjectListResponse(projects=projects)


@router.post("/projects", response_model=LatexProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: LatexCreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexProjectResponse:
    service = LatexProjectService(db)
    try:
        project = await service.create(
            user_id=str(current_user.id),
            name=request.name,
            template_id=request.template_id,
        )
    except LatexTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LatexTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LatexProjectResponse.model_validate(project)


@router.get("/projects/{project_id}", response_model=LatexProjectResponse)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexProjectResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    return LatexProjectResponse.model_validate(project)


@router.patch("/projects/{project_id}", response_model=LatexProjectResponse)
async def update_project(
    project_id: str,
    request: LatexUpdateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexProjectResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    updated = await service.update(project, **request.model_dump(exclude_unset=True))
    return LatexProjectResponse.model_validate(updated)


@router.delete("/projects/{project_id}")
async def soft_delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    await service.soft_delete(project)
    return {"ok": True}


@router.delete("/projects/{project_id}/permanent")
async def permanent_delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    await service.permanent_delete(project)
    return {"ok": True}


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


@router.get("/projects/{project_id}/feedback", response_model=LatexFeedbackListResponse)
async def get_project_feedback(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFeedbackListResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    raw_items = _read_feedback_items_from_project(project.llm_config)
    items: list[LatexFeedbackItemPayload] = []
    for raw in raw_items:
        try:
            items.append(LatexFeedbackItemPayload.model_validate(raw))
        except Exception:
            continue
    return LatexFeedbackListResponse(ok=True, items=items)


@router.put("/projects/{project_id}/feedback")
async def save_project_feedback(
    project_id: str,
    request: LatexFeedbackSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    payload = [item.model_dump(mode="json") for item in request.items]
    await _write_feedback_items_to_project(service=service, project=project, items=payload)
    return {"ok": True}


@router.post(
    "/projects/{project_id}/feedback/rewrite/preview",
    response_model=LatexFeedbackRewritePreviewResponse,
)
async def preview_project_feedback_rewrite(
    project_id: str,
    request: LatexFeedbackRewriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFeedbackRewritePreviewResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    try:
        source_content = (
            request.file_content
            if request.file_content is not None
            else service.read_text_file(project, request.file_path)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        candidate_pairs = await _generate_rewrite_candidates(
            source_content=str(source_content),
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    candidates = [pair[0] for pair in candidate_pairs]
    primary_result = candidate_pairs[0][1]
    return LatexFeedbackRewritePreviewResponse(
        ok=True,
        file_path=request.file_path,
        resolved_selection_start=int(primary_result["resolved_selection_start"]),
        resolved_selection_end=int(primary_result["resolved_selection_end"]),
        candidates=candidates,
    )


@router.post(
    "/projects/{project_id}/feedback/rewrite/apply",
    response_model=LatexFeedbackRewriteApplyResponse,
)
async def apply_project_feedback_rewrite(
    project_id: str,
    request: LatexFeedbackRewriteApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFeedbackRewriteApplyResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    if request.target_end < request.target_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target range")

    try:
        current_content = service.read_text_file(project, request.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    expected_signature = _compute_candidate_signature(
        file_path=request.file_path,
        candidate_id=request.candidate_id,
        target_start=request.target_start,
        target_end=request.target_end,
        rewritten_text=request.rewritten_text,
        base_file_hash=request.base_file_hash,
        base_range_hash=request.base_range_hash,
    )
    if not hmac.compare_digest(expected_signature, request.candidate_signature):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_candidate_signature",
                "message": "Rewrite candidate signature mismatch. Re-generate rewrite preview.",
            },
        )

    current_hash = compute_content_hash(current_content)
    if current_hash != request.base_file_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "base_file_hash_mismatch",
                "message": "File content changed. Re-generate rewrite preview.",
                "current_file_hash": current_hash,
            },
        )

    if request.target_end > len(current_content):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "target_range_out_of_bounds",
                "message": "Target range is no longer valid. Re-generate rewrite preview.",
            },
        )

    current_segment = current_content[request.target_start:request.target_end]
    current_range_hash = compute_range_hash(
        request.target_start,
        request.target_end,
        current_segment,
    )
    if current_range_hash != request.base_range_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "base_range_hash_mismatch",
                "message": "Target range changed. Re-generate rewrite preview.",
                "current_range_hash": current_range_hash,
            },
        )

    try:
        validate_rewrite_segment(
            original_text=current_segment,
            rewritten_text=request.rewritten_text,
            scope=None,
        )
    except LatexStructureValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": f"Rewrite rejected by structure guard: {exc.message}",
            },
        ) from exc

    applied_content = (
        current_content[:request.target_start]
        + request.rewritten_text
        + current_content[request.target_end:]
    )
    try:
        validate_latex_document_structure(applied_content)
    except LatexStructureValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": f"Rewrite rejected by document structure guard: {exc.message}",
            },
        ) from exc

    try:
        await service.write_text_file(project, request.file_path, applied_content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    compile_error: str | None = None
    if _rewrite_compile_guard_enabled():
        compile_service = LatexCompileService(db)
        compile_errors: list[str] = []
        ordered_engines: list[str] = [get_default_latex_engine()]
        for engine in get_supported_latex_engines():
            if engine not in ordered_engines:
                ordered_engines.append(engine)
        for engine in ordered_engines:
            try:
                compile_payload = await compile_service.compile_project(
                    project,
                    main_file=project.main_file,
                    engine=engine,
                    record_history=False,
                )
                if bool(compile_payload.get("ok")):
                    compile_errors = []
                    break
                error_message = str(
                    compile_payload.get("error")
                    or compile_payload.get("log")
                    or "No PDF generated.",
                ).strip()
            except Exception as exc:
                error_message = str(exc).strip() or "Compile validation failed."
            compile_errors.append(f"{engine}: {error_message}")
        if compile_errors:
            compile_error = " | ".join(compile_errors)

    if compile_error:
        try:
            await service.write_text_file(project, request.file_path, current_content)
        except Exception as rollback_exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "rewrite_compile_rollback_failed",
                    "message": "Rewrite compile validation failed and rollback also failed.",
                    "compile_error": compile_error,
                    "rollback_error": str(rollback_exc),
                },
            ) from rollback_exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "rewrite_compile_failed",
                "message": "Rewrite rejected because project no longer compiles. Changes were rolled back.",
                "compile_error": compile_error,
            },
        )

    next_end = request.target_start + len(request.rewritten_text)
    updated_anchor = build_feedback_anchor(
        applied_content,
        request.target_start,
        next_end,
    )
    applied_file_hash = compute_content_hash(applied_content)
    undo_payload = LatexFeedbackRewriteUndoPayload(
        candidate_id=request.candidate_id,
        revert_start=request.target_start,
        revert_end=next_end,
        rewritten_text=request.rewritten_text,
        previous_text=current_segment,
        applied_file_hash=applied_file_hash,
        revert_signature=_compute_revert_signature(
            file_path=request.file_path,
            candidate_id=request.candidate_id,
            revert_start=request.target_start,
            revert_end=next_end,
            rewritten_text=request.rewritten_text,
            previous_text=current_segment,
            applied_file_hash=applied_file_hash,
        ),
    )
    return LatexFeedbackRewriteApplyResponse(
        ok=True,
        applied=True,
        file_path=request.file_path,
        candidate_id=request.candidate_id,
        target_start=request.target_start,
        target_end=request.target_end,
        rewritten_text=request.rewritten_text,
        applied_content=applied_content,
        updated_anchor=LatexFeedbackAnchorPayload.model_validate(updated_anchor),
        file_hash=applied_file_hash,
        undo=undo_payload,
    )


@router.post(
    "/projects/{project_id}/feedback/rewrite/revert",
    response_model=LatexFeedbackRewriteRevertResponse,
)
async def revert_project_feedback_rewrite(
    project_id: str,
    request: LatexFeedbackRewriteRevertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFeedbackRewriteRevertResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    if request.revert_end < request.revert_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid revert range")

    try:
        current_content = service.read_text_file(project, request.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    expected_signature = _compute_revert_signature(
        file_path=request.file_path,
        candidate_id=request.candidate_id,
        revert_start=request.revert_start,
        revert_end=request.revert_end,
        rewritten_text=request.rewritten_text,
        previous_text=request.previous_text,
        applied_file_hash=request.applied_file_hash,
    )
    if not hmac.compare_digest(expected_signature, request.revert_signature):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_revert_signature",
                "message": "Invalid revert signature. Re-generate rewrite preview.",
            },
        )

    current_hash = compute_content_hash(current_content)
    if current_hash != request.applied_file_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "revert_file_hash_mismatch",
                "message": "File content changed, cannot auto-revert this rewrite.",
                "current_file_hash": current_hash,
            },
        )

    if request.revert_end > len(current_content):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "revert_range_out_of_bounds",
                "message": "Revert range is no longer valid.",
            },
        )

    current_segment = current_content[request.revert_start:request.revert_end]
    if current_segment != request.rewritten_text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "revert_target_mismatch",
                "message": "Current text no longer matches the applied rewrite.",
            },
        )

    reverted_content = (
        current_content[:request.revert_start]
        + request.previous_text
        + current_content[request.revert_end:]
    )
    try:
        await service.write_text_file(project, request.file_path, reverted_content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    restored_end = request.revert_start + len(request.previous_text)
    updated_anchor = build_feedback_anchor(
        reverted_content,
        request.revert_start,
        restored_end,
    )
    return LatexFeedbackRewriteRevertResponse(
        ok=True,
        reverted=True,
        file_path=request.file_path,
        candidate_id=request.candidate_id,
        revert_start=request.revert_start,
        revert_end=request.revert_end,
        restored_text=request.previous_text,
        reverted_content=reverted_content,
        updated_anchor=LatexFeedbackAnchorPayload.model_validate(updated_anchor),
        file_hash=compute_content_hash(reverted_content),
    )


@router.post("/projects/{project_id}/feedback/rewrite", response_model=LatexFeedbackRewriteResponse)
async def rewrite_project_feedback(
    project_id: str,
    request: LatexFeedbackRewriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFeedbackRewriteResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    try:
        source_content = (
            request.file_content
            if request.file_content is not None
            else service.read_text_file(project, request.file_path)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        rewrite_result = await rewrite_with_feedback(
            content=str(source_content),
            comment=request.comment,
            selected_text=request.selected_text,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
            anchor=request.anchor.model_dump(mode="json") if request.anchor else None,
            scope=request.scope,
            requested_model_id=request.model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    try:
        candidate = _build_rewrite_candidate(
            source_content=str(source_content),
            file_path=request.file_path,
            scope=request.scope,
            profile="balanced",
            rewrite_result=rewrite_result,
        )
    except LatexStructureValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": f"Rewrite rejected by structure guard: {exc.message}",
            },
        ) from exc

    applied = False
    if request.apply:
        try:
            await service.write_text_file(project, request.file_path, candidate.proposed_content)
            applied = True
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return LatexFeedbackRewriteResponse(
        ok=True,
        model_id=candidate.model_id,
        scope=candidate.scope,
        file_path=request.file_path,
        section_title=candidate.section_title,
        section_level=candidate.section_level,
        resolved_selection_start=int(rewrite_result["resolved_selection_start"]),
        resolved_selection_end=int(rewrite_result["resolved_selection_end"]),
        target_start=candidate.target_start,
        target_end=candidate.target_end,
        rewritten_text=candidate.rewritten_text,
        changes_summary=candidate.changes_summary,
        proposed_content=candidate.proposed_content,
        updated_anchor=candidate.updated_anchor,
        applied=applied,
    )


@router.post("/projects/{project_id}/feedback/map", response_model=LatexFeedbackMapResponse)
async def map_project_feedback_selection(
    project_id: str,
    request: LatexFeedbackMapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexFeedbackMapResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    target_file_path = request.file_path
    source_content: str = ""
    mapping_method: Literal["synctex", "text_fallback"] = "text_fallback"

    if (
        request.source == "pdf"
        and isinstance(request.pdf_anchor, dict)
        and request.history_id
    ):
        page = int(request.pdf_anchor.get("page") or 0)
        rects = request.pdf_anchor.get("rects")
        if page > 0 and isinstance(rects, list) and rects:
            first_rect = rects[0] if isinstance(rects[0], dict) else {}
            width = float(first_rect.get("width") or 0.0)
            height = float(first_rect.get("height") or 0.0)
            x = float(first_rect.get("x") or 0.0) + width / 2.0
            y = float(first_rect.get("y") or 0.0) + height / 2.0
            try:
                compile_service = LatexCompileService(db)
                mapped = await compile_service.map_pdf_point_to_source(
                    history_id=request.history_id,
                    project_id=project_id,
                    page=page,
                    x=max(0.0, x),
                    y=max(0.0, y),
                )
            except RuntimeError:
                mapped = None
            if mapped is not None:
                try:
                    mapped_path = str(mapped.get("file_path") or "").strip()
                    if mapped_path:
                        target_file_path = mapped_path
                    source_content = service.read_text_file(project, target_file_path)
                    synctex_line = int(mapped.get("line") or 1)
                    synctex_column = int(mapped.get("column") or 1)
                    synctex_offset = LatexCompileService._line_column_to_offset(
                        source_content,
                        synctex_line,
                        synctex_column,
                    )
                    resolved = resolve_feedback_range(
                        content=source_content,
                        selected_text=request.selected_text,
                        start=synctex_offset,
                        end=synctex_offset + len(request.selected_text),
                        anchor=request.anchor.model_dump(mode="json") if request.anchor else None,
                    )
                    if resolved is not None:
                        section = resolve_section_by_offset(source_content, resolved.start)
                        updated_anchor = build_feedback_anchor(
                            source_content,
                            resolved.start,
                            resolved.end,
                        )
                        return LatexFeedbackMapResponse(
                            ok=True,
                            file_path=target_file_path,
                            resolved_selection_start=resolved.start,
                            resolved_selection_end=resolved.end,
                            selected_text=resolved.text,
                            updated_anchor=LatexFeedbackAnchorPayload.model_validate(updated_anchor),
                            section_title=section.title,
                            section_level=section.level,
                            mapping_method="synctex",
                            pdf_anchor=request.pdf_anchor,
                        )
                except (ValueError, FileNotFoundError):
                    pass

    try:
        source_content = source_content or (
            request.file_content
            if request.file_content is not None
            else service.read_text_file(project, target_file_path)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    resolved = resolve_feedback_range(
        content=source_content,
        selected_text=request.selected_text,
        start=request.selection_start,
        end=request.selection_end,
        anchor=request.anchor.model_dump(mode="json") if request.anchor else None,
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unable to locate selected text in current file",
        )

    section = resolve_section_by_offset(source_content, resolved.start)
    updated_anchor = build_feedback_anchor(source_content, resolved.start, resolved.end)
    response_pdf_anchor: dict[str, Any] | None = request.pdf_anchor
    if request.source == "tex" and request.history_id:
        try:
            line, column = LatexCompileService._offset_to_line_column(
                source_content,
                resolved.start,
            )
            compile_service = LatexCompileService(db)
            mapped_pdf = await compile_service.map_source_line_to_pdf(
                history_id=request.history_id,
                project_id=project_id,
                relative_file_path=target_file_path,
                line=line,
                column=column,
            )
            if mapped_pdf is not None:
                norm_x = mapped_pdf.get("normalized_x")
                norm_y = mapped_pdf.get("normalized_y")
                if isinstance(norm_x, (int, float)) and isinstance(norm_y, (int, float)):
                    response_pdf_anchor = {
                        "page": int(mapped_pdf.get("page") or 1),
                        "text": resolved.text,
                        "rects": [
                            {
                                "x": max(0.0, min(1.0, float(norm_x))),
                                "y": max(0.0, min(1.0, float(norm_y))),
                                "width": 0.02,
                                "height": 0.02,
                            }
                        ],
                    }
                    mapping_method = "synctex"
        except RuntimeError:
            pass

    return LatexFeedbackMapResponse(
        ok=True,
        file_path=target_file_path,
        resolved_selection_start=resolved.start,
        resolved_selection_end=resolved.end,
        selected_text=resolved.text,
        updated_anchor=LatexFeedbackAnchorPayload.model_validate(updated_anchor),
        section_title=section.title,
        section_level=section.level,
        mapping_method=mapping_method,
        pdf_anchor=response_pdf_anchor,
    )


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


@router.post("/projects/{project_id}/upload", response_model=LatexUploadResponse)
async def upload_project_files(
    project_id: str,
    files: list[UploadFile] | None = File(default=None),
    folders: list[str] | None = Form(default=None),
    base_path: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexUploadResponse:
    service = LatexProjectService(db)
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
    db: AsyncSession = Depends(get_db),
) -> LatexUploadResponse:
    service = LatexProjectService(db)
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


@router.post("/projects/{project_id}/compile", response_model=LatexCompileResponse)
async def compile_project(
    project_id: str,
    request: LatexCompileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexCompileResponse:
    project_service = LatexProjectService(db)
    project = await project_service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    compile_service = LatexCompileService(db)
    try:
        payload = await compile_service.compile_project(
            project,
            main_file=request.main_file,
            engine=request.engine,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LatexCompileResponse(**payload)


@router.get("/projects/{project_id}/compile/{history_id}/pdf")
async def get_compiled_pdf(
    project_id: str,
    history_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    project_service = LatexProjectService(db)
    project = await project_service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    compile_service = LatexCompileService(db)
    pdf_path = await compile_service.get_history_pdf(
        history_id=history_id,
        project_id=project_id,
    )
    if pdf_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compiled PDF not found")

    media_type = mimetypes.guess_type(pdf_path.name)[0] or "application/pdf"
    encoded_filename = quote(pdf_path.name)
    return FileResponse(
        path=pdf_path,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"
        },
    )


@router.get("/projects/{project_id}/compile/{history_id}/synctex")
async def get_compiled_synctex(
    project_id: str,
    history_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    project_service = LatexProjectService(db)
    project = await project_service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    compile_service = LatexCompileService(db)
    synctex_path = await compile_service.get_history_synctex(
        history_id=history_id,
        project_id=project_id,
    )
    if synctex_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Synctex file not found")

    media_type = mimetypes.guess_type(synctex_path.name)[0] or "application/gzip"
    encoded_filename = quote(synctex_path.name)
    return FileResponse(
        path=synctex_path,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )


@router.get("/templates", response_model=LatexTemplateListResponse)
async def list_templates(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexTemplateListResponse:
    service = LatexTemplateService(db)
    templates = await service.list_templates()
    return LatexTemplateListResponse(templates=templates)

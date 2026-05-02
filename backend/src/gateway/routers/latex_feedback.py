"""LaTeX feedback and rewrite endpoints."""

from __future__ import annotations

import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.core import get_db
from src.gateway.contracts.latex import (
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
    get_default_latex_engine,
)
from src.gateway.routers.latex_helpers import (
    _build_rewrite_candidate,
    _compute_candidate_signature,
    _compute_revert_signature,
    _generate_rewrite_candidates,
    _not_found,
    _read_feedback_items_from_project,
    _rewrite_compile_guard_enabled,
    _write_feedback_items_to_project,
)
from src.services.latex import LatexCompileService, LatexProjectService
from src.services.latex.engine_config import get_supported_latex_engines
from src.services.latex.feedback_revision_service import (
    build_feedback_anchor,
    resolve_feedback_range,
    resolve_section_by_offset,
    rewrite_with_feedback,
)
from src.services.latex.rewrite_diff import compute_content_hash, compute_range_hash
from src.services.latex.rewrite_guard import (
    LatexStructureValidationError,
    validate_latex_document_structure,
    validate_rewrite_segment,
)

router = APIRouter(prefix="/latex", tags=["latex"])


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

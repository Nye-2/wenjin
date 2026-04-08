"""LaTeX module router."""

from __future__ import annotations

import mimetypes
from copy import deepcopy
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.core import get_db
from src.services.latex.paths import normalize_relative_path
from src.services.latex import (
    LatexCompileService,
    LatexProjectService,
    LatexTemplateService,
    get_default_latex_engine,
)
from src.services.latex.feedback_revision_service import (
    build_feedback_anchor,
    resolve_feedback_range,
    resolve_section_by_offset,
    rewrite_with_feedback,
)

router = APIRouter(prefix="/latex", tags=["latex"])


class LatexProjectResponse(BaseModel):
    """LaTeX project response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    template_id: str | None
    main_file: str
    tags: list[str]
    archived: bool
    trashed: bool
    trashed_at: datetime | None
    file_order: dict[str, list[str]]
    llm_config: dict | None
    created_at: datetime
    updated_at: datetime


class LatexProjectListResponse(BaseModel):
    """List response for LaTeX projects."""

    projects: list[LatexProjectResponse]


class LatexCreateProjectRequest(BaseModel):
    """Create payload."""

    name: str = Field(min_length=1, max_length=255)
    template_id: str | None = Field(default=None, max_length=50)


class LatexUpdateProjectRequest(BaseModel):
    """Update payload."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    template_id: str | None = Field(default=None, max_length=50)
    main_file: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    archived: bool | None = None
    trashed: bool | None = None
    file_order: dict[str, list[str]] | None = None


class LatexFileItem(BaseModel):
    """File tree item."""

    path: str
    type: Literal["file", "dir"]


class LatexTreeResponse(BaseModel):
    """Tree response."""

    items: list[LatexFileItem]
    file_order: dict[str, list[str]]


class LatexFileContentResponse(BaseModel):
    """Text file payload."""

    content: str


class LatexWriteFileRequest(BaseModel):
    """Write file payload."""

    path: str = Field(min_length=1)
    content: str = ""


class LatexCreateFolderRequest(BaseModel):
    """Create folder payload."""

    path: str = Field(min_length=1)


class LatexRenamePathRequest(BaseModel):
    """Rename payload."""

    from_path: str = Field(alias="from", min_length=1)
    to_path: str = Field(alias="to", min_length=1)


class LatexFileOrderRequest(BaseModel):
    """File order payload."""

    folder: str = ""
    order: list[str]


class LatexResolveConflictRequest(BaseModel):
    """Conflict resolution payload."""

    logical_key: str = Field(min_length=1)
    strategy: Literal["keep_current", "accept_feature"] = "keep_current"
    feature_content: str | None = None


class LatexCompileRequest(BaseModel):
    """Compile request."""

    main_file: str | None = Field(default=None, max_length=255)
    engine: Literal["xelatex", "pdflatex"] = Field(default_factory=get_default_latex_engine)


class LatexCompileResponse(BaseModel):
    """Compile response."""

    ok: bool
    status: int
    engine: str
    main_file: str
    pdf_path: str | None
    pdf_endpoint: str | None
    log: str | None
    error: str | None
    history_id: str
    page_count: int | None


class LatexTemplateResponse(BaseModel):
    """Template payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    main_file: str
    category: str
    description: str | None
    description_en: str | None
    tags: list[str]
    author: str | None
    featured: bool
    template_path: str | None


class LatexTemplateListResponse(BaseModel):
    """Template list response."""

    templates: list[LatexTemplateResponse]


class LatexUploadResponse(BaseModel):
    """Upload response."""

    ok: bool = True
    files: list[str]


class LatexFeedbackAnchorPayload(BaseModel):
    """Anchor used to re-locate feedback ranges after edits."""

    selected_text: str = ""
    prefix: str = ""
    suffix: str = ""
    heading_title: str = ""
    heading_level: str = ""
    line_hint: int = 1


class LatexFeedbackItemPayload(BaseModel):
    """Stored feedback item in LaTeX project metadata."""

    id: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    selected_text: str = ""
    comment: str = Field(min_length=1)
    created_at: datetime | None = None
    anchor: LatexFeedbackAnchorPayload | None = None
    source: Literal["tex", "pdf"] = "tex"
    pdf_anchor: dict[str, Any] | None = None
    tex_anchor: dict[str, Any] | None = None
    last_status: Literal["idle", "pending", "done", "error"] | None = None
    last_error: str | None = None


class LatexFeedbackListResponse(BaseModel):
    """Feedback list response."""

    ok: bool = True
    items: list[LatexFeedbackItemPayload]


class LatexFeedbackSaveRequest(BaseModel):
    """Feedback write request."""

    items: list[LatexFeedbackItemPayload]


class LatexFeedbackRewriteRequest(BaseModel):
    """Rewrite request from one feedback item."""

    file_path: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    comment: str = Field(min_length=1)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    anchor: LatexFeedbackAnchorPayload | None = None
    scope: Literal["selection", "section"] = "section"
    model_id: str | None = None
    file_content: str | None = None
    apply: bool = False


class LatexFeedbackRewriteResponse(BaseModel):
    """Rewrite preview/apply response."""

    ok: bool = True
    model_id: str
    scope: Literal["selection", "section"]
    file_path: str
    section_title: str
    section_level: str
    resolved_selection_start: int
    resolved_selection_end: int
    target_start: int
    target_end: int
    rewritten_text: str
    changes_summary: str
    proposed_content: str
    updated_anchor: LatexFeedbackAnchorPayload
    applied: bool = False


class LatexFeedbackMapRequest(BaseModel):
    """Map feedback selection back to a TeX range."""

    file_path: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    anchor: LatexFeedbackAnchorPayload | None = None
    history_id: str | None = None
    pdf_anchor: dict[str, Any] | None = None
    file_content: str | None = None
    source: Literal["tex", "pdf"] = "pdf"


class LatexFeedbackMapResponse(BaseModel):
    """Resolved TeX mapping result."""

    ok: bool = True
    file_path: str
    resolved_selection_start: int
    resolved_selection_end: int
    selected_text: str
    updated_anchor: LatexFeedbackAnchorPayload
    section_title: str
    section_level: str
    mapping_method: Literal["synctex", "text_fallback"]
    pdf_anchor: dict[str, Any] | None = None


def _normalize_upload_relative_path(filename: str | None, base_path: str | None) -> str:
    """Normalize upload filename against optional base path without double-prefixing."""
    normalized_name = str(filename or "").replace("\\", "/").strip().lstrip("/")
    if not normalized_name:
        return ""
    normalized_base = str(base_path or "").replace("\\", "/").strip().strip("/")
    if not normalized_base:
        return normalize_relative_path(normalized_name)
    if (
        normalized_name == normalized_base
        or normalized_name.startswith(f"{normalized_base}/")
    ):
        merged = normalized_name
    else:
        merged = f"{normalized_base}/{normalized_name}"
    return normalize_relative_path(merged)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _read_feedback_items_from_project(project_llm_config: dict | None) -> list[dict[str, Any]]:
    llm_config = deepcopy(project_llm_config) if isinstance(project_llm_config, dict) else {}
    metadata = llm_config.get("metadata")
    if not isinstance(metadata, dict):
        return []
    items = metadata.get("feedback_items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


async def _write_feedback_items_to_project(
    *,
    service: LatexProjectService,
    project: Any,
    items: list[dict[str, Any]],
) -> None:
    llm_config = deepcopy(project.llm_config) if isinstance(project.llm_config, dict) else {}
    metadata = deepcopy(llm_config.get("metadata")) if isinstance(llm_config.get("metadata"), dict) else {}
    metadata["feedback_items"] = items
    metadata["feedback_updated_at"] = datetime.now().isoformat()
    llm_config["metadata"] = metadata
    await service.update_llm_config(project, llm_config)


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
    project = await service.create(
        user_id=str(current_user.id),
        name=request.name,
        template_id=request.template_id,
    )
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

    target_start = int(rewrite_result["target_start"])
    target_end = int(rewrite_result["target_end"])
    rewritten_text = str(rewrite_result["rewritten_text"])
    proposed_content = (
        str(source_content)[:target_start]
        + rewritten_text
        + str(source_content)[target_end:]
    )
    updated_anchor = build_feedback_anchor(
        proposed_content,
        target_start,
        target_start + len(rewritten_text),
    )

    applied = False
    if request.apply:
        try:
            await service.write_text_file(project, request.file_path, proposed_content)
            applied = True
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return LatexFeedbackRewriteResponse(
        ok=True,
        model_id=str(rewrite_result.get("model_id") or "default"),
        scope=request.scope,
        file_path=request.file_path,
        section_title=str(rewrite_result.get("section_title") or "未命名章节"),
        section_level=str(rewrite_result.get("section_level") or "section"),
        resolved_selection_start=int(rewrite_result["resolved_selection_start"]),
        resolved_selection_end=int(rewrite_result["resolved_selection_end"]),
        target_start=target_start,
        target_end=target_end,
        rewritten_text=rewritten_text,
        changes_summary=str(rewrite_result.get("changes_summary") or ""),
        proposed_content=proposed_content,
        updated_anchor=LatexFeedbackAnchorPayload.model_validate(updated_anchor),
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


@router.post("/projects/{project_id}/resolve-conflict")
async def resolve_project_conflict(
    project_id: str,
    request: LatexResolveConflictRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    llm_config = deepcopy(project.llm_config) if isinstance(project.llm_config, dict) else {}
    metadata = deepcopy(llm_config.get("metadata")) if isinstance(llm_config.get("metadata"), dict) else {}
    conflicts = deepcopy(metadata.get("sync_conflicts")) if isinstance(metadata.get("sync_conflicts"), list) else []
    managed_files = deepcopy(metadata.get("managed_files")) if isinstance(metadata.get("managed_files"), dict) else {}

    conflict = next(
        (
            item for item in conflicts
            if isinstance(item, dict) and str(item.get("logical_key") or "") == request.logical_key
        ),
        None,
    )
    if conflict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")

    path = str(conflict.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conflict path missing")

    import hashlib

    if request.strategy == "accept_feature":
        feature_content = request.feature_content
        if feature_content is None and isinstance(conflict, dict):
            pending = conflict.get("pending_content")
            if isinstance(pending, str):
                feature_content = pending
        if feature_content is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing feature content")
        await service.write_text_file(project, path, feature_content)

        managed_files[request.logical_key] = {
            "path": path,
            "content_hash": hashlib.sha256(feature_content.encode("utf-8")).hexdigest(),
            "protected": False,
        }
    else:
        current_content = service.read_text_file(project, path)
        managed_files[request.logical_key] = {
            "path": path,
            "content_hash": hashlib.sha256(current_content.encode("utf-8")).hexdigest(),
            "protected": True,
        }

    metadata["managed_files"] = managed_files
    metadata["sync_conflicts"] = [
        item
        for item in conflicts
        if not (isinstance(item, dict) and str(item.get("logical_key") or "") == request.logical_key)
    ]
    llm_config["metadata"] = metadata
    await service.update_llm_config(project, llm_config)
    return {"ok": True, "path": path, "strategy": request.strategy}


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
        payload, media_type = service.read_blob(project, path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(content=payload, media_type=media_type)


@router.post("/projects/{project_id}/upload", response_model=LatexUploadResponse)
async def upload_project_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    base_path: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexUploadResponse:
    service = LatexProjectService(db)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    saved_files: list[str] = []
    for upload in files:
        try:
            relative_path = _normalize_upload_relative_path(upload.filename, base_path)
            if not relative_path:
                continue
            saved = await service.save_upload(project, relative_path, await upload.read())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        saved_files.append(saved)

    return LatexUploadResponse(ok=True, files=saved_files)


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

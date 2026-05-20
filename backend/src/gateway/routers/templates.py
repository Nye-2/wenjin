"""Templates router for workspace template management."""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_template_service, get_workspace_service
from src.services.template_service import TemplateService, parse_template_content
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    persist_workspace_upload,
    sanitize_upload_filename,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["templates"])

TEMPLATE_EXTENSIONS = {".docx", ".tex", ".txt", ".md", ".cls", ".sty", ".markdown"}
MAX_TEMPLATE_SIZE = 10 * 1024 * 1024
_TEMPLATE_UPLOAD_ROOT = DEFAULT_WORKSPACE_UPLOAD_ROOT


class TemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    sourceType: str
    structure: dict[str, Any] | None = None
    formatSpec: dict[str, Any] | None = None
    contentGuidelines: dict[str, Any] | None = None
    isActive: bool
    isBuiltin: bool


class TemplatesListResponse(BaseModel):
    templates: list[TemplateResponse]


def _to_response(t: Any) -> TemplateResponse:
    return TemplateResponse(
        id=t.id,
        name=t.name,
        category=t.category,
        sourceType=t.source_type,
        structure=t.structure,
        formatSpec=t.format_spec,
        contentGuidelines=t.content_guidelines,
        isActive=t.is_active,
        isBuiltin=t.is_builtin,
    )


async def _require_workspace_access(
    *,
    workspace_id: str,
    current_user: User,
    workspace_service: WorkspaceService,
) -> Any:
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if not await workspace_service.has_active_membership(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
    ):
        raise HTTPException(403, "Access denied")
    return workspace


@router.get("/workspaces/{workspace_id}/templates", response_model=TemplatesListResponse)
async def list_templates(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplatesListResponse:
    await _require_workspace_access(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    templates = await template_service.list_by_workspace(workspace_id)
    return TemplatesListResponse(templates=[_to_response(t) for t in templates])


@router.get("/workspaces/{workspace_id}/templates/active")
async def get_active_template(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplateResponse | None:
    await _require_workspace_access(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    template = await template_service.get_active(workspace_id)
    return _to_response(template) if template else None


@router.post("/workspaces/{workspace_id}/templates/upload", response_model=TemplateResponse)
async def upload_template(
    workspace_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    workspace = await _require_workspace_access(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    ext = Path(file.filename or "").suffix.lower()
    if ext not in TEMPLATE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Read file with size limit (read in chunks to avoid DoS via large uploads)
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64KB chunks
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_TEMPLATE_SIZE:
            raise HTTPException(400, "File too large (max 10MB)")
        chunks.append(chunk)
    content_bytes = b"".join(chunks)

    # Save file using canonical workspace-upload storage helpers.
    fallback_filename = f"template{ext}"
    try:
        safe_filename = sanitize_upload_filename(file.filename or fallback_filename)
    except ValueError:
        safe_filename = fallback_filename
    if safe_filename.startswith("."):
        safe_filename = fallback_filename
    file_path = persist_workspace_upload(
        workspace_id=workspace_id,
        bucket="templates",
        filename=safe_filename,
        content=content_bytes,
        root=_TEMPLATE_UPLOAD_ROOT,
    )

    # Read text content
    file_content = ""
    if ext in (".txt", ".md", ".markdown", ".tex", ".cls", ".sty"):
        try:
            file_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            file_content = content_bytes.decode("latin-1")
    elif ext == ".docx":
        try:
            from io import BytesIO

            import docx
            doc = docx.Document(BytesIO(content_bytes))
            file_content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            logger.warning("Failed to extract text from docx, will use empty content")

    # Parse with LLM
    parsed: dict[str, Any] = await parse_template_content(file_content) if file_content else {}

    source_type = ext.lstrip(".")
    if source_type in ("cls", "sty"):
        source_type = "latex"
    latex_preamble = file_content if ext in (".tex", ".cls", ".sty") else None

    template = await template_service.create(
        workspace_id=workspace_id,
        name=parsed.get("name") or file.filename or "未命名模板",
        category=workspace.type,
        source_type=source_type,
        source_file_path=str(file_path),
        structure=parsed.get("structure"),
        format_spec=parsed.get("format_spec"),
        content_guidelines=parsed.get("content_guidelines"),
        latex_preamble=latex_preamble,
    )
    return _to_response(template)


@router.put("/workspaces/{workspace_id}/templates/{template_id}/activate", response_model=TemplateResponse)
async def activate_template(
    workspace_id: str,
    template_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    await _require_workspace_access(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    template = await template_service.activate(template_id, workspace_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return _to_response(template)


@router.delete("/workspaces/{workspace_id}/templates/{template_id}")
async def delete_template(
    workspace_id: str,
    template_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> dict[str, str]:
    await _require_workspace_access(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    deleted = await template_service.delete(template_id, workspace_id)
    if not deleted:
        raise HTTPException(404, "Template not found or does not belong to this workspace")
    return {"status": "deleted"}

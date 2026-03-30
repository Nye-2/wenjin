"""Templates router for workspace template management."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_template_service, get_workspace_service
from src.services.template_service import TemplateService, parse_template_content

logger = logging.getLogger(__name__)
router = APIRouter(tags=["templates"])

TEMPLATE_EXTENSIONS = {".docx", ".tex", ".txt", ".md", ".cls", ".sty", ".markdown"}
MAX_TEMPLATE_SIZE = 10 * 1024 * 1024


class TemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    sourceType: str
    structure: dict | None = None
    formatSpec: dict | None = None
    contentGuidelines: dict | None = None
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


@router.get("/workspaces/{workspace_id}/templates", response_model=TemplatesListResponse)
async def list_templates(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplatesListResponse:
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
    templates = await template_service.list_by_workspace(workspace_id)
    return TemplatesListResponse(templates=[_to_response(t) for t in templates])


@router.get("/workspaces/{workspace_id}/templates/active")
async def get_active_template(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplateResponse | None:
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
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
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in TEMPLATE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    content_bytes = await file.read()
    if len(content_bytes) > MAX_TEMPLATE_SIZE:
        raise HTTPException(400, "File too large (max 10MB)")

    # Save file
    from src.config import get_data_dir
    template_dir = os.path.join(get_data_dir(), "workspace_uploads", workspace_id, "templates")
    os.makedirs(template_dir, exist_ok=True)
    file_path = os.path.join(template_dir, file.filename or f"template{ext}")
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    # Read text content
    file_content = ""
    if ext in (".txt", ".md", ".markdown", ".tex", ".cls", ".sty"):
        try:
            file_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            file_content = content_bytes.decode("latin-1")
    elif ext == ".docx":
        try:
            import docx
            from io import BytesIO
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
        source_file_path=file_path,
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
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
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
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
    deleted = await template_service.delete(template_id)
    if not deleted:
        raise HTTPException(404, "Template not found")
    return {"status": "deleted"}

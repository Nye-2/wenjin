"""Academic router for paper and artifact management.

Note: Workspace CRUD operations are handled in workspaces.py.
This router handles paper and artifact operations within workspaces.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.application.errors import ApplicationError
from src.application.handlers.academic_compat_handler import AcademicCompatHandler
from src.database import User
from src.gateway.access_control import require_workspace_owner
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.paper import (
    PaperSummaryResponse as PaperResponse,
)
from src.gateway.contracts.paper import (
    paper_to_summary_response,
)
from src.gateway.deps import get_paper_service, get_workspace_service
from src.gateway.error_mapping import to_http_exception
from src.gateway.validators.paper import PaperCreatePayloadValidator as PaperCreate

router = APIRouter(tags=["academic"])
__all__ = ["get_paper_service", "router"]


async def get_academic_compat_handler(
    paper_service=Depends(get_paper_service),
) -> AcademicCompatHandler:
    """Get deprecated academic compatibility handler."""
    return AcademicCompatHandler(
        paper_service=paper_service,
    )


# ============ Paper Endpoints ============

@router.post("/academic/papers", response_model=PaperResponse, status_code=201)
async def create_paper(
    request: PaperCreate,
    current_user: User = Depends(get_current_user),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Create a new paper via the deprecated academic compatibility surface."""
    try:
        paper = await handler.create_paper(request)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return paper_to_summary_response(paper)


@router.post("/papers/upload")
async def upload_paper(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    workspace_service=Depends(get_workspace_service),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Upload a new paper (PDF).

    Validates the file is a PDF, saves metadata as a paper record,
    and returns structured response with paper_id.
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    try:
        return await handler.upload_paper(file=file, workspace_id=workspace_id)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc


@router.get("/papers/search")
async def search_papers(
    query: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Search papers in Semantic Scholar."""
    try:
        return await handler.search_papers(query=query, limit=limit)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc

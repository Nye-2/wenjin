"""Papers router for paper management API endpoints.

This module provides REST endpoints for:
- Paper creation and management
- Paper listing and retrieval
- Paper extraction triggering
- Paper sections retrieval
- Paper search functionality
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from src.application.errors import ApplicationError
from src.application.handlers.papers_handler import PapersHandler, get_papers_handler
from src.database import (
    User,
)
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.paper import (
    PaperResponse,
    PaperExtractionTaskResponse,
    SectionResponse,
    paper_extraction_task_to_response,
    paper_to_response,
    section_to_response,
)
from src.gateway.deps import (
    get_paper_service,
    get_workspace_service,
)
from src.gateway.error_mapping import to_http_exception
from src.gateway.validators.paper import (
    CreatePaperValidator,
    SearchPapersValidator,
    UpdatePaperValidator,
)

router = APIRouter(prefix="/papers", tags=["papers"])
__all__ = [
    "get_paper_service",
    "get_papers_handler",
    "get_workspace_service",
    "paper_to_response",
    "router",
    "section_to_response",
]


# Re-export validators as request models for backward compatibility
CreatePaperRequest = CreatePaperValidator
UpdatePaperRequest = UpdatePaperValidator
SearchPapersRequest = SearchPapersValidator


# ============ Endpoints ============

@router.post("", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
async def create_paper(
    request: CreatePaperRequest,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Create a new paper manually.

    Args:
        request: Paper creation request with metadata
        paper_service: Paper service instance

    Returns:
        Created paper response

    Raises:
        HTTPException: If creation fails
    """
    try:
        paper = await handler.create_paper(
            request,
            user_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return paper_to_response(paper)


@router.post("/upload")
async def upload_paper(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Upload a paper PDF into a workspace."""
    try:
        return await handler.upload_paper(
            workspace_id=workspace_id,
            user_id=str(current_user.id),
            file=file,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc


@router.get("", response_model=list[PaperResponse])
async def list_papers(
    workspace_id: str | None = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """List papers, optionally filtered by workspace.

    Args:
        workspace_id: Optional workspace ID to filter papers
        limit: Maximum number of papers to return (default 20)
        session: Database session

    Returns:
        List of paper responses
    """
    try:
        papers = await handler.list_papers(
            user_id=str(current_user.id),
            workspace_id=workspace_id,
            limit=limit,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return [paper_to_response(p) for p in papers]


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Get paper by ID.

    Args:
        paper_id: Paper UUID string
        paper_service: Paper service instance

    Returns:
        Paper response

    Raises:
        HTTPException: If paper not found
    """
    try:
        paper = await handler.get_paper(
            paper_id=paper_id,
            user_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return paper_to_response(paper)


@router.put("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: str,
    request: UpdatePaperRequest,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Update paper metadata.

    Args:
        paper_id: Paper UUID string
        request: Update request with fields to update
        paper_service: Paper service instance
        session: Database session

    Returns:
        Updated paper response

    Raises:
        HTTPException: If paper not found
    """
    try:
        paper = await handler.update_paper(
            paper_id=paper_id,
            user_id=str(current_user.id),
            request=request,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return paper_to_response(paper)


@router.delete("/{paper_id}")
async def delete_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Delete paper.

    Args:
        paper_id: Paper UUID string
        paper_service: Paper service instance
        session: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If paper not found
    """
    try:
        await handler.delete_paper(
            paper_id=paper_id,
            user_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return {"success": True, "message": f"Paper {paper_id} deleted"}


@router.post("/{paper_id}/extract", response_model=PaperExtractionTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def extract_paper(
    paper_id: str,
    workspace_id: str,
    tier: int = 1,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Queue paper extraction.

    Args:
        paper_id: Paper UUID string
        workspace_id: Workspace UUID string for section extraction
        tier: Extraction tier (1=engineering, 2=LLM)

    Returns:
        Async task submission response

    Raises:
        HTTPException: If the paper is inaccessible or task submission fails
    """
    try:
        extraction = await handler.extract_paper(
            paper_id=paper_id,
            workspace_id=workspace_id,
            tier=tier,
            user_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return paper_extraction_task_to_response(extraction)


@router.get("/{paper_id}/sections", response_model=list[SectionResponse])
async def get_paper_sections(
    paper_id: str,
    workspace_id: str | None = None,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Get paper sections.

    Args:
        paper_id: Paper UUID string
        workspace_id: Optional workspace ID to filter sections
        session: Database session

    Returns:
        List of section responses

    Raises:
        HTTPException: If paper not found
    """
    try:
        sections = await handler.get_paper_sections(
            paper_id=paper_id,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return [section_to_response(s) for s in sections]


@router.post("/search")
async def search_papers(
    request: SearchPapersRequest,
    current_user: User = Depends(get_current_user),
    handler: PapersHandler = Depends(get_papers_handler),
):
    """Search papers by title, authors, or content.

    Args:
        request: Search request with query and optional filters
        session: Database session

    Returns:
        List of matching papers
    """
    try:
        result = await handler.search_papers(
            request=request,
            user_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return {
        "query": result["query"],
        "count": result["count"],
        "papers": [paper_to_response(p) for p in result["papers"]],
    }

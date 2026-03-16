"""Papers router for paper management API endpoints.

This module provides REST endpoints for:
- Paper creation and management
- Paper listing and retrieval
- Paper extraction triggering
- Paper sections retrieval
- Paper search functionality
"""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.extraction_service import ExtractionService
from src.academic.services.paper_service import PaperService
from src.database import (
    Paper,
    PaperSection,
    User,
    WorkspacePaper,
    get_db_session,
)
from src.gateway.routers.auth import get_current_user
from src.gateway.validators.paper import (
    CreatePaperValidator,
    SearchPapersValidator,
    UpdatePaperValidator,
)

router = APIRouter(prefix="/papers", tags=["papers"])


# ============ Request/Response Models ============

class PaperResponse(BaseModel):
    """Paper response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    doi: str | None
    title: str
    authors: list[dict]
    year: int | None
    venue: str | None
    abstract: str | None
    file_path: str | None
    source: str
    external_ids: dict
    toc: list | None
    citation_count: int | None
    reference_count: int | None


class SectionResponse(BaseModel):
    """Paper section response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    paper_id: str
    workspace_id: str
    section_title: str
    section_path: str
    page_start: int
    page_end: int
    content: str
    level: int


class ExtractionResponse(BaseModel):
    """Paper extraction response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    paper_id: str
    tier: int
    extraction_type: str
    structured_data: dict
    processing_time_ms: int | None
    model_used: str | None


# Re-export validators as request models for backward compatibility
CreatePaperRequest = CreatePaperValidator
UpdatePaperRequest = UpdatePaperValidator
SearchPapersRequest = SearchPapersValidator


# ============ Dependencies ============

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async for session in get_db_session():
        yield session


async def get_paper_service(
    session: AsyncSession = Depends(get_session),
) -> PaperService:
    """Get paper service instance."""
    return PaperService(session)


async def get_extraction_service(
    session: AsyncSession = Depends(get_session),
) -> ExtractionService:
    """Get extraction service instance."""
    return ExtractionService(session)


# ============ Helper Functions ============

def paper_to_response(paper: Paper) -> PaperResponse:
    """Convert Paper model to response model."""
    return PaperResponse(
        id=str(paper.id),
        doi=paper.doi,
        title=paper.title,
        authors=paper.authors or [],
        year=paper.year,
        venue=paper.venue,
        abstract=paper.abstract,
        file_path=paper.file_path,
        source=paper.source,
        external_ids=paper.external_ids or {},
        toc=paper.toc,
        citation_count=paper.citation_count,
        reference_count=paper.reference_count,
    )


def section_to_response(section: PaperSection) -> SectionResponse:
    """Convert PaperSection model to response model."""
    return SectionResponse(
        id=str(section.id),
        paper_id=str(section.paper_id),
        workspace_id=str(section.workspace_id),
        section_title=section.section_title,
        section_path=section.section_path,
        page_start=section.page_start,
        page_end=section.page_end,
        content=section.content,
        level=section.level,
    )


# ============ Endpoints ============

@router.post("/", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
async def create_paper(
    request: CreatePaperRequest,
    current_user: User = Depends(get_current_user),
    paper_service: PaperService = Depends(get_paper_service),
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
        paper = await paper_service.create(
            doi=request.doi,
            title=request.title,
            authors=request.authors,
            year=request.year,
            venue=request.venue,
            abstract=request.abstract,
            file_path=request.file_path,
            source=request.source,
            external_ids=request.external_ids,
            citation_count=request.citation_count,
            reference_count=request.reference_count,
        )
        return paper_to_response(paper)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create paper: {str(e)}",
        ) from e


@router.get("/", response_model=list[PaperResponse])
async def list_papers(
    workspace_id: str | None = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List papers, optionally filtered by workspace.

    Args:
        workspace_id: Optional workspace ID to filter papers
        limit: Maximum number of papers to return (default 20)
        session: Database session

    Returns:
        List of paper responses
    """
    if workspace_id:
        # List papers in a specific workspace
        query = (
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == workspace_id)
            .order_by(WorkspacePaper.created_at.desc())
            .limit(limit)
        )
    else:
        # List all papers globally
        query = (
            select(Paper)
            .order_by(Paper.created_at.desc())
            .limit(limit)
        )

    result = await session.execute(query)
    papers = list(result.scalars().all())

    return [paper_to_response(p) for p in papers]


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    paper_service: PaperService = Depends(get_paper_service),
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
    paper = await paper_service.get(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )
    return paper_to_response(paper)


@router.put("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: str,
    request: UpdatePaperRequest,
    current_user: User = Depends(get_current_user),
    paper_service: PaperService = Depends(get_paper_service),
    session: AsyncSession = Depends(get_session),
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
    paper = await paper_service.get(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    # Update only provided fields
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(paper, key) and value is not None:
            setattr(paper, key, value)

    await session.commit()
    await session.refresh(paper)

    return paper_to_response(paper)


@router.delete("/{paper_id}")
async def delete_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    paper_service: PaperService = Depends(get_paper_service),
    session: AsyncSession = Depends(get_session),
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
    paper = await paper_service.get(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    await session.delete(paper)
    await session.commit()

    return {"success": True, "message": f"Paper {paper_id} deleted"}


@router.post("/{paper_id}/extract", response_model=ExtractionResponse)
async def extract_paper(
    paper_id: str,
    workspace_id: str,
    tier: int = 1,
    current_user: User = Depends(get_current_user),
    paper_service: PaperService = Depends(get_paper_service),
    extraction_service: ExtractionService = Depends(get_extraction_service),
):
    """Trigger paper extraction.

    Args:
        paper_id: Paper UUID string
        workspace_id: Workspace UUID string for section extraction
        tier: Extraction tier (1=engineering, 2=LLM)
        paper_service: Paper service instance
        extraction_service: Extraction service instance

    Returns:
        Extraction response

    Raises:
        HTTPException: If paper not found or extraction fails
    """
    paper = await paper_service.get(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    if not paper.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paper has no file path for extraction",
        )

    try:
        extraction = await extraction_service.extract_paper(
            paper_id=paper_id,
            file_path=paper.file_path,
            tier=tier,
        )

        # Also extract sections
        await extraction_service.extract_sections(
            paper_id=paper_id,
            workspace_id=workspace_id,
            file_path=paper.file_path,
        )

        return ExtractionResponse(
            id=str(extraction.id),
            paper_id=str(extraction.paper_id),
            tier=extraction.tier,
            extraction_type=extraction.extraction_type,
            structured_data=extraction.structured_data,
            processing_time_ms=extraction.processing_time_ms,
            model_used=extraction.model_used,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}",
        ) from e


@router.get("/{paper_id}/sections", response_model=list[SectionResponse])
async def get_paper_sections(
    paper_id: str,
    workspace_id: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
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
    # Verify paper exists
    result = await session.execute(
        select(Paper).where(Paper.id == paper_id)
    )
    paper = result.scalar_one_or_none()
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    # Query sections
    query = select(PaperSection).where(PaperSection.paper_id == paper_id)
    if workspace_id:
        query = query.where(PaperSection.workspace_id == workspace_id)
    query = query.order_by(PaperSection.page_start)

    result = await session.execute(query)
    sections = list(result.scalars().all())

    return [section_to_response(s) for s in sections]


@router.post("/search")
async def search_papers(
    request: SearchPapersRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Search papers by title, authors, or content.

    Args:
        request: Search request with query and optional filters
        session: Database session

    Returns:
        List of matching papers
    """
    query_text = request.query

    if request.workspace_id:
        # Search within workspace papers
        query = (
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == request.workspace_id)
            .where(
                or_(
                    Paper.title.ilike(f"%{query_text}%"),
                    Paper.abstract.ilike(f"%{query_text}%"),
                )
            )
            .limit(request.limit)
        )
    else:
        # Global search
        query = (
            select(Paper)
            .where(
                or_(
                    Paper.title.ilike(f"%{query_text}%"),
                    Paper.abstract.ilike(f"%{query_text}%"),
                )
            )
            .limit(request.limit)
        )

    result = await session.execute(query)
    papers = list(result.scalars().all())

    return {
        "query": query_text,
        "count": len(papers),
        "papers": [paper_to_response(p) for p in papers],
    }

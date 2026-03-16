"""Academic router for paper and artifact management.

Note: Workspace CRUD operations are handled in workspaces.py.
This router handles paper and artifact operations within workspaces.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

from src.database import User
from src.gateway.routers.auth import get_current_user

router = APIRouter(tags=["academic"])


# ============ Request/Response Models ============

class PaperCreate(BaseModel):
    """Paper creation request."""
    doi: str | None = None
    title: str
    authors: list[dict] | None = None
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None


class PaperResponse(BaseModel):
    """Paper response."""
    id: str
    doi: str | None
    title: str
    authors: list[dict]
    year: int | None
    venue: str | None
    abstract: str | None
    source: str
    citation_count: int | None
    reference_count: int | None

    model_config = ConfigDict(from_attributes=True)


class ArtifactCreate(BaseModel):
    """Artifact creation request."""
    type: str
    title: str | None = None
    content: dict
    created_by_skill: str | None = None
    parent_artifact_id: str | None = None


class ArtifactResponse(BaseModel):
    """Artifact response."""
    id: str
    workspace_id: str
    type: str
    title: str | None
    content: dict
    created_by_skill: str | None
    parent_artifact_id: str | None
    version: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArtifactsListResponse(BaseModel):
    """List of artifacts."""
    artifacts: list[ArtifactResponse]
    count: int


# ============ Helper Functions ============

def orm_to_dict(obj) -> dict:
    """Convert SQLAlchemy ORM object to dict for Pydantic."""
    return {
        column.name: getattr(obj, column.name)
        for column in obj.__table__.columns
    }


# ============ Dependency Injection ============

async def get_db():
    """Get database session."""
    from src.database import get_db_session

    async with get_db_session() as db:
        yield db


async def get_paper_service(db = Depends(get_db)):
    """Get paper service instance."""
    from src.academic.services import PaperService
    return PaperService(db)


async def get_artifact_service(db = Depends(get_db)):
    """Get artifact service instance."""
    from src.academic.services import ArtifactService
    return ArtifactService(db)


# ============ Paper Endpoints ============

@router.post("/papers", response_model=PaperResponse, status_code=201)
async def create_paper(
    request: PaperCreate,
    current_user: User = Depends(get_current_user),
    paper_service = Depends(get_paper_service),
):
    """Create a new paper."""
    paper = await paper_service.create(
        doi=request.doi,
        title=request.title,
        authors=request.authors,
        year=request.year,
        venue=request.venue,
        abstract=request.abstract,
    )
    return PaperResponse(**orm_to_dict(paper))


@router.post("/papers/upload")
async def upload_paper(
    file: UploadFile = File(...),
    workspace_id: str | None = None,
    current_user: User = Depends(get_current_user),
    paper_service=Depends(get_paper_service),
):
    """Upload a new paper (PDF).

    Validates the file is a PDF, saves metadata as a paper record,
    and returns structured response with paper_id.
    """
    # Validate content type
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read and validate non-empty
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    size_bytes = len(content)
    filename = file.filename or "untitled.pdf"

    # Create paper record with minimal metadata extracted from filename
    title = filename.rsplit(".", 1)[0] if "." in filename else filename
    paper = await paper_service.create(
        title=title,
        authors=[],
        source="upload",
    )

    return {
        "success": True,
        "paper_id": paper.id,
        "filename": filename,
        "content_type": file.content_type,
        "size_bytes": size_bytes,
        "workspace_id": workspace_id,
    }


@router.get("/papers/search")
async def search_papers(
    query: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
):
    """Search papers in Semantic Scholar."""
    # Use the semantic scholar tool
    from src.academic.tools.semantic_scholar import semantic_scholar_search_tool
    result = await semantic_scholar_search_tool.ainvoke({
        "query": query,
        "limit": limit,
    })
    return {"result": result}


# ============ Artifact Endpoints ============

@router.get("/workspaces/{workspace_id}/artifacts", response_model=ArtifactsListResponse)
async def list_artifacts(
    workspace_id: str,
    artifact_type: str | None = None,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """List artifacts in a workspace."""
    artifacts = await artifact_service.list_by_workspace(
        workspace_id=workspace_id,
        type=artifact_type,
    )
    return ArtifactsListResponse(
        artifacts=[ArtifactResponse(**orm_to_dict(a)) for a in artifacts],
        count=len(artifacts),
    )


@router.post("/workspaces/{workspace_id}/artifacts", response_model=ArtifactResponse, status_code=201)
async def create_artifact(
    workspace_id: str,
    request: ArtifactCreate,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Create a new artifact."""
    artifact = await artifact_service.create(
        workspace_id=workspace_id,
        type=request.type,
        title=request.title,
        content=request.content,
        created_by_skill=request.created_by_skill,
        parent_artifact_id=request.parent_artifact_id,
    )
    return ArtifactResponse(**orm_to_dict(artifact))


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Get artifact details."""
    artifact = await artifact_service.get(artifact_id)
    if not artifact or artifact.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactResponse(**orm_to_dict(artifact))


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/lineage")
async def get_artifact_lineage(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Get artifact lineage (parent chain)."""
    lineage = await artifact_service.get_lineage(artifact_id)
    return {
        "lineage": [ArtifactResponse(**orm_to_dict(a)) for a in lineage],
    }

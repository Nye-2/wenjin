"""Academic router for workspace, paper, and artifact management."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

router = APIRouter()


# ============ Request/Response Models ============

class WorkspaceCreate(BaseModel):
    """Workspace creation request."""
    name: str
    type: str  # sci, thesis, proposal, grant
    discipline: str | None = None
    description: str | None = None
    config: dict | None = None


class WorkspaceUpdate(BaseModel):
    """Workspace update request."""
    name: str | None = None
    discipline: str | None = None
    description: str | None = None
    config: dict | None = None


class WorkspaceResponse(BaseModel):
    """Workspace response."""
    id: str
    user_id: str
    name: str
    type: str
    discipline: str | None
    description: str | None
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspacesListResponse(BaseModel):
    """List of workspaces."""
    workspaces: list[WorkspaceResponse]


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


class PapersListResponse(BaseModel):
    """List of papers."""
    papers: list[PaperResponse]
    count: int


class WorkspacePaperAdd(BaseModel):
    """Add paper to workspace request."""
    paper_id: str
    notes: str | None = None
    tags: list[str] | None = None
    is_primary: bool = False


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

async def get_current_user_id() -> str:
    """Get current user ID from request context.

    In production, this would extract from JWT token.
    For now, returns a default user ID.
    """
    return "default-user"


async def get_db():
    """Get database session."""
    from src.database import get_db_session

    async with get_db_session() as db:
        yield db


async def get_workspace_service(db = Depends(get_db)):
    """Get workspace service instance."""
    from src.academic.services import WorkspaceService
    return WorkspaceService(db)


async def get_paper_service(db = Depends(get_db)):
    """Get paper service instance."""
    from src.academic.services import PaperService
    return PaperService(db)


async def get_artifact_service(db = Depends(get_db)):
    """Get artifact service instance."""
    from src.academic.services import ArtifactService
    return ArtifactService(db)


# ============ Workspace Endpoints ============

@router.get("/workspaces", response_model=WorkspacesListResponse)
async def list_workspaces(
    user_id: str = Depends(get_current_user_id),
    workspace_service = Depends(get_workspace_service),
):
    """List all workspaces for the current user."""
    workspaces = await workspace_service.list_by_user(user_id)
    return WorkspacesListResponse(
        workspaces=[WorkspaceResponse(**orm_to_dict(w)) for w in workspaces]
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    request: WorkspaceCreate,
    user_id: str = Depends(get_current_user_id),
    workspace_service = Depends(get_workspace_service),
):
    """Create a new workspace."""
    workspace = await workspace_service.create(
        user_id=user_id,
        name=request.name,
        type=request.type,
        discipline=request.discipline,
        description=request.description,
        config=request.config,
    )
    return WorkspaceResponse(**orm_to_dict(workspace))


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    workspace_service = Depends(get_workspace_service),
):
    """Get workspace details."""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse(**orm_to_dict(workspace))


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdate,
    workspace_service = Depends(get_workspace_service),
):
    """Update workspace."""
    workspace = await workspace_service.update(
        workspace_id=workspace_id,
        name=request.name,
        discipline=request.discipline,
        description=request.description,
        config=request.config,
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse(**orm_to_dict(workspace))


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    workspace_service = Depends(get_workspace_service),
):
    """Delete workspace."""
    success = await workspace_service.delete(workspace_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"success": True}


# ============ Paper Endpoints ============

@router.get("/workspaces/{workspace_id}/papers", response_model=PapersListResponse)
async def list_workspace_papers(
    workspace_id: str,
    read_status: str | None = None,
    paper_service = Depends(get_paper_service),
):
    """List papers in a workspace."""
    papers = await paper_service.list_workspace_papers(
        workspace_id=workspace_id,
        read_status=read_status,
    )
    return PapersListResponse(
        papers=[PaperResponse(**orm_to_dict(p)) for p in papers],
        count=len(papers),
    )


@router.post("/workspaces/{workspace_id}/papers")
async def add_paper_to_workspace(
    workspace_id: str,
    request: WorkspacePaperAdd,
    paper_service = Depends(get_paper_service),
):
    """Add a paper to a workspace."""
    await paper_service.add_to_workspace(
        workspace_id=workspace_id,
        paper_id=request.paper_id,
        notes=request.notes,
        tags=request.tags,
        is_primary=request.is_primary,
    )
    return {"success": True, "paper_id": request.paper_id}


@router.post("/papers", response_model=PaperResponse, status_code=201)
async def create_paper(
    request: PaperCreate,
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
):
    """Upload a new paper (PDF)."""
    # TODO: Implement PDF processing and extraction
    return {
        "success": True,
        "filename": file.filename,
        "content_type": file.content_type,
    }


@router.get("/papers/search")
async def search_papers(
    query: str,
    limit: int = 10,
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
    artifact_service = Depends(get_artifact_service),
):
    """Get artifact lineage (parent chain)."""
    lineage = await artifact_service.get_lineage(artifact_id)
    return {
        "lineage": [ArtifactResponse(**orm_to_dict(a)) for a in lineage],
    }

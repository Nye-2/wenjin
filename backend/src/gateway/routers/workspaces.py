"""Workspaces router for workspace management API endpoints.

This module provides REST endpoints for:
- Workspace CRUD operations
- Paper association management
"""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.database import Paper, Workspace, get_db_session
from src.gateway.validators.workspace import (
    AddPaperToWorkspaceValidator,
    CreateWorkspaceValidator,
    UpdateWorkspaceValidator,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# ============ Request/Response Models ============

class WorkspaceResponse(BaseModel):
    """Workspace response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    type: str
    discipline: str | None
    description: str | None
    config: dict


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
    source: str
    citation_count: int | None
    reference_count: int | None


# Re-export validators as request models for backward compatibility
CreateWorkspaceRequest = CreateWorkspaceValidator
UpdateWorkspaceRequest = UpdateWorkspaceValidator
AddPaperRequest = AddPaperToWorkspaceValidator


# ============ Dependencies ============

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async for session in get_db_session():
        yield session


async def get_workspace_service(db: AsyncSession = Depends(get_db)) -> WorkspaceService:
    """Get workspace service instance."""
    return WorkspaceService(db)


async def get_paper_service(db: AsyncSession = Depends(get_db)) -> PaperService:
    """Get paper service instance."""
    return PaperService(db)


def workspace_to_response(workspace: Workspace) -> WorkspaceResponse:
    """Convert Workspace ORM object to response model."""
    return WorkspaceResponse(
        id=str(workspace.id),
        user_id=str(workspace.user_id),
        name=workspace.name,
        type=workspace.type.value if workspace.type else None,
        discipline=workspace.discipline,
        description=workspace.description,
        config=workspace.config or {},
    )


def paper_to_response(paper: Paper) -> PaperResponse:
    """Convert Paper ORM object to response model."""
    return PaperResponse(
        id=str(paper.id),
        doi=paper.doi,
        title=paper.title,
        authors=paper.authors or [],
        year=paper.year,
        venue=paper.venue,
        abstract=paper.abstract,
        source=paper.source,
        citation_count=paper.citation_count,
        reference_count=paper.reference_count,
    )


# ============ Endpoints ============

@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    user_id: str,
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """Create a new workspace.

    Args:
        request: Workspace creation request
        user_id: User ID who owns the workspace
        workspace_service: Workspace service instance

    Returns:
        Created workspace

    Raises:
        HTTPException: If workspace type is invalid
    """
    try:
        workspace = await workspace_service.create(
            user_id=user_id,
            name=request.name,
            type=request.type,
            discipline=request.discipline,
            description=request.description,
            config=request.config,
        )
        return workspace_to_response(workspace)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user_id: str,
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """List workspaces for user.

    Args:
        user_id: User ID to list workspaces for
        workspace_service: Workspace service instance

    Returns:
        List of workspaces for the user
    """
    workspaces = await workspace_service.list_by_user(user_id)
    return [workspace_to_response(w) for w in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """Get workspace by ID.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance

    Returns:
        Workspace details

    Raises:
        HTTPException: If workspace not found
    """
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return workspace_to_response(workspace)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """Update workspace.

    Args:
        workspace_id: Workspace ID
        request: Update request with fields to update
        workspace_service: Workspace service instance

    Returns:
        Updated workspace

    Raises:
        HTTPException: If workspace not found
    """
    update_data = request.model_dump(exclude_unset=True)
    workspace = await workspace_service.update(workspace_id, **update_data)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return workspace_to_response(workspace)


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """Delete workspace.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance

    Returns:
        Success message

    Raises:
        HTTPException: If workspace not found
    """
    success = await workspace_service.delete(workspace_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return {"success": True}


@router.get("/{workspace_id}/papers", response_model=list[PaperResponse])
async def list_workspace_papers(
    workspace_id: str,
    read_status: str | None = None,
    paper_service: PaperService = Depends(get_paper_service),
):
    """List papers in workspace.

    Args:
        workspace_id: Workspace ID
        read_status: Optional filter by read status
        paper_service: Paper service instance

    Returns:
        List of papers in the workspace
    """
    papers = await paper_service.list_workspace_papers(
        workspace_id=workspace_id,
        read_status=read_status,
    )
    return [paper_to_response(p) for p in papers]


@router.post("/{workspace_id}/papers/{paper_id}")
async def add_paper_to_workspace(
    workspace_id: str,
    paper_id: str,
    request: AddPaperRequest,
    paper_service: PaperService = Depends(get_paper_service),
):
    """Add paper to workspace.

    Args:
        workspace_id: Workspace ID
        paper_id: Paper ID to add
        request: Add paper request with optional notes and tags
        paper_service: Paper service instance

    Returns:
        Success message
    """
    await paper_service.add_to_workspace(
        paper_id=paper_id,
        workspace_id=workspace_id,
        notes=request.notes,
        tags=request.tags,
        is_primary=request.is_primary,
    )
    return {"success": True, "paper_id": paper_id}


@router.delete("/{workspace_id}/papers/{paper_id}")
async def remove_paper_from_workspace(
    workspace_id: str,
    paper_id: str,
    paper_service: PaperService = Depends(get_paper_service),
):
    """Remove paper from workspace.

    Args:
        workspace_id: Workspace ID
        paper_id: Paper ID to remove
        paper_service: Paper service instance

    Returns:
        Success message
    """
    success = await paper_service.remove_from_workspace(
        paper_id=paper_id,
        workspace_id=workspace_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found in workspace",
        )
    return {"success": True}

"""Workspaces router for workspace management API endpoints.

This module provides REST endpoints for:
- Workspace CRUD operations
- Paper association management
- Dashboard overview
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.database import User, Workspace
from src.gateway.access_control import require_workspace_owner
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.paper import (
    PaperSummaryResponse as PaperResponse,
)
from src.gateway.contracts.paper import (
    paper_to_summary_response as paper_to_response,
)
from src.gateway.deps import get_dashboard_service, get_paper_service, get_workspace_service
from src.gateway.validators.workspace import (
    AddPaperToWorkspaceValidator,
    CreateWorkspaceValidator,
    UpdateWorkspaceValidator,
)
from src.services.dashboard_service import DashboardService

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
    created_at: str
    updated_at: str


class WorkspacesListResponse(BaseModel):
    """Workspaces list response."""
    workspaces: list[WorkspaceResponse]


class PapersListResponse(BaseModel):
    """Workspace papers response."""

    papers: list[PaperResponse]
    count: int


# Re-export validators as request models for backward compatibility
CreateWorkspaceRequest = CreateWorkspaceValidator
UpdateWorkspaceRequest = UpdateWorkspaceValidator
AddPaperRequest = AddPaperToWorkspaceValidator


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
        created_at=workspace.created_at.isoformat() if workspace.created_at else "",
        updated_at=workspace.updated_at.isoformat() if workspace.updated_at else "",
    )


# ============ Endpoints ============

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """Create a new workspace.

    Args:
        request: Workspace creation request
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        Created workspace

    Raises:
        HTTPException: If workspace type is invalid
    """
    try:
        workspace = await workspace_service.create(
            user_id=str(current_user.id),
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


@router.get("", response_model=WorkspacesListResponse)
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
):
    """List workspaces for current user.

    Args:
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        List of workspaces for the user
    """
    workspaces = await workspace_service.list_by_user(str(current_user.id))
    return {"workspaces": [workspace_to_response(w) for w in workspaces]}


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
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
    workspace = await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return workspace_to_response(workspace)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
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
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

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
    current_user: User = Depends(get_current_user),
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
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    success = await workspace_service.delete(workspace_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return {"success": True}


@router.get("/{workspace_id}/papers", response_model=PapersListResponse)
async def list_workspace_papers(
    workspace_id: str,
    read_status: str | None = None,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    paper_service: PaperService = Depends(get_paper_service),
):
    """List papers in workspace.

    Args:
        workspace_id: Workspace ID
        read_status: Optional filter by read status
        paper_service: Paper service instance

    Returns:
        Papers in the workspace with total count
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    papers = await paper_service.list_workspace_papers(
        workspace_id=workspace_id,
        read_status=read_status,
    )
    return PapersListResponse(
        papers=[paper_to_response(p) for p in papers],
        count=len(papers),
    )


@router.post("/{workspace_id}/papers/{paper_id}")
async def add_paper_to_workspace(
    workspace_id: str,
    paper_id: str,
    request: AddPaperRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
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
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

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
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
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
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

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


@router.get("/{workspace_id}/dashboard")
async def get_workspace_dashboard(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """Get workspace dashboard overview.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance
        dashboard_service: Dashboard service instance

    Returns:
        Dashboard with module statuses and recent artifacts

    Raises:
        HTTPException: If workspace not found
    """
    workspace = await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    workspace_type = workspace.type.value if workspace.type else None
    return await dashboard_service.get_dashboard(
        workspace_id,
        workspace_type=workspace_type,
    )

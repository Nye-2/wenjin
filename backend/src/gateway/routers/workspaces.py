"""Workspaces router for workspace management API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.paper import (
    paper_to_summary_response as paper_to_response,
)
from src.gateway.deps import (
    get_dashboard_service,
    get_paper_service,
    get_workspace_activity_service,
    get_workspace_service,
    get_workspace_summary_service,
)
from src.gateway.routers.workspaces_contracts import (
    AddPaperRequest,
    CreateWorkspaceRequest,
    PapersListResponse,
    UpdateWorkspaceRequest,
    WorkspaceActivityResponse,
    WorkspaceResponse,
    WorkspacesListResponse,
    WorkspaceSummaryResponse,
)
from src.gateway.routers.workspaces_runtime import (
    create_workspace_events_response_with_stream,
    get_owned_workspace,
    workspace_type_value,
)
from src.gateway.routers.workspaces_serializers import (
    workspace_activity_to_response,
    workspace_to_response,
)
from src.services.dashboard_service import DashboardService
from src.services.workspace_activity_service import WorkspaceActivityService
from src.services.workspace_summary_service import WorkspaceSummaryService
from src.workspace_events import stream_workspace_events

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
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
) -> WorkspacesListResponse:
    """List workspaces for current user.

    Args:
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        List of workspaces for the user
    """
    workspaces = await workspace_service.list_by_user(str(current_user.id))
    return WorkspacesListResponse(
        workspaces=[workspace_to_response(w) for w in workspaces]
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Get workspace by ID.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance

    Returns:
        Workspace details

    Raises:
        HTTPException: If workspace not found
    """
    workspace = await get_owned_workspace(
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
) -> WorkspaceResponse:
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
    await get_owned_workspace(
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
) -> dict[str, bool]:
    """Delete workspace.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance

    Returns:
        Success message

    Raises:
        HTTPException: If workspace not found
    """
    await get_owned_workspace(
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
) -> PapersListResponse:
    """List papers in workspace.

    Args:
        workspace_id: Workspace ID
        read_status: Optional filter by read status
        paper_service: Paper service instance

    Returns:
        Papers in the workspace with total count
    """
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    papers = await paper_service.list_workspace_papers(
        workspace_id=workspace_id,
        read_status=read_status,
    )
    return PapersListResponse(
        papers=[paper_to_response(p, workspace_id=workspace_id) for p in papers],
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
) -> dict[str, bool | str]:
    """Add paper to workspace.

    Args:
        workspace_id: Workspace ID
        paper_id: Paper ID to add
        request: Add paper request with optional notes and tags
        paper_service: Paper service instance

    Returns:
        Success message
    """
    await get_owned_workspace(
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
) -> dict[str, bool]:
    """Remove paper from workspace.

    Args:
        workspace_id: Workspace ID
        paper_id: Paper ID to remove
        paper_service: Paper service instance

    Returns:
        Success message
    """
    await get_owned_workspace(
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
) -> dict[str, Any]:
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
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        workspace_type = workspace_type_value(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return await dashboard_service.get_dashboard(
        workspace_id,
        workspace_type=workspace_type,
    )


@router.get("/{workspace_id}/summary", response_model=WorkspaceSummaryResponse)
async def get_workspace_summary(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    summary_service: WorkspaceSummaryService = Depends(get_workspace_summary_service),
) -> WorkspaceSummaryResponse:
    """Get workspace cockpit summary with phase, recommendation, and risk data."""
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        workspace_type = workspace_type_value(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    payload = await summary_service.get_summary(
        workspace_id,
        workspace_type=workspace_type,
        user_id=str(current_user.id),
    )
    return WorkspaceSummaryResponse(**payload)


@router.get("/{workspace_id}/activity", response_model=WorkspaceActivityResponse)
async def get_workspace_activity(
    workspace_id: str,
    limit: int = 40,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    activity_service: WorkspaceActivityService = Depends(get_workspace_activity_service),
) -> WorkspaceActivityResponse:
    """Get a unified recent activity timeline for the workspace."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    activity = await activity_service.get_activity(
        workspace_id,
        user_id=str(current_user.id),
        limit=limit,
    )
    return WorkspaceActivityResponse(
        items=[workspace_activity_to_response(item) for item in activity["items"]],
        count=int(activity.get("count", 0)),
    )


@router.get("/{workspace_id}/events")
async def subscribe_workspace_events(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> StreamingResponse:
    """Subscribe to workspace-scoped live events via SSE."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return await create_workspace_events_response_with_stream(
        workspace_id=workspace_id,
        stream_factory=stream_workspace_events,
    )

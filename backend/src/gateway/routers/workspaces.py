"""Workspaces router for workspace management API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from src.academic.services.workspace_service import WorkspaceService
from src.database import User, get_db_session
from src.database.models.capability import Capability
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import (
    get_dashboard_service,
    get_db,
    get_workspace_activity_service,
    get_workspace_service,
    get_workspace_summary_service,
)
from src.gateway.routers.workspaces_contracts import (
    CreateWorkspaceRequest,
    ResolveCapabilityActionRequest,
    ResolveCapabilityActionResponse,
    UpdateWorkspaceRequest,
    WorkspaceActivityResponse,
    WorkspaceExecutionsResponse,
    WorkspacePrismEnsureResponse,
    WorkspacePrismSurfaceResponse,
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
from src.services.execution_service import ExecutionService
from src.services.feature_action_resolution_service import resolve_feature_action_state
from src.services.workspace_activity_service import WorkspaceActivityService
from src.services.workspace_prism_service import WorkspacePrismService
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


@router.post(
    "/{workspace_id}/prism/ensure",
    response_model=WorkspacePrismEnsureResponse,
)
async def ensure_workspace_prism_project(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: Any = Depends(get_db),
) -> WorkspacePrismEnsureResponse:
    """Ensure a workspace-linked WenjinPrism project exists."""
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    linked_project = await WorkspacePrismService(db).ensure_primary_project(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        project_name=str(workspace.name or ""),
    )
    latex_project_id = str(linked_project.id)
    return WorkspacePrismEnsureResponse(
        latex_project_id=latex_project_id,
        url=f"/workspaces/{workspace_id}/prism",
        sync_status="ready",
    )


@router.get(
    "/{workspace_id}/prism",
    response_model=WorkspacePrismSurfaceResponse,
)
async def get_workspace_prism_surface(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: Any = Depends(get_db),
) -> WorkspacePrismSurfaceResponse:
    """Return the workspace-owned WenjinPrism surface projection."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    projection = await WorkspacePrismService(db).get_surface_projection(
        workspace_id,
        user_id=str(current_user.id),
    )
    return WorkspacePrismSurfaceResponse(**projection)


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


@router.post(
    "/{workspace_id}/capabilities/{capability_id}/resolve-action",
    response_model=ResolveCapabilityActionResponse,
)
async def resolve_workspace_capability_action(
    workspace_id: str,
    capability_id: str,
    request: ResolveCapabilityActionRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: Any = Depends(get_db),
) -> ResolveCapabilityActionResponse:
    """Resolve canonical follow-up / rerun action state for a capability card."""
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        workspace_type = workspace_type_value(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    async with get_db_session() as cap_db:
        cap_result = await cap_db.execute(
            select(Capability).where(
                Capability.id == capability_id,
                Capability.workspace_type == workspace_type,
            )
        )
        capability = cap_result.scalars().first()
    if capability is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{capability_id}' not found for workspace type '{workspace_type}'",
        )

    from src.academic.services.artifact_service import ArtifactService

    artifacts = await ArtifactService(db).list_by_workspace(
        workspace_id=workspace_id,
        limit=200,
        offset=0,
    )
    payload = resolve_feature_action_state(
        feature_id=capability_id,
        workspace=workspace,
        artifacts=artifacts,
        orchestration_params=request.orchestration_params,
        explicit_source_artifact_id=request.source_artifact_id,
        follow_up_prompt=(capability.ui_meta or {}).get("follow_up_prompt") or "",
    )
    return ResolveCapabilityActionResponse(**payload)


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


@router.get(
    "/{workspace_id}/executions",
    response_model=WorkspaceExecutionsResponse,
)
async def list_workspace_executions(
    workspace_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceExecutionsResponse:
    """List execution records for a workspace."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    from src.database import get_db_session

    async with get_db_session() as db:
        from src.services.execution_service import serialize_execution_record

        service = ExecutionService(db)
        items = await service.list_executions(
            workspace_id=workspace_id,
            user_id=str(current_user.id),
            limit=limit,
        )
        serialized_items = [serialize_execution_record(item) for item in items]
    return WorkspaceExecutionsResponse(
        items=serialized_items,
        count=len(items),
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

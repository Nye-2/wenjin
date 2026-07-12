"""Workspaces router for workspace management API endpoints."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.academic.services.workspace_service import WorkspaceService
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.prism import (
    PrismFileContentUpdatePayload,
    PrismWorkspaceFileUpsertPayload,
)
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps import (
    get_dataservice_client,
    get_workspace_activity_service,
    get_workspace_service,
    get_workspace_summary_service,
)
from src.gateway.routers.workspaces_contracts import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceActivityResponse,
    WorkspacePrismEnsureResponse,
    WorkspacePrismFileContentResponse,
    WorkspacePrismFileSaveRequest,
    WorkspacePrismFileUpsertRequest,
    WorkspacePrismFileWriteResponse,
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
from src.services.workspace_activity_service import WorkspaceActivityService
from src.services.workspace_prism_service import WorkspacePrismService
from src.services.workspace_summary_service import WorkspaceSummaryService
from src.workspace_events import stream_workspace_events

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _workspace_prism_content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    return WorkspacesListResponse(workspaces=[workspace_to_response(w) for w in workspaces])


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspacePrismEnsureResponse:
    """Ensure a workspace-linked WenjinPrism project exists."""
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    projection = await WorkspacePrismService(dataservice=dataservice).ensure_surface_projection(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        project_name=str(workspace.name or ""),
    )
    return WorkspacePrismEnsureResponse(
        latex_project_id=projection.get("latex_project_id"),
        prism_project_id=projection.get("prism_project_id"),
        url=f"/workspaces/{workspace_id}/prism",
        sync_status="ready",
    )


@router.get(
    "/{workspace_id}/prism",
    response_model=WorkspacePrismSurfaceResponse,
)
async def get_workspace_prism_surface(
    workspace_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspacePrismSurfaceResponse:
    """Return the workspace-owned WenjinPrism surface projection."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        projection = await WorkspacePrismService(dataservice=dataservice).get_surface_projection(
            workspace_id,
            user_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace Prism surface not found",
        ) from exc
    return WorkspacePrismSurfaceResponse(**projection)


@router.post(
    "/{workspace_id}/prism/files",
    response_model=WorkspacePrismFileWriteResponse,
)
async def upsert_workspace_prism_file(
    workspace_id: str,
    request: WorkspacePrismFileUpsertRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspacePrismFileWriteResponse:
    """Create or replace a text-backed file in the workspace Prism surface."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    content_hash = _workspace_prism_content_hash(request.content_inline)
    result = await dataservice.upsert_prism_workspace_file(
        workspace_id,
        PrismWorkspaceFileUpsertPayload(
            path=request.path,
            file_role=request.file_role,
            mime_type=request.mime_type,
            content_inline=request.content_inline,
            content_hash=content_hash,
            created_by=str(current_user.id),
            metadata_json={"source": "user_edit"},
        ),
    )
    return WorkspacePrismFileWriteResponse(**result.model_dump(mode="json"))


@router.get(
    "/{workspace_id}/prism/files/{file_id}",
    response_model=WorkspacePrismFileContentResponse,
)
async def get_workspace_prism_file(
    workspace_id: str,
    file_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspacePrismFileContentResponse:
    """Read current Prism file content for the editor."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    record = await dataservice.get_prism_workspace_file(workspace_id, file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prism file not found",
        )
    return WorkspacePrismFileContentResponse(**record.model_dump(mode="json"))


@router.put(
    "/{workspace_id}/prism/files/{file_id}",
    response_model=WorkspacePrismFileWriteResponse,
)
async def save_workspace_prism_file(
    workspace_id: str,
    file_id: str,
    request: WorkspacePrismFileSaveRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspacePrismFileWriteResponse:
    """Autosave text content into a new Prism file version."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    result = await dataservice.update_prism_workspace_file(
        workspace_id,
        file_id,
        PrismFileContentUpdatePayload(
            content_inline=request.content_inline,
            content_hash=_workspace_prism_content_hash(request.content_inline),
            created_by=str(current_user.id),
            expected_current_hash=request.expected_current_hash,
            metadata_json={"source": "user_autosave"},
        ),
    )
    if result.skipped_reason == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prism file not found",
        )
    if result.skipped_reason == "hash_mismatch":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prism file changed before save",
        )
    return WorkspacePrismFileWriteResponse(**result.model_dump(mode="json"))


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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


@router.get("/{workspace_id}/summary", response_model=WorkspaceSummaryResponse)
async def get_workspace_summary(
    workspace_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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

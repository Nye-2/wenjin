"""Artifacts router for artifact management endpoints.

This module provides REST endpoints for:
- Creating artifacts
- Listing artifacts (filtered by workspace and type)
- Getting artifact details
- Updating artifacts
- Deleting artifacts
- Getting artifact lineage (parent chain)
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.database import User
from src.gateway.access_control import (
    owner_check_session_from_service as _owner_check_session_from_service,
)
from src.gateway.access_control import (
    require_workspace_owner_by_session as _require_workspace_owner,
)
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.artifact import (
    ArtifactResponse,
    ArtifactsListResponse,
    artifact_to_responses,
)
from src.gateway.deps import get_artifact_service
from src.gateway.resource_access import (
    ensure_workspace_owner_for_service as _ensure_workspace_owner_for_artifact_service,
)
from src.gateway.resource_access import (
    get_workspace_artifact_or_404 as _get_workspace_artifact_or_404,
)
from src.gateway.validators.artifact import (
    ArtifactCreatePayloadValidator,
    UpdateArtifactValidator,
)

router = APIRouter(tags=["artifacts"])

WorkspaceArtifactCreateRequest = ArtifactCreatePayloadValidator
WorkspaceArtifactUpdateRequest = UpdateArtifactValidator


async def _create_workspace_artifact(
    *,
    workspace_id: str,
    request: ArtifactCreatePayloadValidator,
    current_user: User,
    artifact_service,
) -> ArtifactResponse:
    """Create an artifact within a workspace-scoped canonical route."""
    await _ensure_workspace_owner_for_artifact_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifact = await artifact_service.create(
        workspace_id=workspace_id,
        type=request.type,
        title=request.title,
        content=request.content,
        created_by_skill=request.created_by_skill,
        parent_artifact_id=request.parent_artifact_id,
    )
    return artifact_to_responses([artifact])[0]


async def _list_workspace_artifacts(
    *,
    workspace_id: str,
    artifact_type: str | None,
    current_user: User,
    artifact_service,
) -> ArtifactsListResponse:
    """List artifacts within a workspace-scoped canonical route."""
    await _ensure_workspace_owner_for_artifact_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifacts = await artifact_service.list_by_workspace(
        workspace_id=workspace_id,
        type=artifact_type,
    )
    return ArtifactsListResponse(
        artifacts=artifact_to_responses(artifacts),
        count=len(artifacts),
    )


async def _get_workspace_artifact(
    *,
    workspace_id: str,
    artifact_id: str,
    current_user: User,
    artifact_service,
) -> ArtifactResponse:
    """Get a workspace-scoped artifact."""
    artifact = await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    return artifact_to_responses([artifact])[0]


async def _update_workspace_artifact(
    *,
    workspace_id: str,
    artifact_id: str,
    request: UpdateArtifactValidator,
    current_user: User,
    artifact_service,
) -> ArtifactResponse:
    """Update a workspace-scoped artifact."""
    await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifact = await artifact_service.update(
        artifact_id=artifact_id,
        title=request.title,
        content=request.content,
        status=request.status,
        increment_version=True,
    )
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    return artifact_to_responses([artifact])[0]


async def _delete_workspace_artifact(
    *,
    workspace_id: str,
    artifact_id: str,
    current_user: User,
    artifact_service,
) -> dict[str, object]:
    """Delete a workspace-scoped artifact."""
    await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    success = await artifact_service.delete(artifact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    return {"success": True, "artifact_id": artifact_id}


async def _get_workspace_artifact_lineage(
    *,
    workspace_id: str,
    artifact_id: str,
    current_user: User,
    artifact_service,
) -> list[ArtifactResponse]:
    """Get lineage for a workspace-scoped artifact."""
    await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    lineage = await artifact_service.get_lineage(artifact_id)
    return artifact_to_responses(lineage)


# ============ Endpoints ============

@router.post(
    "/workspaces/{workspace_id}/artifacts",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_artifact(
    workspace_id: str,
    request: WorkspaceArtifactCreateRequest,
    current_user: User = Depends(get_current_user),
    artifact_service=Depends(get_artifact_service),
):
    """Canonical workspace-scoped artifact creation route."""
    return await _create_workspace_artifact(
        workspace_id=workspace_id,
        request=request,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.get(
    "/workspaces/{workspace_id}/artifacts",
    response_model=ArtifactsListResponse,
)
async def list_workspace_artifacts(
    workspace_id: str,
    type: str | None = None,
    current_user: User = Depends(get_current_user),
    artifact_service=Depends(get_artifact_service),
):
    """Canonical workspace-scoped artifact list route."""
    return await _list_workspace_artifacts(
        workspace_id=workspace_id,
        artifact_type=type,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.get(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def get_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service=Depends(get_artifact_service),
):
    """Canonical workspace-scoped artifact detail route."""
    return await _get_workspace_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.put(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def update_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    request: WorkspaceArtifactUpdateRequest,
    current_user: User = Depends(get_current_user),
    artifact_service=Depends(get_artifact_service),
):
    """Canonical workspace-scoped artifact update route."""
    return await _update_workspace_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        request=request,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.delete("/workspaces/{workspace_id}/artifacts/{artifact_id}")
async def delete_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service=Depends(get_artifact_service),
):
    """Canonical workspace-scoped artifact delete route."""
    return await _delete_workspace_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.get(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}/lineage",
    response_model=list[ArtifactResponse],
)
async def get_workspace_artifact_lineage(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service=Depends(get_artifact_service),
):
    """Canonical workspace-scoped artifact lineage route."""
    return await _get_workspace_artifact_lineage(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        current_user=current_user,
        artifact_service=artifact_service,
    )

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
    artifact_to_response,
)
from src.gateway.dependencies import get_artifact_service
from src.gateway.resource_access import (
    ensure_workspace_owner_for_service as _ensure_workspace_owner_for_artifact_service,
)
from src.gateway.resource_access import (
    get_owned_artifact_or_404 as _get_owned_artifact_or_404,
)
from src.gateway.validators.artifact import (
    CreateArtifactValidator,
    UpdateArtifactValidator,
)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# Re-export validators as request models for backward compatibility
CreateArtifactRequest = CreateArtifactValidator
UpdateArtifactRequest = UpdateArtifactValidator


# ============ Endpoints ============

@router.post("", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    request: CreateArtifactRequest,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Create a new artifact.

    Creates an artifact in the specified workspace with the given content.

    Args:
        request: Artifact creation request with workspace_id, type, content, etc.
        artifact_service: Injected artifact service

    Returns:
        ArtifactResponse with created artifact details

    Raises:
        HTTPException: If workspace not found or creation fails
    """
    await _ensure_workspace_owner_for_artifact_service(
        artifact_service,
        workspace_id=request.workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifact = await artifact_service.create(
        workspace_id=request.workspace_id,
        type=request.type,
        title=request.title,
        content=request.content,
        created_by_skill=request.created_by_skill,
        parent_artifact_id=request.parent_artifact_id,
    )
    return artifact_to_response(artifact)


@router.get("", response_model=list[ArtifactResponse])
async def list_artifacts(
    workspace_id: str,
    type: str | None = None,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """List artifacts, filtered by workspace and optionally by type.

    Args:
        workspace_id: Workspace ID to filter artifacts
        type: Optional artifact type filter (research_idea, methodology, etc.)
        artifact_service: Injected artifact service

    Returns:
        List of ArtifactResponse objects
    """
    await _ensure_workspace_owner_for_artifact_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifacts = await artifact_service.list_by_workspace(
        workspace_id=workspace_id,
        type=type,
    )
    return [artifact_to_response(a) for a in artifacts]


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Get artifact by ID.

    Args:
        artifact_id: Artifact ID
        artifact_service: Injected artifact service

    Returns:
        ArtifactResponse with artifact details

    Raises:
        HTTPException: If artifact not found (404)
    """
    artifact = await _get_owned_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    return artifact_to_response(artifact)


@router.put("/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(
    artifact_id: str,
    request: UpdateArtifactRequest,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Update artifact.

    Updates the specified artifact with the provided fields.
    Only non-None fields in the request will be updated.

    Args:
        artifact_id: Artifact ID
        request: Update request with optional title, content, and status
        artifact_service: Injected artifact service

    Returns:
        ArtifactResponse with updated artifact details

    Raises:
        HTTPException: If artifact not found (404)
    """
    await _get_owned_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
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
    return artifact_to_response(artifact)


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Delete artifact.

    Permanently deletes the specified artifact.

    Args:
        artifact_id: Artifact ID
        artifact_service: Injected artifact service

    Returns:
        Success message

    Raises:
        HTTPException: If artifact not found (404)
    """
    await _get_owned_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
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
    return {"success": True, "message": "Artifact deleted successfully"}


@router.get("/{artifact_id}/lineage", response_model=list[ArtifactResponse])
async def get_artifact_lineage(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
):
    """Get artifact lineage (parent chain).

    Returns the lineage of the artifact from root to the specified artifact.
    This represents the chain of derived artifacts.

    Args:
        artifact_id: Artifact ID
        artifact_service: Injected artifact service

    Returns:
        List of ArtifactResponse objects representing the lineage

    Raises:
        HTTPException: If artifact not found (404)
    """
    await _get_owned_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    lineage = await artifact_service.get_lineage(artifact_id)
    return [artifact_to_response(a) for a in lineage]

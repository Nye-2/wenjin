"""Artifacts router for artifact management endpoints.

This module provides REST endpoints for:
- Creating artifacts
- Listing artifacts (filtered by workspace and type)
- Getting artifact details
- Updating artifacts
- Deleting artifacts
- Getting artifact lineage (parent chain)
"""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User, Workspace, get_db_session
from src.gateway.routers.auth import get_current_user
from src.gateway.validators.artifact import (
    CreateArtifactValidator,
    UpdateArtifactValidator,
)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ============ Request/Response Models ============

class ArtifactResponse(BaseModel):
    """Artifact response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    type: str
    title: str | None
    content: dict
    created_by_skill: str | None
    parent_artifact_id: str | None = None
    version: int
    status: str
    created_at: str
    updated_at: str


# Re-export validators as request models for backward compatibility
CreateArtifactRequest = CreateArtifactValidator
UpdateArtifactRequest = UpdateArtifactValidator


# ============ Dependencies ============

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with get_db_session() as session:
        yield session


async def get_artifact_service(db: AsyncSession = Depends(get_session)):
    """Get artifact service instance."""
    from src.academic.services import ArtifactService
    return ArtifactService(db)


# ============ Helper Functions ============

def orm_to_dict(obj) -> dict:
    """Convert SQLAlchemy ORM object to dict for Pydantic."""
    data = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        # Convert datetime to ISO format string
        if hasattr(value, 'isoformat'):
            value = value.isoformat()
        data[column.name] = value
    return data


def artifact_to_response(artifact) -> ArtifactResponse:
    """Convert Artifact ORM object to ArtifactResponse."""
    return ArtifactResponse(**orm_to_dict(artifact))


def _owner_check_session_from_service(artifact_service) -> AsyncSession | None:
    """Extract SQLAlchemy session from service for owner checks."""
    db = getattr(artifact_service, "db", None)
    return db if isinstance(db, AsyncSession) else None


async def _require_workspace_owner(
    session: AsyncSession,
    workspace_id: str,
    user_id: str,
) -> None:
    """Ensure workspace exists and is owned by user."""
    result = await session.execute(
        select(Workspace.user_id).where(Workspace.id == workspace_id)
    )
    owner_id = result.scalar_one_or_none()
    if owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    if str(owner_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


# ============ Endpoints ============

@router.post("/", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
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
    owner_session = _owner_check_session_from_service(artifact_service)
    if owner_session is not None:
        await _require_workspace_owner(
            owner_session,
            workspace_id=request.workspace_id,
            user_id=str(current_user.id),
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


@router.get("/", response_model=list[ArtifactResponse])
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
    owner_session = _owner_check_session_from_service(artifact_service)
    if owner_session is not None:
        await _require_workspace_owner(
            owner_session,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
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
    artifact = await artifact_service.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    owner_session = _owner_check_session_from_service(artifact_service)
    if owner_session is not None:
        await _require_workspace_owner(
            owner_session,
            workspace_id=str(artifact.workspace_id),
            user_id=str(current_user.id),
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
    existing_artifact = await artifact_service.get(artifact_id)
    if not existing_artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )

    owner_session = _owner_check_session_from_service(artifact_service)
    if owner_session is not None:
        await _require_workspace_owner(
            owner_session,
            workspace_id=str(existing_artifact.workspace_id),
            user_id=str(current_user.id),
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
    artifact = await artifact_service.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )

    owner_session = _owner_check_session_from_service(artifact_service)
    if owner_session is not None:
        await _require_workspace_owner(
            owner_session,
            workspace_id=str(artifact.workspace_id),
            user_id=str(current_user.id),
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
    # First verify the artifact exists
    artifact = await artifact_service.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    owner_session = _owner_check_session_from_service(artifact_service)
    if owner_session is not None:
        await _require_workspace_owner(
            owner_session,
            workspace_id=str(artifact.workspace_id),
            user_id=str(current_user.id),
        )

    lineage = await artifact_service.get_lineage(artifact_id)
    return [artifact_to_response(a) for a in lineage]

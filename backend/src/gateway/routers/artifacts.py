"""Artifacts router for artifact management endpoints.

This module provides REST endpoints for:
- Creating artifacts
- Listing artifacts (filtered by workspace and type)
- Getting artifact details
- Updating artifacts
- Deleting artifacts
- Getting artifact lineage (parent chain)
"""

from typing import Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db_session


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ============ Request/Response Models ============

class CreateArtifactRequest(BaseModel):
    """Artifact creation request."""
    workspace_id: str
    type: str  # research_idea, methodology, framework_outline, abstract, etc.
    title: Optional[str] = None
    content: dict
    created_by_skill: Optional[str] = None
    parent_artifact_id: Optional[str] = None


class UpdateArtifactRequest(BaseModel):
    """Artifact update request."""
    title: Optional[str] = None
    content: Optional[dict] = None
    status: Optional[str] = None


class ArtifactResponse(BaseModel):
    """Artifact response."""
    id: str
    workspace_id: str
    type: str
    title: Optional[str]
    content: dict
    created_by_skill: Optional[str]
    parent_artifact_id: Optional[str] = None
    version: int
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ============ Dependencies ============

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async for session in get_db_session():
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


# ============ Endpoints ============

@router.post("/", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    request: CreateArtifactRequest,
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
    type: Optional[str] = None,
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
    artifacts = await artifact_service.list_by_workspace(
        workspace_id=workspace_id,
        type=type,
    )
    return [artifact_to_response(a) for a in artifacts]


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
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
    return artifact_to_response(artifact)


@router.put("/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(
    artifact_id: str,
    request: UpdateArtifactRequest,
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

    lineage = await artifact_service.get_lineage(artifact_id)
    return [artifact_to_response(a) for a in lineage]

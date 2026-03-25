"""Shared artifact response contracts and serializers."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ArtifactResponse(BaseModel):
    """Canonical artifact response model shared across routers."""

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
    created_at: datetime
    updated_at: datetime


class ArtifactsListResponse(BaseModel):
    """List response for workspace artifact routes."""

    artifacts: list[ArtifactResponse]
    count: int


def artifact_to_response(artifact: Any) -> ArtifactResponse:
    """Convert an ORM artifact object into the shared response model."""
    parent_artifact_id = getattr(artifact, "parent_artifact_id", None)
    return ArtifactResponse(
        id=str(artifact.id),
        workspace_id=str(artifact.workspace_id),
        type=artifact.type,
        title=artifact.title,
        content=artifact.content or {},
        created_by_skill=artifact.created_by_skill,
        parent_artifact_id=str(parent_artifact_id) if parent_artifact_id else None,
        version=artifact.version,
        status=artifact.status,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def artifact_to_responses(artifacts: Iterable[Any]) -> list[ArtifactResponse]:
    """Convert multiple artifacts into shared response models."""
    return [artifact_to_response(artifact) for artifact in artifacts]

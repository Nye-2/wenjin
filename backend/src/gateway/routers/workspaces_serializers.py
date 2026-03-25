"""Serialization helpers for workspace router responses."""

from __future__ import annotations

from typing import Any

from src.database import Workspace
from src.gateway.routers.workspaces_contracts import (
    WorkspaceActivityItemResponse,
    WorkspaceResponse,
)
from src.services.workspace_activity_contracts import serialize_activity_item


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


def workspace_activity_to_response(item: dict[str, Any]) -> WorkspaceActivityItemResponse:
    """Convert a service activity item into the API response contract."""

    return WorkspaceActivityItemResponse(**serialize_activity_item(item))

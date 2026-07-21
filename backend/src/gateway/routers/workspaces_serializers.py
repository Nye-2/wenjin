"""Serialization helpers for workspace router responses."""

from __future__ import annotations

from typing import Any

from src.gateway.routers.workspaces_contracts import (
    WorkspaceActivityItemResponse,
    WorkspaceResponse,
)
from src.services.workspace_activity_contracts import serialize_activity_item


def workspace_to_response(workspace: Any) -> WorkspaceResponse:
    """Convert a Workspace ORM row or DataService projection to response model."""

    workspace_type = getattr(workspace, "workspace_type", None) or getattr(workspace, "type", None)
    workspace_type_value = workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)
    settings_json = getattr(workspace, "settings_json", None)
    config = settings_json if settings_json is not None else getattr(workspace, "config", None)
    created_by_user_id = getattr(workspace, "created_by_user_id", None)
    user_id = created_by_user_id if created_by_user_id is not None else workspace.user_id

    return WorkspaceResponse(
        id=str(workspace.id),
        user_id=str(user_id),
        name=workspace.name,
        type=workspace_type_value,
        description=workspace.description,
        config=config or {},
        created_at=workspace.created_at.isoformat() if workspace.created_at else "",
        updated_at=workspace.updated_at.isoformat() if workspace.updated_at else "",
    )


def workspace_activity_to_response(item: dict[str, Any]) -> WorkspaceActivityItemResponse:
    """Convert a service activity item into the API response contract."""

    return WorkspaceActivityItemResponse(**serialize_activity_item(item))

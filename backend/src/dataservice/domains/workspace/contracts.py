"""Workspace domain contracts."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.database.models.workspace import WorkspaceType


class WorkspaceMembershipRole(enum.StrEnum):
    """Workspace membership role."""

    OWNER = "owner"
    COLLABORATOR = "collaborator"
    VIEWER = "viewer"


class WorkspaceMembershipStatus(enum.StrEnum):
    """Workspace membership lifecycle status."""

    ACTIVE = "active"
    REVOKED = "revoked"


class WorkspaceCreateCommand(BaseModel):
    """Create workspace command."""

    created_by_user_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    workspace_type: WorkspaceType
    discipline: str | None = Field(default=None, max_length=100)
    description: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdateCommand(BaseModel):
    """Update workspace command."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    workspace_type: WorkspaceType | None = None
    discipline: str | None = Field(default=None, max_length=100)
    description: str | None = None
    settings_json: dict[str, Any] | None = None
    active_thread_id: str | None = None


class WorkspaceRecord(BaseModel):
    """Canonical workspace projection."""

    id: str
    created_by_user_id: str
    name: str
    workspace_type: WorkspaceType
    discipline: str | None = None
    description: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)
    active_thread_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

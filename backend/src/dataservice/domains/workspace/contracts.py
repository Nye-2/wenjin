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


class WorkspaceSettingsUpdateCommand(BaseModel):
    """Update mutable workspace settings."""

    default_model: str | None = Field(default=None, max_length=100)
    thinking_enabled: bool | None = None
    sandbox_provider: str | None = Field(default=None, max_length=50)
    auto_compact_threshold: float | None = None
    capability_overrides: dict[str, Any] | None = None
    settings_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


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


class WorkspaceSettingsRecord(BaseModel):
    """Workspace settings projection."""

    workspace_id: str
    default_model: str | None = None
    thinking_enabled: bool = True
    sandbox_provider: str = "local"
    auto_compact_threshold: float = 0.8
    capability_overrides: dict[str, Any] = Field(default_factory=dict)
    settings_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

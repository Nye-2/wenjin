"""Workspace domain contracts."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.reasoning import ReasoningEffort
from src.contracts.review_policy import DEFAULT_REVIEW_MODE, ReviewMode, normalize_review_mode
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

    model_config = ConfigDict(extra="forbid")

    default_model: str | None = Field(default=None, max_length=100)
    reasoning_effort: ReasoningEffort | None = None
    auto_compact_threshold: float | None = None
    settings_json: dict[str, Any] | None = None
    review_mode: ReviewMode | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("review_mode", mode="before")
    @classmethod
    def _normalize_review_mode(cls, value: Any) -> ReviewMode | None:
        if value is None:
            return None
        return normalize_review_mode(value)


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
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH
    auto_compact_threshold: float = 0.8
    settings_json: dict[str, Any] = Field(default_factory=dict)
    review_mode: ReviewMode = DEFAULT_REVIEW_MODE
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _sync_review_mode_from_settings_json(self) -> WorkspaceSettingsRecord:
        settings_json = dict(self.settings_json or {})
        mode = normalize_review_mode(settings_json.get("review_mode", self.review_mode))
        settings_json["review_mode"] = mode
        self.settings_json = settings_json
        self.review_mode = mode
        return self


class WorkspaceStatsRecord(BaseModel):
    """Workspace aggregate stats for user-facing dashboards."""

    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    created_last_7d: int


class WorkspaceAdminStatsRecord(BaseModel):
    """Workspace aggregate stats for admin dashboards."""

    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    users_with_workspaces: int

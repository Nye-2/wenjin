"""Workspace contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

WORKSPACE_TYPES = ("thesis", "sci", "proposal", "software_copyright", "patent")
THREAD_COCKPIT_DEFAULT_TYPES = set(WORKSPACE_TYPES)


def normalize_workspace_type(value: object) -> str:
    raw_value = getattr(value, "value", value)
    normalized = str(raw_value)
    if normalized not in WORKSPACE_TYPES:
        raise ValueError(f"Invalid workspace type: {value}. Must be one of: {list(WORKSPACE_TYPES)}")
    return normalized


def with_rollout_defaults(
    workspace_type: object,
    settings_json: dict[str, Any] | None,
) -> dict[str, Any]:
    resolved_type = normalize_workspace_type(workspace_type)
    base = dict(settings_json or {})
    rollout = base.get("rollout")
    rollout_config = dict(rollout) if isinstance(rollout, dict) else {}
    rollout_config.setdefault(
        "thread_cockpit_enabled",
        resolved_type in THREAD_COCKPIT_DEFAULT_TYPES,
    )
    base["rollout"] = rollout_config
    return base


class WorkspacePayload(BaseModel):
    """Canonical DataService workspace payload."""

    id: str
    created_by_user_id: str
    name: str
    workspace_type: str
    discipline: str | None = None
    description: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)
    active_thread_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def type(self) -> str:
        return self.workspace_type

    @property
    def config(self) -> dict[str, Any]:
        return self.settings_json

    @property
    def thread_id(self) -> str | None:
        return self.active_thread_id


class WorkspaceCreatePayload(BaseModel):
    """Client-facing workspace create payload."""

    created_by_user_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    workspace_type: str
    discipline: str | None = Field(default=None, max_length=100)
    description: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdatePayload(BaseModel):
    """Client-facing workspace update payload."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    workspace_type: str | None = None
    discipline: str | None = Field(default=None, max_length=100)
    description: str | None = None
    settings_json: dict[str, Any] | None = None
    active_thread_id: str | None = None


class WorkspaceSettingsPayload(BaseModel):
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


class WorkspaceSettingsUpdatePayload(BaseModel):
    """Mutable workspace settings update payload."""

    default_model: str | None = Field(default=None, max_length=100)
    thinking_enabled: bool | None = None
    sandbox_provider: str | None = Field(default=None, max_length=50)
    auto_compact_threshold: float | None = None
    capability_overrides: dict[str, Any] | None = None
    settings_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class WorkspaceStatsPayload(BaseModel):
    """Workspace aggregate stats for user-facing dashboards."""

    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    created_last_7d: int


class WorkspaceAdminStatsPayload(BaseModel):
    """Workspace aggregate stats for admin-facing dashboards."""

    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    users_with_workspaces: int

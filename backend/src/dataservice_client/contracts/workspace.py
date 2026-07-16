"""Workspace contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.reasoning import ReasoningEffort
from src.contracts.review_policy import DEFAULT_REVIEW_MODE, ReviewMode, normalize_review_mode

WORKSPACE_TYPES = ("thesis", "sci", "proposal", "software_copyright", "math_modeling", "patent")
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


def with_review_mode_default(settings_json: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(settings_json or {})
    base["review_mode"] = normalize_review_mode(base.get("review_mode"))
    return base


def with_workspace_settings_defaults(
    workspace_type: object,
    settings_json: dict[str, Any] | None,
) -> dict[str, Any]:
    return with_review_mode_default(with_rollout_defaults(workspace_type, settings_json))


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

    @model_validator(mode="after")
    def _sync_settings_defaults(self) -> WorkspacePayload:
        self.settings_json = with_workspace_settings_defaults(self.workspace_type, self.settings_json)
        return self

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
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH
    auto_compact_threshold: float = 0.8
    settings_json: dict[str, Any] = Field(default_factory=dict)
    review_mode: ReviewMode = DEFAULT_REVIEW_MODE
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _sync_review_mode_from_settings_json(self) -> WorkspaceSettingsPayload:
        settings_json = dict(self.settings_json or {})
        mode = normalize_review_mode(settings_json.get("review_mode", self.review_mode))
        settings_json["review_mode"] = mode
        self.settings_json = settings_json
        self.review_mode = mode
        return self


class WorkspaceSettingsUpdatePayload(BaseModel):
    """Mutable workspace settings update payload."""

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

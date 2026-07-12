"""Workspace domain policies."""

from __future__ import annotations

from typing import Any

from src.contracts.review_policy import normalize_review_mode
from src.database.models.workspace import WorkspaceType

THREAD_COCKPIT_DEFAULT_TYPES = {
    WorkspaceType.THESIS.value,
    WorkspaceType.SCI.value,
    WorkspaceType.PROPOSAL.value,
    WorkspaceType.SOFTWARE_COPYRIGHT.value,
    WorkspaceType.MATH_MODELING.value,
    WorkspaceType.PATENT.value,
}


def normalize_workspace_type(value: WorkspaceType | str) -> WorkspaceType:
    """Return a valid workspace type or raise ValueError."""
    if isinstance(value, WorkspaceType):
        return value
    try:
        return WorkspaceType(str(value))
    except ValueError:
        valid_types = [item.value for item in WorkspaceType]
        raise ValueError(f"Invalid workspace type: {value}. Must be one of: {valid_types}") from None


def with_rollout_defaults(
    workspace_type: WorkspaceType | str,
    settings_json: dict[str, Any] | None,
) -> dict[str, Any]:
    """Inject rollout defaults into workspace settings without overwriting overrides."""
    resolved_type = normalize_workspace_type(workspace_type)
    base = dict(settings_json or {})
    rollout = base.get("rollout")
    rollout_config = dict(rollout) if isinstance(rollout, dict) else {}
    rollout_config.setdefault("thread_cockpit_enabled", resolved_type.value in THREAD_COCKPIT_DEFAULT_TYPES)
    base["rollout"] = rollout_config
    return base


def with_review_mode_default(settings_json: dict[str, Any] | None) -> dict[str, Any]:
    """Inject the workspace write-mode default without overwriting valid overrides."""
    base = dict(settings_json or {})
    base["review_mode"] = normalize_review_mode(base.get("review_mode"))
    return base


def with_workspace_settings_defaults(
    workspace_type: WorkspaceType | str,
    settings_json: dict[str, Any] | None,
) -> dict[str, Any]:
    """Inject all workspace settings defaults without overwriting valid overrides."""
    return with_review_mode_default(with_rollout_defaults(workspace_type, settings_json))

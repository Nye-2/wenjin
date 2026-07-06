"""Tests for DataService workspace contract helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.dataservice.domains.workspace.policies import (
    with_rollout_defaults,
    with_workspace_settings_defaults,
)
from src.dataservice_client.contracts.workspace import (
    WORKSPACE_TYPES,
    WorkspaceSettingsPayload,
    WorkspaceSettingsUpdatePayload,
    normalize_workspace_type,
)


def test_math_modeling_workspace_type_is_supported() -> None:
    assert "math_modeling" in WORKSPACE_TYPES
    assert normalize_workspace_type("math_modeling") == "math_modeling"


def test_math_modeling_workspace_enables_thread_cockpit_by_default() -> None:
    settings = with_rollout_defaults("math_modeling", {})
    assert settings["rollout"]["thread_cockpit_enabled"] is True


def test_workspace_defaults_include_auto_draft_write_mode() -> None:
    settings = with_workspace_settings_defaults("thesis", {})
    assert settings["write_mode"] == "auto_draft"


def test_client_workspace_settings_payload_projects_missing_write_mode_default() -> None:
    payload = WorkspaceSettingsPayload.model_validate(
        {
            "workspace_id": "ws-1",
            "settings_json": {"language": "zh"},
        }
    )

    assert payload.write_mode == "auto_draft"
    assert payload.settings_json == {"language": "zh", "write_mode": "auto_draft"}


def test_client_workspace_settings_update_accepts_valid_write_mode() -> None:
    payload = WorkspaceSettingsUpdatePayload(write_mode="ask_workspace_write")

    assert payload.write_mode == "ask_workspace_write"


def test_client_workspace_settings_update_trims_write_mode() -> None:
    payload = WorkspaceSettingsUpdatePayload(write_mode=" strict_review ")

    assert payload.write_mode == "strict_review"


def test_client_workspace_settings_update_preserves_null_write_mode() -> None:
    payload = WorkspaceSettingsUpdatePayload(write_mode=None)

    assert payload.write_mode is None


def test_client_workspace_settings_update_rejects_invalid_write_mode() -> None:
    with pytest.raises(ValidationError):
        WorkspaceSettingsUpdatePayload(write_mode="manual_review")

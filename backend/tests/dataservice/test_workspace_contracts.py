"""Tests for DataService workspace contract helpers."""

from __future__ import annotations

from src.dataservice_client.contracts.workspace import WORKSPACE_TYPES, normalize_workspace_type
from src.dataservice.domains.workspace.policies import with_rollout_defaults


def test_math_modeling_workspace_type_is_supported() -> None:
    assert "math_modeling" in WORKSPACE_TYPES
    assert normalize_workspace_type("math_modeling") == "math_modeling"


def test_math_modeling_workspace_enables_thread_cockpit_by_default() -> None:
    settings = with_rollout_defaults("math_modeling", {})
    assert settings["rollout"]["thread_cockpit_enabled"] is True

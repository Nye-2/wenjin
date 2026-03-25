"""Registry-to-graph sync checks for workspace feature execution."""

from __future__ import annotations

from src.agents import workspace_lead_agent
from src.workspace_features import CANONICAL_WORKSPACE_TYPES, list_workspace_features


def test_workspace_registry_features_all_have_loadable_graphs() -> None:
    expected_keys: set[str] = set()

    for workspace_type in CANONICAL_WORKSPACE_TYPES:
        workspace_lead_agent._ensure_graphs_loaded(workspace_type)
        expected_keys.update(
            f"{workspace_type}.{feature.id}"
            for feature in list_workspace_features(workspace_type)
        )

    missing = sorted(
        key for key in expected_keys if key not in workspace_lead_agent._FEATURE_GRAPH_REGISTRY
    )
    assert not missing, f"Missing graph registrations for: {missing}"

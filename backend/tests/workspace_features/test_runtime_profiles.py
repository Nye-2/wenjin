"""Tests for workspace feature runtime profiles."""

from __future__ import annotations

from src.workspace_features import (
    FeatureRuntimeMode,
    get_feature_runtime_profile,
    iter_feature_runtime_profiles,
    iter_workspace_features,
)
from src.workspace_features.registry import FIGURE_GENERATION_GRAPH_MODULE


def test_runtime_profiles_cover_every_registered_feature() -> None:
    feature_keys = {
        (feature.workspace_type, feature.id)
        for feature in iter_workspace_features()
    }
    profile_keys = {
        (profile.workspace_type, profile.feature_id)
        for profile in iter_feature_runtime_profiles()
    }

    assert profile_keys == feature_keys


def test_agentic_runtime_profiles_are_explicit() -> None:
    profile = get_feature_runtime_profile("thesis", "deep_research")

    assert profile is not None
    assert profile.runtime_mode == FeatureRuntimeMode.COMPUTE_AGENTIC
    assert profile.allowed_subagents == (
        "scout",
        "trend_spotter",
        "gap_miner",
        "synthesizer",
    )
    assert profile.max_subagents == 4
    assert profile.output_contract == "evidence_pack"


def test_non_agentic_feature_defaults_to_compute_workflow() -> None:
    profile = get_feature_runtime_profile("sci", "framework_outline")

    assert profile is not None
    assert profile.runtime_mode == FeatureRuntimeMode.COMPUTE_WORKFLOW
    assert profile.allowed_subagents == ()
    assert profile.max_subagents == 0


def test_shared_figure_generation_graph_module_lives_in_feature_registry() -> None:
    figure_features = [
        feature
        for feature in iter_workspace_features()
        if feature.id == "figure_generation"
    ]

    assert figure_features
    assert {
        feature.graph_module for feature in figure_features
    } == {FIGURE_GENERATION_GRAPH_MODULE}

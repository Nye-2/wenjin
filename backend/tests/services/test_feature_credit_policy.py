"""Tests for feature_credit_policy – the single source of truth for billing rules."""

import pytest

from src.services.feature_credit_policy import (
    FEATURE_COSTS,
    BILLABLE_TASK_TYPES,
    get_feature_cost,
)


class TestFeatureCosts:
    def test_thesis_writing_has_nested_actions(self):
        costs = FEATURE_COSTS["thesis_writing"]
        assert isinstance(costs, dict)
        assert "generate_outline" in costs
        assert "write_chapter" in costs
        assert "write_all" in costs

    def test_top_level_features_are_ints(self):
        for key, value in FEATURE_COSTS.items():
            if key == "thesis_writing":
                continue
            assert isinstance(value, int), f"{key} should be int, got {type(value)}"


class TestBillableTaskTypes:
    def test_contains_core_types(self):
        assert "workspace_feature" in BILLABLE_TASK_TYPES
        assert "deep_research" in BILLABLE_TASK_TYPES
        assert "thesis_generation" in BILLABLE_TASK_TYPES
        assert "literature_search" in BILLABLE_TASK_TYPES

    def test_is_frozen_set(self):
        assert isinstance(BILLABLE_TASK_TYPES, frozenset)


class TestGetFeatureCost:
    def test_simple_feature(self):
        assert get_feature_cost("deep_research") == 100

    def test_nested_feature_with_action(self):
        assert get_feature_cost("thesis_writing", "generate_outline") == 20

    def test_nested_feature_without_action_uses_default(self):
        assert get_feature_cost("thesis_writing") == 200

    def test_unknown_feature_returns_zero(self):
        assert get_feature_cost("nonexistent_feature") == 0

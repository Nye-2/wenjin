"""Registry v2: each feature definition carries its credit cost."""

from src.workspace_features.registry import (
    get_workspace_feature,
    iter_workspace_features,
)


def test_every_feature_has_credit_cost():
    """Every registered feature must declare a credit cost (int or dict)."""
    missing = []
    for feature in iter_workspace_features():
        if not hasattr(feature, "credit_cost") or feature.credit_cost is None:
            missing.append(feature.id)
    assert not missing, f"Features missing credit_cost: {missing}"


def test_thesis_writing_has_action_costs():
    """thesis_writing declares per-action costs as a dict."""
    feature = get_workspace_feature("thesis", "thesis_writing")
    assert isinstance(feature.credit_cost, dict), (
        f"Expected dict, got {type(feature.credit_cost)}"
    )
    assert "write_chapter" in feature.credit_cost
    assert "write_all" in feature.credit_cost


def test_deep_research_has_integer_cost():
    """Simple features have integer credit costs."""
    feature = get_workspace_feature("thesis", "deep_research")
    assert isinstance(feature.credit_cost, int)
    assert feature.credit_cost > 0

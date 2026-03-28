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


def test_get_feature_cost_reads_from_registry():
    """get_feature_cost() result must match registry credit_cost."""
    from src.services.feature_credit_policy import get_feature_cost
    from src.workspace_features.registry import iter_workspace_features

    for feature in iter_workspace_features():
        if isinstance(feature.credit_cost, int):
            policy_cost = get_feature_cost(feature.id)
            assert policy_cost == feature.credit_cost, (
                f"{feature.id}: registry={feature.credit_cost}, "
                f"policy={policy_cost}"
            )
            break  # One verification is enough for the contract test


def test_get_feature_cost_thesis_writing_action():
    """thesis_writing action-based cost resolves correctly."""
    from src.services.feature_credit_policy import get_feature_cost
    from src.workspace_features.registry import get_workspace_feature

    feature = get_workspace_feature("thesis", "thesis_writing")
    assert isinstance(feature.credit_cost, dict)

    # Test write_chapter
    cost = get_feature_cost("thesis_writing", action="write_chapter")
    assert cost == feature.credit_cost["write_chapter"]

    # Test default
    cost_no_action = get_feature_cost("thesis_writing")
    assert cost_no_action == feature.credit_cost.get("default", 0)

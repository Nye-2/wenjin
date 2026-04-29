"""Workspace feature registry contract tests."""

from src.workspace_features.registry import iter_workspace_features


def test_feature_registry_does_not_own_billing_policy() -> None:
    """Feature definitions should not carry fixed billing prices."""
    violations = [
        feature.id
        for feature in iter_workspace_features()
        if hasattr(feature, "credit_cost")
    ]
    assert not violations, f"Feature registry leaked billing policy: {violations}"


def test_every_feature_has_follow_up_prompt():
    """Every registered feature must have a non-empty follow_up_prompt."""
    missing = [
        f.id for f in iter_workspace_features()
        if not getattr(f, "follow_up_prompt", None)
    ]
    assert not missing, f"Features missing follow_up_prompt: {missing}"


def test_api_dict_includes_follow_up_prompt():
    """to_api_dict() must include a non-None followUpPrompt key for every feature."""
    for feature in iter_workspace_features():
        api = feature.to_api_dict()
        assert "followUpPrompt" in api, f"{feature.id} missing followUpPrompt in to_api_dict()"
        assert api["followUpPrompt"] is not None, f"{feature.id} followUpPrompt is None"

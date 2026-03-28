"""Artifact builder dispatch: every registered feature has a builder."""

from src.task.workspace_feature_artifacts import _ARTIFACT_BUILDERS
from src.workspace_features.registry import iter_workspace_features


def test_every_feature_has_artifact_builder():
    """Every feature in the registry must have a registered artifact builder."""
    missing = [
        f.id
        for f in iter_workspace_features()
        if f.id not in _ARTIFACT_BUILDERS
    ]
    assert not missing, f"Features missing artifact builder: {missing}"

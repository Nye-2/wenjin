"""Tests for thesis workspace feature registry updates."""

from src.workspace_features.registry import get_workspace_feature, list_workspace_features


class TestThesisRegistryUpdate:
    """Tests verifying thesis feature registry design."""

    def test_thesis_has_five_features(self):
        features = list_workspace_features("thesis")
        assert len(features) == 5

    def test_thesis_feature_ids(self):
        features = list_workspace_features("thesis")
        ids = [f.id for f in features]
        assert ids == [
            "deep_research",
            "literature_management",
            "opening_research",
            "thesis_writing",
            "figure_generation",
        ]

    def test_deep_research_feature_exists(self):
        f = get_workspace_feature("thesis", "deep_research")
        assert f is not None
        assert f.id == "deep_research"

    def test_thesis_writing_feature_exists(self):
        f = get_workspace_feature("thesis", "thesis_writing")
        assert f is not None
        assert f.id == "thesis_writing"

    def test_literature_management_has_no_panel(self):
        f = get_workspace_feature("thesis", "literature_management")
        assert f is not None
        assert f.panel is None

    def test_old_thesis_features_removed(self):
        """Old feature IDs should no longer exist."""
        for old_id in ("outline", "literature", "chapter", "figure", "compile", "export"):
            assert get_workspace_feature("thesis", old_id) is None

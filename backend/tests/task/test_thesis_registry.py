"""Tests for thesis workspace feature registry updates."""

from src.workspace_features.registry import (
    get_workspace_feature,
    get_workspace_feature_by_handler,
    list_workspace_features,
)


class TestThesisRegistryUpdate:
    """Tests verifying the new 6-module thesis feature design."""

    def test_thesis_has_six_features(self):
        features = list_workspace_features("thesis")
        assert len(features) == 6

    def test_thesis_feature_ids(self):
        features = list_workspace_features("thesis")
        ids = [f.id for f in features]
        assert ids == [
            "deep_research",
            "literature_management",
            "opening_research",
            "thesis_writing",
            "figure_generation",
            "compile_export",
        ]

    def test_deep_research_feature_uses_workspace_feature_task_type(self):
        f = get_workspace_feature("thesis", "deep_research")
        assert f is not None
        assert f.task_type == "workspace_feature"
        assert f.handler_key == "thesis.deep_research"

    def test_thesis_writing_uses_workspace_feature_task_type(self):
        f = get_workspace_feature("thesis", "thesis_writing")
        assert f is not None
        assert f.task_type == "workspace_feature"
        assert f.handler_key == "thesis.thesis_writing"

    def test_literature_management_has_no_panel(self):
        f = get_workspace_feature("thesis", "literature_management")
        assert f is not None
        assert f.panel is None
        assert f.task_type == "workspace_feature"

    def test_all_handler_keys_unique(self):
        features = list_workspace_features("thesis")
        keys = [f.handler_key for f in features]
        assert len(keys) == len(set(keys))

    def test_old_thesis_features_removed(self):
        """Old feature IDs should no longer exist."""
        for old_id in ("outline", "literature", "chapter", "figure", "compile", "export"):
            assert get_workspace_feature("thesis", old_id) is None

    def test_old_handler_keys_removed(self):
        for old_key in (
            "thesis.outline",
            "thesis.literature",
            "thesis.chapter",
            "thesis.figure",
            "thesis.compile",
            "thesis.export",
        ):
            assert get_workspace_feature_by_handler(old_key) is None

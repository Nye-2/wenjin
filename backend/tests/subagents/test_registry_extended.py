"""Tests for extended subagent registry."""

from src.subagents.academic.registry import registry


class TestExtendedSubagentRegistry:
    def test_has_gap_miner_subagent(self):
        """Gap Miner subagent should be registered."""
        config = registry.get("gap_miner")
        assert config is not None
        assert "read_file" in config.tools

    def test_has_trend_spotter_subagent(self):
        """Trend Spotter subagent should be registered."""
        config = registry.get("trend_spotter")
        assert config is not None
        assert "search_workspace_references" in config.tools

    def test_has_reviewer_subagent(self):
        """Reviewer subagent should be registered."""
        config = registry.get("reviewer")
        assert config is not None
        assert "read_file" in config.tools

    def test_all_academic_subagents_count(self):
        """Should have at least 7 academic subagent types."""
        all_configs = registry.list_all()
        assert len(all_configs) >= 7

    def test_subagent_max_turns_configurable(self):
        """Subagent max_turns should be configurable."""
        config = registry.get("scout")
        assert config.max_turns > 0

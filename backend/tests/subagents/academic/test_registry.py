"""Tests for academic subagent registry."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.subagents.academic.prompts import (
    ANALYST_PROMPT,
    SCOUT_PROMPT,
    SYNTHESIZER_PROMPT,
    WRITER_PROMPT,
)
from src.subagents.academic.registry import (
    SubagentConfig,
    get_all_subagent_types,
    get_subagent_config,
)


class TestSubagentConfig:
    """Tests for SubagentConfig dataclass."""

    def test_subagent_config_creation(self):
        """Test creating a SubagentConfig instance."""
        config = SubagentConfig(
            name="TestAgent",
            description="A test agent",
            system_prompt="You are a test agent.",
            tools=["tool1", "tool2"],
            max_turns=5,
        )
        assert config.name == "TestAgent"
        assert config.description == "A test agent"
        assert config.system_prompt == "You are a test agent."
        assert config.tools == ["tool1", "tool2"]
        assert config.max_turns == 5

    def test_subagent_config_default_max_turns(self):
        """Test that max_turns defaults to 10."""
        config = SubagentConfig(
            name="TestAgent",
            description="A test agent",
            system_prompt="You are a test agent.",
            tools=[],
        )
        assert config.max_turns == 10


class TestSubagentPrompts:
    """Tests for subagent system prompts."""

    def test_scout_prompt_exists(self):
        """Test that SCOUT_PROMPT is defined and non-empty."""
        assert SCOUT_PROMPT is not None
        assert len(SCOUT_PROMPT) > 0
        assert "literature" in SCOUT_PROMPT.lower()
        assert "semantic_scholar" in SCOUT_PROMPT.lower()

    def test_writer_prompt_exists(self):
        """Test that WRITER_PROMPT is defined and non-empty."""
        assert WRITER_PROMPT is not None
        assert len(WRITER_PROMPT) > 0
        assert "writing" in WRITER_PROMPT.lower() or "academic" in WRITER_PROMPT.lower()

    def test_synthesizer_prompt_exists(self):
        """Test that SYNTHESIZER_PROMPT is defined and non-empty."""
        assert SYNTHESIZER_PROMPT is not None
        assert len(SYNTHESIZER_PROMPT) > 0
        assert "insight" in SYNTHESIZER_PROMPT.lower() or "gap" in SYNTHESIZER_PROMPT.lower()

    def test_analyst_prompt_exists(self):
        """Test that ANALYST_PROMPT is defined and non-empty."""
        assert ANALYST_PROMPT is not None
        assert len(ANALYST_PROMPT) > 0
        assert "analysis" in ANALYST_PROMPT.lower() or "methodology" in ANALYST_PROMPT.lower()


class TestSubagentRegistry:
    """Tests for the subagent registry."""

    def test_registry_has_required_subagents(self):
        """Test that the registry contains the required subagents."""
        all_types = get_all_subagent_types()
        # Core academic subagents
        assert "scout" in all_types
        assert "writer" in all_types
        assert "synthesizer" in all_types
        assert "analyst" in all_types
        # Research workflow specialists migrated from the legacy registry
        assert "gap_miner" in all_types
        assert "trend_spotter" in all_types
        assert "reviewer" in all_types
        # Thesis-specific subagents
        assert "thesis_writer" in all_types
        assert "librarian" in all_types
        assert "figure_planner" in all_types
        # Ensure the unified registry preserves the full role set
        assert len(all_types) >= 10

    def test_get_scout_config(self):
        """Test getting scout subagent configuration."""
        config = get_subagent_config("scout")
        assert config is not None
        assert config.name == "Scout"
        assert "semantic_scholar_search" in config.tools
        assert config.max_turns == 10

    def test_get_writer_config(self):
        """Test getting writer subagent configuration."""
        config = get_subagent_config("writer")
        assert config is not None
        assert config.name == "Writer"
        assert "get_paper_section" in config.tools
        assert "get_paper_toc" in config.tools
        assert config.max_turns == 15

    def test_get_synthesizer_config(self):
        """Test getting synthesizer subagent configuration."""
        config = get_subagent_config("synthesizer")
        assert config is not None
        assert config.name == "Synthesizer"
        assert "get_paper_section" in config.tools
        assert "get_paper_toc" in config.tools
        assert config.max_turns == 10

    def test_get_analyst_config(self):
        """Test getting analyst subagent configuration."""
        config = get_subagent_config("analyst")
        assert config is not None
        assert config.name == "Analyst"
        assert "get_paper_section" in config.tools
        assert config.max_turns == 10

    def test_get_invalid_subagent_raises_error(self):
        """Test that requesting an invalid subagent type raises an error."""
        with pytest.raises(ValueError, match="Unknown subagent type"):
            get_subagent_config("nonexistent")

    def test_all_configs_have_required_fields(self):
        """Test that all subagent configs have required fields."""
        for subagent_type in get_all_subagent_types():
            config = get_subagent_config(subagent_type)
            assert config.name is not None
            assert config.description is not None
            assert config.system_prompt is not None
            assert isinstance(config.tools, list)
            assert len(config.tools) > 0
            assert config.max_turns > 0

    def test_registry_applies_app_config_overrides(self):
        override_cfg = SimpleNamespace(
            subagents=SimpleNamespace(
                types={
                    "scout": SimpleNamespace(
                        allowed_tools=["read_file"],
                        disallowed_tools=["semantic_scholar_search"],
                        max_turns=6,
                        timeout=321,
                        model_name="resolved-tool-model",
                    )
                }
            )
        )

        with patch(
            "src.subagents.academic.registry.get_app_config",
            return_value=override_cfg,
        ):
            config = get_subagent_config("scout", apply_runtime_overrides=True)

        assert config.tools == ["read_file"]
        assert config.disallowed_tools == ["semantic_scholar_search"]
        assert config.max_turns == 6
        assert config.timeout == 321
        assert config.model_name == "resolved-tool-model"

class TestSubagentToolAssignments:
    """Tests for correct tool assignments to subagents."""

    def test_scout_has_semantic_scholar_only(self):
        """Test that Scout only has semantic_scholar_search tool."""
        config = get_subagent_config("scout")
        assert config.tools == ["semantic_scholar_search"]

    def test_writer_has_paper_tools(self):
        """Test that Writer has get_paper_section and get_paper_toc."""
        config = get_subagent_config("writer")
        assert "get_paper_section" in config.tools
        assert "get_paper_toc" in config.tools

    def test_synthesizer_has_paper_tools(self):
        """Test that Synthesizer has get_paper_section and get_paper_toc."""
        config = get_subagent_config("synthesizer")
        assert "get_paper_section" in config.tools
        assert "get_paper_toc" in config.tools

    def test_analyst_has_paper_section_only(self):
        """Test that Analyst only has get_paper_section tool."""
        config = get_subagent_config("analyst")
        assert config.tools == ["get_paper_section"]

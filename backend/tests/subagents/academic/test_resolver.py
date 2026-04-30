"""Tests for AcademicAgentResolver."""

import pytest

from src.subagents.academic.errors import InvalidToolError, UnknownSubagentTypeError
from src.subagents.academic.resolver import AcademicAgentResolver


class TestAcademicAgentResolver:
    """Tests for AcademicAgentResolver."""

    @pytest.fixture
    def sandbox_tools(self):
        """Create mock sandbox tools."""
        return {
            "read_file": lambda p: f"read: {p}",
            "list_workspace_reference_outline": lambda workspace_id: f"outline: {workspace_id}",
            "search_workspace_references": lambda q: f"reference search: {q}",
            "read_workspace_reference_section": lambda s: f"section: {s}",
            "python_exec": lambda c: f"exec: {c}",
            "web_search": lambda q: f"web: {q}",
        }

    @pytest.fixture
    def resolver(self, sandbox_tools):
        """Create resolver instance."""
        return AcademicAgentResolver(sandbox_tools)

    def test_accepts_tool_sequences(self):
        """Resolver should normalize tool lists into a name mapping."""

        class _Tool:
            def __init__(self, name: str):
                self.name = name

        resolver = AcademicAgentResolver([_Tool("read_file"), _Tool("write_file")])

        config = resolver.resolve_config("scout", requested_tools=["read_file"])

        assert config.tools == ["read_file"]

    def test_resolve_config_valid_scout(self, resolver):
        """Test resolving scout configuration."""
        config = resolver.resolve_config("scout")
        assert config.name == "Scout"
        assert "list_workspace_reference_outline" in config.tools
        assert "search_workspace_references" in config.tools
        assert config.system_prompt is not None

    def test_resolve_config_valid_writer(self, resolver):
        """Test resolving writer configuration."""
        config = resolver.resolve_config("writer")
        assert config.name == "Writer"
        assert "read_workspace_reference_section" in config.tools

    def test_resolve_config_valid_synthesizer(self, resolver):
        """Test resolving synthesizer configuration."""
        config = resolver.resolve_config("synthesizer")
        assert config.name == "Synthesizer"

    def test_resolve_config_valid_analyst(self, resolver):
        """Test resolving analyst configuration."""
        config = resolver.resolve_config("analyst")
        assert config.name == "Analyst"

    def test_resolve_config_invalid_type_raises(self, resolver):
        """Test that invalid type raises UnknownSubagentTypeError."""
        with pytest.raises(UnknownSubagentTypeError) as exc_info:
            resolver.resolve_config("researcher")
        assert exc_info.value.subagent_type == "researcher"

    def test_resolve_config_with_tool_override(self, resolver):
        """Test resolving config with custom tools."""
        config = resolver.resolve_config("scout", requested_tools=["read_file", "search_workspace_references"])
        assert "read_file" in config.tools
        assert "search_workspace_references" in config.tools
        # Should only have requested tools, not all sandbox tools
        assert len(config.tools) == 2

    def test_resolve_config_rejects_retired_search_tool_override(self, resolver):
        """Academic agents should not opt back into retired web/arXiv discovery."""
        config = resolver.resolve_config("scout", requested_tools=["read_file", "web_search"])
        assert "read_file" in config.tools
        assert "web_search" not in config.tools

    def test_resolve_config_with_invalid_tool_in_override(self, resolver):
        """Test that invalid tools in override are filtered out."""
        config = resolver.resolve_config(
            "scout",
            requested_tools=["read_file", "nonexistent_tool"]
        )
        assert "read_file" in config.tools
        assert "nonexistent_tool" not in config.tools

    def test_resolve_config_all_invalid_tools_raises(self, resolver):
        """Test that all invalid tools raises InvalidToolError."""
        with pytest.raises(InvalidToolError) as exc_info:
            resolver.resolve_config("scout", requested_tools=["fake1", "fake2"])
        assert exc_info.value.tool_name in ["fake1", "fake2"]

    def test_resolve_config_merges_all_sandbox_tools_by_default(self, resolver, sandbox_tools):
        """Test that default behavior merges all sandbox tools."""
        config = resolver.resolve_config("scout")
        # Should have base tools + all sandbox tools
        for tool_name in set(sandbox_tools.keys()) - {"web_search"}:
            assert tool_name in config.tools
        assert "web_search" not in config.tools

    def test_validate_tools_filters_invalid(self, resolver):
        """Test _validate_tools filters out invalid tools."""
        valid = resolver._validate_tools(["read_file", "fake_tool"])
        assert "read_file" in valid
        assert "fake_tool" not in valid

    def test_merge_default_tools_includes_all_sandbox(self, resolver, sandbox_tools):
        """Test _merge_default_tools includes all sandbox tools."""
        merged = resolver._merge_default_tools(["search_workspace_references"])
        for tool_name in set(sandbox_tools.keys()) - {"web_search"}:
            assert tool_name in merged
        assert "web_search" not in merged

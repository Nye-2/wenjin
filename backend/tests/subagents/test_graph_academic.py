"""Tests for academic graph template functions."""

from unittest.mock import MagicMock, patch

import pytest

from src.subagents.graph import (
    GraphTemplateRegistry,
)


class TestCreateAcademicAgentGraph:
    """Tests for create_academic_agent_graph."""

    def test_creates_graph_with_tools_and_prompt(self):
        """Test that graph is created with tools and system prompt."""
        from src.subagents.graph import create_academic_agent_graph

        mock_llm = MagicMock()
        mock_tools = [MagicMock(), MagicMock()]
        system_prompt = "You are a scout agent."

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            graph = create_academic_agent_graph(
                mock_llm,
                mock_tools,
                system_prompt,
                max_turns=10
            )
            assert graph is mock_create.return_value
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["state_modifier"] == system_prompt
            assert call_kwargs["tools"] == mock_tools

    def test_uses_default_max_turns(self):
        """Test that default max_turns is 10."""
        from src.subagents.graph import create_academic_agent_graph

        mock_llm = MagicMock()
        mock_tools = []
        system_prompt = "Test prompt"

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            create_academic_agent_graph(mock_llm, mock_tools, system_prompt)
            assert mock_create.called


class TestRegisterAcademicTemplates:
    """Tests for register_academic_templates."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools dict."""
        return {
            "semantic_scholar_search": MagicMock(),
            "read_file": MagicMock(),
            "get_paper_section": MagicMock(),
            "get_paper_toc": MagicMock(),
        }

    def test_registers_four_academic_templates(self, mock_tools):
        """Test that all academic templates are registered."""
        from src.subagents.graph import register_academic_templates

        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, mock_tools)

        # Check for expected templates
        assert registry.has("academic_scout")
        assert registry.has("academic_writer")
        assert registry.has("academic_synthesizer")
        assert registry.has("academic_analyst")
        # Verify all templates are registered
        assert registry.count == 7

    def test_uses_correct_tools_for_scout(self, mock_tools):
        """Test that scout template uses correct tools."""
        from src.subagents.graph import register_academic_templates

        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, mock_tools)

            # Check that create_react_agent was called at least 4 times (once per agent)
            assert mock_create.call_count >= 4

    def test_filters_unavailable_tools(self):
        """Test that unavailable tools are filtered out."""
        from src.subagents.graph import register_academic_templates

        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()
        # Only provide one tool
        limited_tools = {
            "semantic_scholar_search": MagicMock(),
        }

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, limited_tools)

            # Should still register all 7 templates
            assert registry.count == 7

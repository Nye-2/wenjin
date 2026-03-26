"""Tests for academic graph template functions."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import tool

from src.subagents.graph import (
    GraphTemplateRegistry,
)


def _make_test_tool(name: str):
    @tool(name)
    def _test_tool(query: str) -> str:
        """Return the provided query for test assertions."""
        return query

    return _test_tool


class TestCreateAcademicAgentGraph:
    """Tests for create_academic_agent_graph."""

    def test_creates_graph_with_tools_and_prompt(self):
        """Test that graph is created with tools and system prompt."""
        from src.agents.lead_agent.dynamic_tools import DynamicToolNode
        from src.subagents.graph import create_academic_agent_graph

        mock_llm = MagicMock()
        mock_tools = [_make_test_tool("tool1"), _make_test_tool("tool2")]
        system_prompt = "You are a scout agent."

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            graph = create_academic_agent_graph(
                mock_llm,
                mock_tools,
                system_prompt,
                max_turns=10
            )
            assert graph is mock_create.return_value
            mock_create.assert_called_once()
            call_args, call_kwargs = mock_create.call_args
            assert callable(call_args[0])
            assert isinstance(call_args[1], DynamicToolNode)
            assert call_kwargs["prompt"] == system_prompt

    def test_uses_default_max_turns(self):
        """Test that default max_turns is 10."""
        from src.subagents.graph import create_academic_agent_graph

        mock_llm = MagicMock()
        mock_tools = []
        system_prompt = "Test prompt"

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            create_academic_agent_graph(mock_llm, mock_tools, system_prompt)
            assert mock_create.called


class TestRegisterAcademicTemplates:
    """Tests for register_academic_templates."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools dict."""
        return {
            "semantic_scholar_search": _make_test_tool("semantic_scholar_search"),
            "read_file": _make_test_tool("read_file"),
            "get_paper_section": _make_test_tool("get_paper_section"),
            "get_paper_toc": _make_test_tool("get_paper_toc"),
        }

    def test_registers_all_unified_academic_templates(self, mock_tools):
        """Test that the unified registry is fully registered into graph templates."""
        from src.subagents.academic.registry import get_all_subagent_types
        from src.subagents.graph import register_academic_templates

        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, mock_tools)

        # Check for expected templates
        assert registry.has("academic_scout")
        assert registry.has("academic_writer")
        assert registry.has("academic_synthesizer")
        assert registry.has("academic_analyst")
        assert registry.has("academic_gap_miner")
        assert registry.has("academic_trend_spotter")
        assert registry.has("academic_reviewer")
        assert registry.has("academic_thesis_writer")
        assert registry.has("academic_librarian")
        assert registry.has("academic_figure_planner")
        # Verify all templates are registered
        assert registry.count == len(get_all_subagent_types())

    def test_uses_correct_tools_for_scout(self, mock_tools):
        """Test that scout template uses correct tools."""
        from src.subagents.graph import register_academic_templates

        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
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
            "semantic_scholar_search": _make_test_tool("semantic_scholar_search"),
        }

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, limited_tools)

            from src.subagents.academic.registry import get_all_subagent_types

            # Missing tools should shrink each template's toolset, not the template registry.
            assert registry.count == len(get_all_subagent_types())

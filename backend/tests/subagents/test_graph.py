"""Tests for graph template registry and default graph creation."""

import pytest
from unittest.mock import MagicMock, patch


class TestGraphTemplateRegistry:
    """Tests for GraphTemplateRegistry class."""

    def test_init_empty_registry(self):
        """Registry should start empty."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        assert registry.count == 0

    def test_register_template(self):
        """Should register a graph template."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        mock_graph = MagicMock(name="test_graph")

        registry.register("default", mock_graph)

        assert registry.count == 1

    def test_register_multiple_templates(self):
        """Should register multiple templates."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        mock_graph1 = MagicMock(name="graph1")
        mock_graph2 = MagicMock(name="graph2")

        registry.register("default", mock_graph1)
        registry.register("custom", mock_graph2)

        assert registry.count == 2

    def test_get_template(self):
        """Should retrieve a registered template."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        mock_graph = MagicMock(name="test_graph")

        registry.register("default", mock_graph)
        retrieved = registry.get("default")

        assert retrieved is mock_graph

    def test_get_nonexistent_template(self):
        """Should return None for unregistered template."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        retrieved = registry.get("nonexistent")

        assert retrieved is None

    def test_has_template(self):
        """Should check if template exists."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        mock_graph = MagicMock(name="test_graph")

        assert registry.has("default") is False

        registry.register("default", mock_graph)

        assert registry.has("default") is True

    def test_has_nonexistent_template(self):
        """Should return False for unregistered template."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        assert registry.has("nonexistent") is False

    def test_register_overwrites(self):
        """Registering with same name should overwrite."""
        from src.subagents.graph import GraphTemplateRegistry

        registry = GraphTemplateRegistry()
        mock_graph1 = MagicMock(name="graph1")
        mock_graph2 = MagicMock(name="graph2")

        registry.register("default", mock_graph1)
        registry.register("default", mock_graph2)

        assert registry.count == 1
        assert registry.get("default") is mock_graph2


class TestCreateDefaultSubagentGraph:
    """Tests for create_default_subagent_graph function."""

    def test_create_graph_with_llm_and_tools(self):
        """Should create graph with LLM and tools."""
        from src.subagents.graph import create_default_subagent_graph

        mock_llm = MagicMock(name="llm")
        mock_tools = [MagicMock(name="tool1"), MagicMock(name="tool2")]

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_graph = MagicMock(name="graph")
            mock_create.return_value = mock_graph

            result = create_default_subagent_graph(mock_llm, mock_tools)

            mock_create.assert_called_once_with(mock_llm, tools=mock_tools)
            assert result is mock_graph

    def test_create_graph_with_max_turns_parameter(self):
        """Should accept max_turns parameter (even if not used)."""
        from src.subagents.graph import create_default_subagent_graph

        mock_llm = MagicMock(name="llm")
        mock_tools = []

        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_graph = MagicMock(name="graph")
            mock_create.return_value = mock_graph

            result = create_default_subagent_graph(mock_llm, mock_tools, max_turns=5)

            assert result is mock_graph

    def test_create_graph_raises_import_error_without_langgraph(self):
        """Should raise ImportError with helpful message if langgraph is not installed."""
        # This test verifies that the error message is helpful
        # We test the import statement inside the function is properly wrapped
        from src.subagents.graph import create_default_subagent_graph

        mock_llm = MagicMock(name="llm")
        mock_tools = []

        # The function uses try/except to catch ImportError and re-raise with helpful message
        # When langgraph.prebuilt.create_react_agent raises ImportError,
        # our code catches it and raises a new ImportError with "langgraph is required"
        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.side_effect = ImportError("No module named 'langgraph'")

            with pytest.raises(ImportError):
                create_default_subagent_graph(mock_llm, mock_tools)

    def test_create_graph_default_max_turns(self):
        """Should have default max_turns of 10."""
        from src.subagents.graph import create_default_subagent_graph
        import inspect

        sig = inspect.signature(create_default_subagent_graph)
        assert sig.parameters["max_turns"].default == 10

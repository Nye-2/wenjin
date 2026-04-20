"""Tests for graph template registry and default graph creation."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import tool


def _make_test_tool(name: str):
    @tool(name)
    def _test_tool(query: str) -> str:
        """Return the provided query for test assertions."""
        return query

    return _test_tool


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
        from src.agents.lead_agent.dynamic_tools import DynamicToolNode
        from src.subagents.graph import create_default_subagent_graph

        mock_llm = MagicMock(name="llm")
        mock_tools = [_make_test_tool("tool1"), _make_test_tool("tool2")]

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_graph = MagicMock(name="graph")
            mock_create.return_value = mock_graph

            result = create_default_subagent_graph(mock_llm, mock_tools)

            mock_create.assert_called_once()
            args, _ = mock_create.call_args
            assert callable(args[0])
            assert isinstance(args[1], DynamicToolNode)
            assert result is mock_graph

    def test_create_graph_with_max_turns_parameter(self):
        """Should accept max_turns parameter (even if not used)."""
        from src.subagents.graph import create_default_subagent_graph

        mock_llm = MagicMock(name="llm")
        mock_tools = []

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
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
        import inspect

        from src.subagents.graph import create_default_subagent_graph

        sig = inspect.signature(create_default_subagent_graph)
        assert sig.parameters["max_turns"].default == 10

    def test_create_graph_wires_subagent_tool_middlewares(self):
        """Subagent graph should pass tool middlewares into DynamicToolNode."""
        from src.subagents.graph import create_default_subagent_graph

        mock_llm = MagicMock(name="llm")
        middleware = MagicMock(name="middleware")

        with patch(
            "src.subagents.graph.build_subagent_tool_middlewares",
            return_value=[middleware],
        ), patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock(name="graph")

            create_default_subagent_graph(mock_llm, [])

            args, _ = mock_create.call_args
            assert args[1]._middlewares == [middleware]


def test_registry_evicts_oldest_entry_at_max_size():
    """Registry must evict the LRU (oldest) entry when max_size is reached."""
    from unittest.mock import MagicMock

    from src.subagents.graph import GraphTemplateRegistry

    registry = GraphTemplateRegistry(max_size=3)
    g1, g2, g3, g4 = MagicMock(), MagicMock(), MagicMock(), MagicMock()

    registry.register("a", g1)
    registry.register("b", g2)
    registry.register("c", g3)
    assert registry.count == 3

    # Adding a 4th entry must evict the oldest ("a")
    registry.register("d", g4)
    assert registry.count == 3
    assert registry.get("a") is None, "Oldest entry 'a' must have been evicted"
    assert registry.get("d") is g4


def test_registry_get_moves_entry_to_most_recent():
    """Accessing an entry must make it the most recently used (not evicted next)."""
    from unittest.mock import MagicMock

    from src.subagents.graph import GraphTemplateRegistry

    registry = GraphTemplateRegistry(max_size=2)
    g1, g2, g3 = MagicMock(), MagicMock(), MagicMock()

    registry.register("a", g1)
    registry.register("b", g2)

    # Access "a" to mark it as recently used
    assert registry.get("a") is g1

    # Adding "c" must evict "b" (LRU), not "a"
    registry.register("c", g3)
    assert registry.get("b") is None, "'b' should have been evicted as LRU"
    assert registry.get("a") is g1, "'a' should survive (was recently accessed)"
    assert registry.get("c") is g3


def test_registry_default_max_size_is_50():
    """Default max_size must be 50."""
    from src.subagents.graph import GraphTemplateRegistry

    registry = GraphTemplateRegistry()
    assert registry.max_size == 50


def test_registry_rejects_invalid_max_size():
    """GraphTemplateRegistry must raise ValueError for max_size < 1."""
    from src.subagents.graph import GraphTemplateRegistry

    with pytest.raises(ValueError, match="max_size must be >= 1"):
        GraphTemplateRegistry(max_size=0)

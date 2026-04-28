"""Test fixtures for subagent tests."""

from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool

from src.subagents.config import SubagentConfig
from src.subagents.graph import GraphTemplateRegistry


def make_test_tool(name: str):
    @tool(name)
    def _test_tool(query: str) -> str:
        """Return the provided query for test assertions."""
        return query

    return _test_tool


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    return MagicMock()


@pytest.fixture
def mock_tools():
    """Create mock tools."""
    return [make_test_tool("tool1"), make_test_tool("tool2")]


@pytest.fixture
def graph_registry():
    """Create a graph registry."""
    return GraphTemplateRegistry()


@pytest.fixture
def subagent_config(mock_llm, mock_tools):
    """Create subagent configuration."""
    return SubagentConfig(llm=mock_llm, default_tools=mock_tools)

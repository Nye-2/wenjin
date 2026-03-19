"""Test fixtures for subagent tests."""

from unittest.mock import MagicMock

import pytest

from src.subagents.config import SubagentConfig
from src.subagents.events import SubagentEventStream
from src.subagents.graph import GraphTemplateRegistry


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    return MagicMock()


@pytest.fixture
def mock_tools():
    """Create mock tools."""
    return [MagicMock(), MagicMock()]


@pytest.fixture
def event_stream():
    """Create an event stream."""
    return SubagentEventStream()


@pytest.fixture
def graph_registry():
    """Create a graph registry."""
    return GraphTemplateRegistry()


@pytest.fixture
def subagent_config(mock_llm, mock_tools):
    """Create subagent configuration."""
    return SubagentConfig(llm=mock_llm, default_tools=mock_tools)

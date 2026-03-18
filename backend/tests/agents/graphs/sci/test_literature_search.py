"""Tests for SCI literature search sub-graph."""

import pytest

from src.agents.graphs._shared import _read_optional_str
from src.agents.graphs.sci.literature_search import literature_search_graph


class TestReadOptionalStr:
    def test_none_value(self):
        assert _read_optional_str(None) is None

    def test_empty_string(self):
        assert _read_optional_str("") is None

    def test_whitespace_only(self):
        assert _read_optional_str("   ") is None

    def test_valid_string(self):
        assert _read_optional_str("  machine learning  ") == "machine learning"


class TestLiteratureSearchGraph:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic graph execution with minimal payload."""
        initial_state = {
            "messages": [],
            "workspace_id": "test-workspace",
            "workspace_type": "sci",
        }
        payload = {
            "workspace_id": "test-workspace",
            "workspace_name": "Test Workspace",
            "params": {
                "query": "machine learning",
            },
        }

        result = await literature_search_graph(initial_state, payload)

        assert "query" in result
        assert "papers" in result
        assert "search_strategy" in result
        assert result["query"] == "machine learning"

    @pytest.mark.asyncio
    async def test_fallback_to_workspace_name(self):
        """Test that query falls back to workspace name when not provided."""
        initial_state = {
            "messages": [],
            "workspace_id": "test-workspace",
            "workspace_type": "sci",
        }
        payload = {
            "workspace_id": "test-workspace",
            "workspace_name": "Deep Learning Research",
            "params": {},
        }

        result = await literature_search_graph(initial_state, payload)

        assert "query" in result
        assert result["query"] == "Deep Learning Research"

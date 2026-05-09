"""Tests for the WebSearcher v2 subagent."""

import pytest

from src.subagents.v2 import REGISTRY, SubagentContext
from src.subagents.v2.types import WebSearcher  # triggers registration


def _ctx(**inputs):
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs,
        tools=[],
    )


class TestWebSearcher:
    async def test_web_searcher_returns_expected_shape(self):
        """run() returns a dict with 'results' list, each item has required keys."""
        agent = WebSearcher()
        result = await agent.run(_ctx(query="large language models"))

        assert "results" in result.output
        results = result.output["results"]
        assert isinstance(results, list)
        assert len(results) > 0

        for item in results:
            assert "title" in item
            assert "url" in item
            assert "snippet" in item

    async def test_web_searcher_validates_required_input(self):
        """run() without 'query' raises ValueError."""
        agent = WebSearcher()
        with pytest.raises(ValueError, match="query"):
            await agent.run(_ctx())

    def test_web_searcher_registered(self):
        """WebSearcher is registered in REGISTRY."""
        cls = REGISTRY.get("web_searcher")
        assert cls is WebSearcher

    def test_allowed_tools(self):
        """web_searcher declares correct allowed_tools."""
        assert "web_search" in WebSearcher.allowed_tools
        assert "fetch_url" in WebSearcher.allowed_tools

"""Tests for the ScholarSearcher v2 subagent."""

import pytest

from src.subagents.v2 import REGISTRY, SubagentContext
from src.subagents.v2.types import ScholarSearcher  # triggers registration


def _ctx(**inputs):
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs,
        tools=[],
    )


class TestScholarSearcher:
    async def test_scholar_searcher_returns_expected_shape(self):
        """run() returns a dict with 'papers' list, each item has required keys."""
        agent = ScholarSearcher()
        result = await agent.run(_ctx(topic="transformer architectures"))

        assert "papers" in result.output
        papers = result.output["papers"]
        assert isinstance(papers, list)
        assert len(papers) > 0

        for paper in papers:
            assert "title" in paper
            assert "authors" in paper
            assert isinstance(paper["authors"], list)
            assert "year" in paper
            assert "doi" in paper  # may be None

    async def test_scholar_searcher_validates_required_input(self):
        """run() without 'topic' raises ValueError."""
        agent = ScholarSearcher()
        with pytest.raises(ValueError, match="topic"):
            await agent.run(_ctx())

    def test_scholar_searcher_registered(self):
        """ScholarSearcher is registered in REGISTRY."""
        cls = REGISTRY.get("scholar_searcher")
        assert cls is ScholarSearcher

    def test_allowed_tools(self):
        """scholar_searcher declares correct allowed_tools."""
        assert "scholar_search" in ScholarSearcher.allowed_tools
        assert "web_search" in ScholarSearcher.allowed_tools

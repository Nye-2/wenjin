"""Tests for the Clusterer v2 subagent."""

import pytest

from src.subagents.v2 import REGISTRY, SubagentContext
from src.subagents.v2.types import Clusterer  # triggers registration


def _ctx(**inputs):
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs,
        tools=[],
    )


_SAMPLE_PAPERS = [
    {"id": "p1", "title": "Old Paper A", "year": 2018},
    {"id": "p2", "title": "Old Paper B", "year": 2020},
    {"id": "p3", "title": "Recent Paper C", "year": 2023},
    {"id": "p4", "title": "Recent Paper D", "year": 2024},
]


class TestClusterer:
    async def test_clusterer_returns_expected_shape(self):
        """run() returns a dict with 'clusters' list, each item has 'theme' and 'paper_ids'."""
        agent = Clusterer()
        result = await agent.run(_ctx(papers=_SAMPLE_PAPERS))

        assert "clusters" in result.output
        clusters = result.output["clusters"]
        assert isinstance(clusters, list)
        assert len(clusters) > 0

        for cluster in clusters:
            assert "theme" in cluster
            assert "paper_ids" in cluster
            assert isinstance(cluster["paper_ids"], list)

    async def test_clusterer_validates_required_input(self):
        """run() without 'papers' raises ValueError."""
        agent = Clusterer()
        with pytest.raises(ValueError, match="papers"):
            await agent.run(_ctx())

    async def test_clusterer_buckets_by_year(self):
        """Papers before 2022 go to Foundational Works; 2022+ go to Recent Advances."""
        agent = Clusterer()
        result = await agent.run(_ctx(papers=_SAMPLE_PAPERS))

        clusters = result.output["clusters"]
        themes = {c["theme"]: c["paper_ids"] for c in clusters}

        assert "Foundational Works" in themes
        assert "Recent Advances" in themes
        assert "p1" in themes["Foundational Works"]
        assert "p3" in themes["Recent Advances"]

    async def test_clusterer_empty_papers(self):
        """Empty papers list produces a valid (single) cluster."""
        agent = Clusterer()
        result = await agent.run(_ctx(papers=[]))
        clusters = result.output["clusters"]
        assert isinstance(clusters, list)
        assert len(clusters) >= 1

    def test_clusterer_registered(self):
        """Clusterer is registered in REGISTRY."""
        cls = REGISTRY.get("clusterer")
        assert cls is Clusterer

    def test_allowed_tools(self):
        """clusterer has no allowed_tools."""
        assert Clusterer.allowed_tools == []

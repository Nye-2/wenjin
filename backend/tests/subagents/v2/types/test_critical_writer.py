"""Tests for the CriticalWriter v2 subagent."""

import pytest

from src.subagents.v2 import REGISTRY, SubagentContext
from src.subagents.v2.types import CriticalWriter  # triggers registration


def _ctx(**inputs):
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs,
        tools=[],
    )


_SAMPLE_CLUSTERS = [
    {"theme": "Foundational Works", "paper_ids": ["p1", "p2"]},
    {"theme": "Recent Advances", "paper_ids": ["p3"]},
]


class TestCriticalWriter:
    async def test_critical_writer_returns_expected_shape(self):
        """run() returns a dict with 'markdown' string key."""
        agent = CriticalWriter()
        result = await agent.run(_ctx(clusters=_SAMPLE_CLUSTERS))

        assert "markdown" in result.output
        assert isinstance(result.output["markdown"], str)
        assert len(result.output["markdown"]) > 0

    async def test_critical_writer_validates_required_input(self):
        """run() without 'clusters' raises ValueError."""
        agent = CriticalWriter()
        with pytest.raises(ValueError, match="clusters"):
            await agent.run(_ctx())

    async def test_critical_writer_includes_cluster_themes(self):
        """Generated markdown contains each cluster theme as a heading."""
        agent = CriticalWriter()
        result = await agent.run(_ctx(clusters=_SAMPLE_CLUSTERS))

        md = result.output["markdown"]
        assert "Foundational Works" in md
        assert "Recent Advances" in md

    async def test_critical_writer_respects_style(self):
        """Style input is reflected in the generated markdown."""
        agent = CriticalWriter()
        result = await agent.run(_ctx(clusters=_SAMPLE_CLUSTERS, style="narrative"))
        assert "narrative" in result.output["markdown"]

    async def test_critical_writer_empty_clusters(self):
        """Empty clusters list still produces valid markdown output."""
        agent = CriticalWriter()
        result = await agent.run(_ctx(clusters=[]))
        md = result.output["markdown"]
        assert isinstance(md, str)
        assert len(md) > 0

    def test_critical_writer_registered(self):
        """CriticalWriter is registered in REGISTRY."""
        cls = REGISTRY.get("critical_writer")
        assert cls is CriticalWriter

    def test_allowed_tools(self):
        """critical_writer has no allowed_tools."""
        assert CriticalWriter.allowed_tools == []

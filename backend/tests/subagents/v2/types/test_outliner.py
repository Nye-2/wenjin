"""Tests for the Outliner v2 subagent."""

import pytest

from src.subagents.v2 import REGISTRY, SubagentContext
from src.subagents.v2.types import Outliner  # triggers registration


def _ctx(**inputs):
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs,
        tools=[],
    )


class TestOutliner:
    async def test_outliner_returns_expected_shape(self):
        """run() returns a dict with 'outline' list, each item has 'section' and 'subsections'."""
        agent = Outliner()
        result = await agent.run(_ctx(topic="deep learning for NLP"))

        assert "outline" in result.output
        outline = result.output["outline"]
        assert isinstance(outline, list)
        assert len(outline) == 3  # V1 stub always returns 3 sections

        for section in outline:
            assert "section" in section
            assert "subsections" in section
            assert isinstance(section["subsections"], list)
            assert len(section["subsections"]) > 0

    async def test_outliner_validates_required_input(self):
        """run() without 'topic' raises ValueError."""
        agent = Outliner()
        with pytest.raises(ValueError, match="topic"):
            await agent.run(_ctx())

    async def test_outliner_includes_topic_in_sections(self):
        """Topic string appears in at least one section name."""
        agent = Outliner()
        result = await agent.run(_ctx(topic="quantum computing"))

        outline = result.output["outline"]
        section_names = [s["section"] for s in outline]
        assert any("quantum computing" in name for name in section_names)

    def test_outliner_registered(self):
        """Outliner is registered in REGISTRY."""
        cls = REGISTRY.get("outliner")
        assert cls is Outliner

    def test_allowed_tools(self):
        """outliner has no allowed_tools."""
        assert Outliner.allowed_tools == []

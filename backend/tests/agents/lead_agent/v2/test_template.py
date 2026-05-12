"""Tests for the capability template renderer."""

from __future__ import annotations

from src.agents.lead_agent.v2.template import (
    build_task_render_context,
    render_template,
)


class TestPureTemplate:
    def test_resolves_top_level_var(self):
        assert render_template("{{topic}}", {"topic": "diffusion"}) == "diffusion"

    def test_resolves_dotted_path(self):
        ctx = {"phases": {"p1": {"t1": {"output": {"papers": [1, 2]}}}}}
        assert render_template(
            "{{phases.p1.t1.output.papers}}", ctx
        ) == [1, 2]

    def test_preserves_list_type(self):
        ctx = {"items": ["a", "b"]}
        assert render_template("{{items}}", ctx) == ["a", "b"]

    def test_preserves_int_type(self):
        ctx = {"n": 42}
        assert render_template("{{n}}", ctx) == 42

    def test_missing_returns_none(self):
        assert render_template("{{nope}}", {}) is None


class TestDefaultFilter:
    def test_default_int_when_missing(self):
        assert render_template("{{year_min|default(2019)}}", {}) == 2019

    def test_default_string_when_missing(self):
        assert render_template("{{mode|default('full')}}", {}) == "full"

    def test_default_skipped_when_present(self):
        assert render_template(
            "{{year_min|default(2019)}}", {"year_min": 2022}
        ) == 2022

    def test_default_null(self):
        assert render_template("{{x|default(null)}}", {}) is None

    def test_default_bool(self):
        assert render_template("{{x|default(true)}}", {}) is True


class TestInterpolation:
    def test_mixed_string_renders(self):
        assert render_template(
            "search query: {{topic}}", {"topic": "diffusion"}
        ) == "search query: diffusion"

    def test_multiple_placeholders(self):
        assert render_template(
            "{{a}} and {{b}}", {"a": "x", "b": "y"}
        ) == "x and y"

    def test_missing_renders_empty(self):
        assert render_template(
            "before {{nope}} after", {}
        ) == "before  after"


class TestNestedStructures:
    def test_dict_walked_recursively(self):
        template = {"query": "{{topic}}", "limit": "{{n|default(10)}}"}
        ctx = {"topic": "RAG"}
        assert render_template(template, ctx) == {"query": "RAG", "limit": 10}

    def test_list_walked_recursively(self):
        template = ["{{a}}", "{{b}}"]
        assert render_template(template, {"a": 1, "b": 2}) == [1, 2]

    def test_non_string_scalar_passthrough(self):
        assert render_template(42, {}) == 42
        assert render_template(None, {}) is None
        assert render_template(True, {}) is True


class TestBuildContext:
    def test_brief_at_top_level(self):
        ctx = build_task_render_context(
            brief={"topic": "x"}, node_results={}, phase_index={}
        )
        assert ctx["topic"] == "x"

    def test_phase_index_populates_phases_namespace(self):
        ctx = build_task_render_context(
            brief={"topic": "x"},
            node_results={
                "search": {"output": {"papers": ["p1"]}},
            },
            phase_index={"discover": ["search"]},
        )
        assert ctx["phases"]["discover"]["search"]["output"]["papers"] == ["p1"]

    def test_unfinished_task_absent_from_phases(self):
        ctx = build_task_render_context(
            brief={}, node_results={}, phase_index={"discover": ["search"]}
        )
        assert "search" not in ctx["phases"]["discover"]


class TestEndToEndCapabilityShape:
    """A representative literature_search-style inputs block."""

    def test_searcher_inputs_resolve(self):
        template = {
            "query": "{{topic}}",
            "year_min": "{{year_min|default(2019)}}",
        }
        ctx = build_task_render_context(
            brief={"topic": "diffusion medical imaging"},
            node_results={},
            phase_index={"discover": ["search"]},
        )
        assert render_template(template, ctx) == {
            "query": "diffusion medical imaging",
            "year_min": 2019,
        }

    def test_react_inputs_pull_upstream_papers(self):
        template = {
            "topic": "{{topic}}",
            "papers": "{{phases.discover.search.output.papers}}",
        }
        ctx = build_task_render_context(
            brief={"topic": "diffusion"},
            node_results={
                "search": {
                    "output": {
                        "papers": [
                            {"title": "Paper A"},
                            {"title": "Paper B"},
                        ]
                    }
                }
            },
            phase_index={"discover": ["search"], "synthesize": ["review"]},
        )
        rendered = render_template(template, ctx)
        assert rendered["topic"] == "diffusion"
        assert rendered["papers"] == [{"title": "Paper A"}, {"title": "Paper B"}]


# ---------------------------------------------------------------------------
# Integration: full compile_graph → run → templated inputs reach subagents
# ---------------------------------------------------------------------------

import pytest
from typing import TypedDict
from src.agents.lead_agent.v2.compiler import compile_graph
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY


class _CaptureState(TypedDict, total=False):
    node_results: dict
    workspace_id: str
    execution_id: str
    inputs_for_tasks: dict
    workspace_data: dict


@pytest.mark.asyncio
async def test_compile_graph_renders_inputs_at_run_time(monkeypatch):
    """End-to-end: a 2-phase template with {{topic}} + {{phases.A.B.output.X}}
    must reach each subagent with rendered values, not the raw brief.
    """

    captured: dict[str, dict] = {}

    class _CaptureSearcher(SubagentBase):
        name = "_capture_searcher"

        async def run(self, ctx: SubagentContext) -> SubagentResult:
            captured["search"] = dict(ctx.inputs)
            return SubagentResult(output={"papers": [{"title": "A"}, {"title": "B"}]})

    class _CaptureReact(SubagentBase):
        name = "_capture_react"

        async def run(self, ctx: SubagentContext) -> SubagentResult:
            captured["review"] = dict(ctx.inputs)
            return SubagentResult(output={"markdown": "ok"})

    REGISTRY.register(_CaptureSearcher.name, _CaptureSearcher)
    REGISTRY.register(_CaptureReact.name, _CaptureReact)
    try:
        template = {
            "phases": [
                {
                    "name": "discover",
                    "tasks": [
                        {
                            "name": "search",
                            "subagent_type": _CaptureSearcher.name,
                            "inputs": {
                                "query": "{{topic}}",
                                "year_min": "{{year_min|default(2019)}}",
                            },
                        }
                    ],
                },
                {
                    "name": "synthesize",
                    "depends_on": ["discover"],
                    "tasks": [
                        {
                            "name": "review",
                            "subagent_type": _CaptureReact.name,
                            "inputs": {
                                "topic": "{{topic}}",
                                "papers": "{{phases.discover.search.output.papers}}",
                            },
                        }
                    ],
                },
            ]
        }

        graph = compile_graph(template, state_class=_CaptureState)
        await graph.ainvoke(
            {
                "node_results": {},
                "inputs_for_tasks": {
                    "search": {"topic": "RAG", "year_min": 2022},
                    "review": {"topic": "RAG"},
                },
            }
        )
    finally:
        REGISTRY._d.pop(_CaptureSearcher.name, None)  # type: ignore[attr-defined]
        REGISTRY._d.pop(_CaptureReact.name, None)  # type: ignore[attr-defined]

    # Searcher saw rendered query and year_min (not raw {topic, year_min} from brief)
    assert captured["search"]["query"] == "RAG"
    assert captured["search"]["year_min"] == 2022

    # React saw upstream papers via {{phases.discover.search.output.papers}}
    assert captured["review"]["topic"] == "RAG"
    assert captured["review"]["papers"] == [{"title": "A"}, {"title": "B"}]

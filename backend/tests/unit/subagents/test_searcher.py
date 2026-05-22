"""Unit tests for SearcherSubagent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.search.base import SearchResult
from src.subagents.v2.base import SubagentContext
from src.subagents.v2.registry import REGISTRY
from src.subagents.v2.types.searcher import (
    SearcherSubagent,
    _deduplicate,
    _normalize_search_query,
    _normalize_title,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(*, inputs: dict | None = None, skill=None) -> SubagentContext:
    """Build a minimal SubagentContext for testing."""
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt="",
        inputs=inputs or {},
        tools=[],
        workspace_data={},
        skill=skill,
    )


def _make_skill(sources: list[str] | None = None, *, config: dict | None = None) -> MagicMock:
    """Build a mock CapabilitySkill with the given source config."""
    skill = MagicMock()
    skill.config = config if config is not None else {"sources": sources or []}
    skill.prompt = ""
    skill.resources = []
    skill.allowed_tools = []
    return skill


def _paper(title: str, doi: str | None = None, **kw) -> SearchResult:
    """Shorthand to build a SearchResult."""
    return SearchResult(title=title, doi=doi, source="test", **kw)


# ---------------------------------------------------------------------------
# Test: _normalize_title
# ---------------------------------------------------------------------------

class TestNormalizeTitle:
    def test_lowercase_and_strip(self):
        assert _normalize_title("Hello World!") == "helloworld"

    def test_punctuation_removed(self):
        assert _normalize_title("A, B; C. D") == "abcd"

    def test_already_clean(self):
        assert _normalize_title("abc123") == "abc123"


class TestNormalizeSearchQuery:
    def test_extracts_topic_from_bilingual_task_request(self):
        query = _normalize_search_query(
            "再次执行文献定位与创新点。主题：federated fine-tuning of large "
            "language models with LoRA/adapter, communication-efficient federated "
            "instruction tuning。请输出 gap matrix。"
        )

        assert query == (
            "federated fine-tuning of large language models with LoRA adapter "
            "communication-efficient federated instruction tuning"
        )

    def test_keeps_plain_english_query(self):
        assert _normalize_search_query("federated learning LoRA") == "federated learning LoRA"


# ---------------------------------------------------------------------------
# Test: SearcherSubagent registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_registered_in_global_registry(self):
        assert "searcher" in REGISTRY.all_names()
        assert REGISTRY.get("searcher") is SearcherSubagent


# ---------------------------------------------------------------------------
# Test: run() -- no skill => empty papers
# ---------------------------------------------------------------------------

class TestNoSkill:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_skill(self):
        sub = SearcherSubagent()
        ctx = _make_ctx(skill=None)
        result = await sub.run(ctx)
        assert result.output == {"papers": []}


class TestMissingSources:
    @pytest.mark.asyncio
    async def test_raises_when_no_search_sources_configured(self):
        sub = SearcherSubagent()
        ctx = _make_ctx(inputs={"query": "test query"}, skill=_make_skill(sources=[]))

        with pytest.raises(ValueError, match="without configured search sources"):
            await sub.run(ctx)


# ---------------------------------------------------------------------------
# Test: run() -- single mock source
# ---------------------------------------------------------------------------

class TestSingleSource:
    @pytest.mark.asyncio
    async def test_calls_source_and_returns_papers(self):
        papers = [
            _paper("Paper A", doi="10.1/a"),
            _paper("Paper B", doi="10.1/b"),
        ]

        mock_source = AsyncMock()
        mock_source.search.return_value = papers

        with patch(
            "src.subagents.v2.types.searcher.get_search_source",
            return_value=mock_source,
        ):
            sub = SearcherSubagent()
            skill = _make_skill(sources=["mock_src"])
            ctx = _make_ctx(inputs={"query": "主题：test query。请输出报告"}, skill=skill)
            result = await sub.run(ctx)

        mock_source.search.assert_awaited_once_with(
            "test query", year_range=None, limit=30,
        )
        assert len(result.output["papers"]) == 2
        assert result.output["papers"][0]["title"] == "Paper A"
        assert result.output["papers"][1]["title"] == "Paper B"

    @pytest.mark.asyncio
    async def test_keeps_results_when_one_source_fails(self):
        failing_source = AsyncMock()
        failing_source.search.side_effect = RuntimeError("rate limited")
        working_source = AsyncMock()
        working_source.search.return_value = [_paper("Curated Paper")]

        def get_source(name: str):
            return failing_source if name == "semantic_scholar" else working_source

        with patch(
            "src.subagents.v2.types.searcher.get_search_source",
            side_effect=get_source,
        ):
            sub = SearcherSubagent()
            skill = _make_skill(sources=["semantic_scholar", "curated_academic"])
            ctx = _make_ctx(inputs={"query": "federated LoRA"}, skill=skill)
            result = await sub.run(ctx)

        assert result.output["papers"][0]["title"] == "Curated Paper"

    @pytest.mark.asyncio
    async def test_reads_search_config_from_skill_extensions(self):
        papers = [_paper("Paper A", doi="10.1/a")]

        mock_source = AsyncMock()
        mock_source.search.return_value = papers

        with patch(
            "src.subagents.v2.types.searcher.get_search_source",
            return_value=mock_source,
        ):
            sub = SearcherSubagent()
            skill = _make_skill(
                config={
                    "extensions": {
                        "search": {
                            "sources": ["mock_src"],
                            "max_results": 5,
                        }
                    }
                }
            )
            ctx = _make_ctx(inputs={"query": "test query"}, skill=skill)
            result = await sub.run(ctx)

        mock_source.search.assert_awaited_once_with(
            "test query", year_range=None, limit=5,
        )
        assert result.output["papers"][0]["title"] == "Paper A"


# ---------------------------------------------------------------------------
# Test: run() -- dedup by DOI
# ---------------------------------------------------------------------------

class TestDedupByDOI:
    @pytest.mark.asyncio
    async def test_deduplicates_papers_with_same_doi(self):
        papers = [
            _paper("Paper A from source 1", doi="10.1/a"),
            _paper("Paper A from source 2", doi="10.1/A"),  # same DOI, different case
            _paper("Paper B", doi="10.1/b"),
        ]

        mock_source = AsyncMock()
        mock_source.search.return_value = papers

        with patch(
            "src.subagents.v2.types.searcher.get_search_source",
            return_value=mock_source,
        ):
            sub = SearcherSubagent()
            skill = _make_skill(sources=["mock_src"])
            ctx = _make_ctx(inputs={"query": "dedup test"}, skill=skill)
            result = await sub.run(ctx)

        # DOI 10.1/a appears twice; should keep only first
        assert len(result.output["papers"]) == 2
        assert result.output["papers"][0]["title"] == "Paper A from source 1"
        assert result.output["papers"][1]["title"] == "Paper B"


# ---------------------------------------------------------------------------
# Test: _deduplicate unit-level
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_dedup_by_doi(self):
        results = [
            _paper("Title A", doi="10.1/a"),
            _paper("Title A alt", doi="10.1/A"),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 1

    def test_dedup_by_title_when_no_doi(self):
        results = [
            _paper("Same Title!", doi=None),
            _paper("same title", doi=None),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 1

    def test_different_papers_kept(self):
        results = [
            _paper("Paper One", doi="10.1/a"),
            _paper("Paper Two", doi="10.1/b"),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 2

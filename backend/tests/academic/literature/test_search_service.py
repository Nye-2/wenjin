"""Tests for the literature search service."""

from __future__ import annotations

import pytest

from src.academic.literature.search_service import LiteratureSearchService
from src.services.search.base import SearchResult


class _FakeSearchSource:
    def __init__(
        self,
        name: str,
        results: list[SearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.results = results or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, *, year_range=None, limit: int = 10):
        self.calls.append({"query": query, "year_range": year_range, "limit": limit})
        if self.error is not None:
            raise self.error
        return self.results


@pytest.mark.asyncio
async def test_literature_search_service_returns_verified_multi_source_papers() -> None:
    source = _FakeSearchSource(
        "semantic_scholar",
        [
            SearchResult(
                title="Paper A",
                authors=["Alice"],
                year=2024,
                doi="https://doi.org/10.1000/A",
                url="https://example.com/a",
                abstract="Abstract A",
                external_id="ss-a",
                source="semantic_scholar",
                citations=12,
                venue="ACL",
            )
        ],
    )
    service = LiteratureSearchService(sources=[source])

    result = await service.search(query="  LLM planning  ", discipline="计算机科学", limit=30)

    assert source.calls == [{"query": "LLM planning", "year_range": None, "limit": 20}]
    assert result["source"] == "literature_search"
    assert result["retrieval"]["status"] == "ok"
    assert result["retrieval"]["verified"] == 1
    assert result["retrieval"]["sources"][0]["source"] == "semantic_scholar"
    paper = result["verified_papers"][0]
    assert paper["title"] == "Paper A"
    assert paper["doi"] == "10.1000/a"
    assert paper["external_id"] == "ss-a"
    assert paper["source"] == "semantic_scholar"
    assert paper["evidence_level"] == "semantic_scholar_metadata"
    assert paper["retrieval_query"] == "LLM planning"


@pytest.mark.asyncio
async def test_literature_search_service_dedupes_by_doi() -> None:
    source = _FakeSearchSource(
        "semantic_scholar",
        [
            SearchResult(title="Paper A", doi="10.1000/a", external_id="ss-a", source="semantic_scholar"),
            SearchResult(title="Paper A Duplicate", doi="10.1000/A", external_id="ss-b", source="semantic_scholar"),
        ],
    )
    service = LiteratureSearchService(sources=[source])

    result = await service.search(query="agent planning")

    assert result["retrieval"]["returned"] == 2
    assert result["retrieval"]["verified"] == 1
    assert [paper["external_id"] for paper in result["verified_papers"]] == ["ss-a"]


@pytest.mark.asyncio
async def test_literature_search_service_keeps_web_results_when_semantic_scholar_fails() -> None:
    service = LiteratureSearchService(
        sources=[
            _FakeSearchSource("semantic_scholar", error=RuntimeError("api unavailable")),
            _FakeSearchSource(
                "web_search",
                [
                    SearchResult(
                        title="OpenAI | Research & Deployment",
                        url="https://openai.com/",
                        abstract="Creating safe and beneficial AI.",
                        external_id="https://openai.com/",
                        source="web_search",
                        raw={"evidence_level": "web_search_result_snippet"},
                    )
                ],
            ),
        ]
    )

    result = await service.search(query="agent planning")

    assert result["retrieval"]["status"] == "partial"
    assert result["retrieval"]["source_errors"] == [
        {"source": "semantic_scholar", "error": "api unavailable"}
    ]
    assert result["retrieval"]["verified"] == 1
    paper = result["verified_papers"][0]
    assert paper["title"] == "OpenAI | Research & Deployment"
    assert paper["source"] == "web_search"
    assert paper["evidence_level"] == "web_search_result_snippet"


@pytest.mark.asyncio
async def test_literature_search_service_reports_total_source_failure_without_fake_papers() -> None:
    service = LiteratureSearchService(
        sources=[_FakeSearchSource("semantic_scholar", error=RuntimeError("api unavailable"))]
    )

    result = await service.search(query="agent planning")

    assert result["retrieval"]["status"] == "failed"
    assert result["retrieval"]["source_errors"] == [
        {"source": "semantic_scholar", "error": "api unavailable"}
    ]
    assert result["verified_papers"] == []

"""Tests for the Semantic Scholar literature search service."""

from __future__ import annotations

import pytest

from src.academic.literature.external.base import PaperSearchResult
from src.academic.literature.search_service import LiteratureSearchService


class _FakeSemanticScholarClient:
    def __init__(self, results: list[PaperSearchResult] | None = None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        self.calls.append({"query": query, "limit": limit})
        if self.error is not None:
            raise self.error
        return self.results


@pytest.mark.asyncio
async def test_literature_search_service_returns_verified_semantic_scholar_papers() -> None:
    client = _FakeSemanticScholarClient(
        [
            PaperSearchResult(
                title="Paper A",
                authors=["Alice"],
                year=2024,
                doi="https://doi.org/10.1000/A",
                url="https://example.com/a",
                abstract="Abstract A",
                external_id="ss-a",
                source="semantic_scholar",
                citations_count=12,
                venue="ACL",
            )
        ]
    )
    service = LiteratureSearchService(client=client)  # type: ignore[arg-type]

    result = await service.search(query="  LLM planning  ", discipline="计算机科学", limit=30)

    assert client.calls == [{"query": "LLM planning", "limit": 20}]
    assert result["source"] == "semantic_scholar"
    assert result["retrieval"]["status"] == "ok"
    assert result["retrieval"]["verified"] == 1
    paper = result["verified_papers"][0]
    assert paper["title"] == "Paper A"
    assert paper["doi"] == "10.1000/a"
    assert paper["external_id"] == "ss-a"
    assert paper["evidence_level"] == "semantic_scholar_metadata"
    assert paper["retrieval_query"] == "LLM planning"


@pytest.mark.asyncio
async def test_literature_search_service_dedupes_by_doi() -> None:
    client = _FakeSemanticScholarClient(
        [
            PaperSearchResult(title="Paper A", doi="10.1000/a", external_id="ss-a", source="semantic_scholar"),
            PaperSearchResult(title="Paper A Duplicate", doi="10.1000/A", external_id="ss-b", source="semantic_scholar"),
        ]
    )
    service = LiteratureSearchService(client=client)  # type: ignore[arg-type]

    result = await service.search(query="agent planning")

    assert result["retrieval"]["returned"] == 2
    assert result["retrieval"]["verified"] == 1
    assert [paper["external_id"] for paper in result["verified_papers"]] == ["ss-a"]


@pytest.mark.asyncio
async def test_literature_search_service_reports_source_failure_without_fake_papers() -> None:
    service = LiteratureSearchService(
        client=_FakeSemanticScholarClient(error=RuntimeError("api unavailable"))  # type: ignore[arg-type]
    )

    result = await service.search(query="agent planning")

    assert result["retrieval"]["status"] == "failed"
    assert result["retrieval"]["error"] == "api unavailable"
    assert result["verified_papers"] == []

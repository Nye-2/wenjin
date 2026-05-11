"""Semantic Scholar search source -- wraps the existing client."""

from __future__ import annotations

from typing import Any

from src.academic.literature.external.semantic_scholar import SemanticScholarClient
from src.services.search.base import SearchResult
from src.services.search.registry import register_search_source


class SemanticScholarSource:
    """Search source backed by SemanticScholarClient."""

    name: str = "semantic_scholar"

    def __init__(self) -> None:
        self._client = SemanticScholarClient()

    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]:
        paper_results = await self._client.search(query, limit=limit)

        results: list[SearchResult] = []
        for pr in paper_results:
            # Apply year-range filter if provided
            if year_range is not None and pr.year is not None:
                if not (year_range[0] <= pr.year <= year_range[1]):
                    continue

            results.append(
                SearchResult(
                    title=pr.title,
                    authors=list(pr.authors),
                    year=pr.year,
                    abstract=pr.abstract or None,
                    doi=pr.doi,
                    url=pr.url,
                    citations=pr.citations_count,
                    venue=pr.venue,
                    external_id=pr.external_id or "",
                    source="semantic_scholar",
                    raw=pr.model_dump(),
                )
            )
        return results


# Auto-register on import
register_search_source(SemanticScholarSource.name, SemanticScholarSource)  # type: ignore[arg-type]

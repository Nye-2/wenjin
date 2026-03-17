# src/academic/literature/external/crossref.py
"""Crossref API client."""

import logging

from src.integration.http_client import ServiceHttpClient

from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)
API_BASE = "https://api.crossref.org"

_http = ServiceHttpClient(
    service_name="crossref",
    timeout=30.0,
    headers={"User-Agent": "AcademiaGPT/2.0 (mailto:contact@example.com)"},
)


class CrossrefClient(ExternalDBBase):
    """Client for Crossref DOI API."""

    @property
    def name(self) -> str:
        return "crossref"

    @property
    def display_name(self) -> str:
        return "Crossref"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search Crossref for papers."""
        response = await _http.get(
            f"{API_BASE}/works",
            params={"query": query, "rows": limit},
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("message", {}).get("items", []):
            results.append(
                PaperSearchResult(
                    title=item.get("title", [""])[0] if item.get("title") else "",
                    authors=self._normalize_authors(item.get("author", [])),
                    year=item.get("published-print", {}).get("date-parts", [[None]])[0][0],
                    doi=item.get("DOI"),
                    url=item.get("URL"),
                    abstract=item.get("abstract", ""),
                    source="crossref",
                    citations_count=item.get("is-referenced-by-count"),
                    venue=item.get("container-title", [""])[0] if item.get("container-title") else None,
                )
            )
        return results

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI."""
        response = await _http.get(f"{API_BASE}/works/{doi}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json().get("message", {})

        return PaperSearchResult(
            title=item.get("title", [""])[0] if item.get("title") else "",
            authors=self._normalize_authors(item.get("author", [])),
            year=item.get("published-print", {}).get("date-parts", [[None]])[0][0],
            doi=item.get("DOI"),
            url=item.get("URL"),
            abstract=item.get("abstract", ""),
            source="crossref",
            citations_count=item.get("is-referenced-by-count"),
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Crossref references lookup (not citations)."""
        logger.warning("Crossref does not support direct citations lookup")
        return []

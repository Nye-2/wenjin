# src/academic/literature/external/semantic_scholar.py
"""Semantic Scholar API client."""

import logging

from src.integration.http_client import ServiceHttpClient

from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)

# Semantic Scholar API base URL
API_BASE = "https://api.semanticscholar.org/graph/v1"

_http = ServiceHttpClient(service_name="semantic_scholar", timeout=30.0)


class SemanticScholarClient(ExternalDBBase):
    """Client for Semantic Scholar API."""

    @property
    def name(self) -> str:
        return "semantic_scholar"

    @property
    def display_name(self) -> str:
        return "Semantic Scholar"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search Semantic Scholar for papers.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        response = await _http.get(
            f"{API_BASE}/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "paperId,title,authors,year,doi,url,abstract,citationCount,venue",
            },
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("data", []):
            results.append(
                PaperSearchResult(
                    title=item.get("title", ""),
                    authors=self._normalize_authors(item.get("authors", [])),
                    year=item.get("year"),
                    doi=item.get("doi"),
                    url=item.get("url"),
                    abstract=item.get("abstract", ""),
                    external_id=item.get("paperId"),
                    source="semantic_scholar",
                    citations_count=item.get("citationCount"),
                    venue=item.get("venue"),
                )
            )

        return results

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI.

        Args:
            doi: Paper DOI

        Returns:
            Paper if found, None otherwise
        """
        response = await _http.get(
            f"{API_BASE}/paper/DOI:{doi}",
            params={
                "fields": "paperId,title,authors,year,doi,url,abstract,citationCount,venue",
            },
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json()

        return PaperSearchResult(
            title=item.get("title", ""),
            authors=self._normalize_authors(item.get("authors", [])),
            year=item.get("year"),
            doi=item.get("doi"),
            url=item.get("url"),
            abstract=item.get("abstract", ""),
            external_id=item.get("paperId"),
            source="semantic_scholar",
            citations_count=item.get("citationCount"),
            venue=item.get("venue"),
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Get papers that cite this paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum citations

        Returns:
            List of citing papers
        """
        response = await _http.get(
            f"{API_BASE}/paper/{paper_id}/citations",
            params={
                "limit": limit,
                "fields": "paperId,title,authors,year,doi,url,abstract",
            },
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("data", []):
            citing_paper = item.get("citingPaper", {})
            results.append(
                PaperSearchResult(  # type: ignore[call-arg]
                    title=citing_paper.get("title", ""),
                    authors=self._normalize_authors(citing_paper.get("authors", [])),
                    year=citing_paper.get("year"),
                    doi=citing_paper.get("doi"),
                    url=citing_paper.get("url"),
                    abstract=citing_paper.get("abstract", ""),
                    external_id=citing_paper.get("paperId"),
                    source="semantic_scholar",
                )
            )

        return results

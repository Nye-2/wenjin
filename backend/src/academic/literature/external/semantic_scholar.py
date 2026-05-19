# src/academic/literature/external/semantic_scholar.py
"""Semantic Scholar API client."""

import asyncio
import logging
import time

from src.config.app_config import get_settings
from src.integration.http_client import ServiceHttpClient

from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)

# Semantic Scholar API base URL
API_BASE = "https://api.semanticscholar.org/graph/v1"

_http = ServiceHttpClient(service_name="semantic_scholar", timeout=30.0)
_rate_limit_lock = asyncio.Lock()
_next_request_at = 0.0
_PAPER_FIELDS = "paperId,title,authors,year,externalIds,url,abstract,citationCount,venue"
_CITATION_FIELDS = "paperId,title,authors,year,externalIds,url,abstract"


def _request_headers() -> dict[str, str]:
    settings = get_settings()
    api_key = str(settings.semantic_scholar_api_key or "").strip()
    if not api_key:
        return {}
    return {"x-api-key": api_key}


async def _wait_for_rate_limit() -> None:
    global _next_request_at

    delay = float(get_settings().semantic_scholar_rate_limit_delay or 0.0)
    if delay <= 0:
        return

    async with _rate_limit_lock:
        now = time.monotonic()
        if _next_request_at > now:
            await asyncio.sleep(_next_request_at - now)
            now = _next_request_at
        _next_request_at = now + delay


def _extract_doi(item: dict[str, object]) -> str | None:
    external_ids = item.get("externalIds")
    if not isinstance(external_ids, dict):
        return None
    doi = external_ids.get("DOI")
    return str(doi).strip() or None if doi is not None else None


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
        await _wait_for_rate_limit()
        response = await _http.get(
            f"{API_BASE}/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": _PAPER_FIELDS,
            },
            headers=_request_headers(),
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
                    doi=_extract_doi(item),
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
        await _wait_for_rate_limit()
        response = await _http.get(
            f"{API_BASE}/paper/DOI:{doi}",
            params={
                "fields": _PAPER_FIELDS,
            },
            headers=_request_headers(),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json()

        return PaperSearchResult(
            title=item.get("title", ""),
            authors=self._normalize_authors(item.get("authors", [])),
            year=item.get("year"),
            doi=_extract_doi(item),
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
        await _wait_for_rate_limit()
        response = await _http.get(
            f"{API_BASE}/paper/{paper_id}/citations",
            params={
                "limit": limit,
                "fields": _CITATION_FIELDS,
            },
            headers=_request_headers(),
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
                    doi=_extract_doi(citing_paper),
                    url=citing_paper.get("url"),
                    abstract=citing_paper.get("abstract", ""),
                    external_id=citing_paper.get("paperId"),
                    source="semantic_scholar",
                )
            )

        return results

# src/academic/literature/external/openalex.py
"""OpenAlex API client."""

import logging
import httpx
from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)
API_BASE = "https://api.openalex.org"


class OpenAlexClient(ExternalDBBase):
    """Client for OpenAlex API."""

    @property
    def name(self) -> str:
        return "openalex"

    @property
    def display_name(self) -> str:
        return "OpenAlex"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search OpenAlex for papers."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works",
                params={"search": query, "per_page": limit},
                headers={"mailto": "contact@example.com"},
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("results", []):
            results.append(
                PaperSearchResult(
                    title=item.get("title", ""),
                    authors=[a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
                    year=item.get("publication_year"),
                    doi=item.get("doi"),
                    url=item.get("id"),
                    abstract=item.get("abstract", ""),
                    source="openalex",
                    citations_count=item.get("cited_by_count"),
                    venue=item.get("primary_location", {}).get("source", {}).get("display_name"),
                )
            )
        return results

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works/doi:{doi}",
                headers={"mailto": "contact@example.com"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            item = response.json()

        return PaperSearchResult(
            title=item.get("title", ""),
            authors=[a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
            year=item.get("publication_year"),
            doi=item.get("doi"),
            url=item.get("id"),
            abstract=item.get("abstract", ""),
            source="openalex",
            citations_count=item.get("cited_by_count"),
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Get papers that cite this work."""
        logger.warning("OpenAlex citations lookup requires pagination")
        return []

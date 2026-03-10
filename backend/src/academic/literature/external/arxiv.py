# src/academic/literature/external/arxiv.py
"""arXiv API client."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)

# arXiv API base URL
API_BASE = "http://export.arxiv.org/api/query"


class ArxivClient(ExternalDBBase):
    """Client for arXiv API."""

    @property
    def name(self) -> str:
        return "arxiv"

    @property
    def display_name(self) -> str:
        return "arXiv"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search arXiv for papers.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                API_BASE,
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": limit,
                },
            )
            response.raise_for_status()

        return self._parse_arxiv_response(response.text)

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI (arXiv ID).

        Args:
            doi: arXiv DOI or ID

        Returns:
            Paper if found, None otherwise
        """
        # Extract arXiv ID from DOI if present
        arxiv_id = doi
        if "arXiv" in doi:
            arxiv_id = doi.split("arXiv.")[-1]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                API_BASE,
                params={
                    "id_list": arxiv_id,
                    "max_results": 1,
                },
            )
            response.raise_for_status()

        results = self._parse_arxiv_response(response.text)
        return results[0] if results else None

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """arXiv does not support citations lookup.

        Args:
            paper_id: arXiv paper ID
            limit: Ignored

        Returns:
            Empty list (not supported by arXiv API)
        """
        logger.warning("arXiv does not support citations lookup")
        return []

    def _parse_arxiv_response(self, xml_text: str) -> list[PaperSearchResult]:
        """Parse arXiv XML response.

        Args:
            xml_text: XML response from arXiv API

        Returns:
            List of PaperSearchResult
        """
        results = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                published = entry.find("atom:published", ns)
                link = entry.find("atom:id", ns)

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns)
                    if name is not None and name.text:
                        authors.append(name.text)

                year = None
                if published is not None and published.text:
                    year = int(published.text[:4])

                results.append(
                    PaperSearchResult(
                        title=title.text if title is not None else "",
                        authors=authors,
                        year=year,
                        doi=None,
                        url=link.text if link is not None else None,
                        abstract=summary.text if summary is not None else "",
                        source="arxiv",
                    )
                )
        except ET.ParseError as e:
            logger.error(f"Failed to parse arXiv response: {e}")

        return results

"""ArXiv search tool for academic paper discovery."""

import logging
from typing import Any

import arxiv

logger = logging.getLogger(__name__)


class ArxivTool:
    """Tool for searching academic papers on ArXiv."""

    name = "arxiv_search"
    description = "Search for academic papers on ArXiv by query. Returns paper metadata including title, authors, abstract, URL, DOI, and year."

    def __init__(self) -> None:
        """Initialize the ArXiv tool."""
        self._client = arxiv.Client()

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search for papers on ArXiv.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of paper dictionaries with title, authors, abstract, url, doi, year.
            Returns empty list on error.
        """
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            results = []
            for paper in self._client.results(search):
                paper_dict = {
                    "title": paper.title,
                    "authors": [author.name for author in paper.authors],
                    "abstract": paper.summary.replace("\n", " ").strip(),
                    "url": paper.pdf_url or paper.entry_id,
                    "doi": paper.doi,
                    "year": paper.published.year if paper.published else None,
                    "arxiv_id": paper.entry_id.split("/")[-1] if paper.entry_id else None,
                    "categories": [cat for cat in paper.categories] if paper.categories else [],
                }
                results.append(paper_dict)

            return results
        except Exception as e:
            logger.error(f"ArXiv search error: {e}")
            return []

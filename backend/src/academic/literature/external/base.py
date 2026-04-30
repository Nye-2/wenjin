# src/academic/literature/external/base.py
"""Base class for external academic databases."""

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperSearchResult(BaseModel):
    """Unified search result from external databases."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Attention Is All You Need",
                "authors": ["Ashish Vaswani", "et al."],
                "year": 2017,
                "doi": "10.48550/arXiv.1706.03762",
                "url": "https://www.semanticscholar.org/paper/example",
                "abstract": "The dominant sequence transduction models...",
                "source": "semantic_scholar",
                "citations_count": 50000,
                "venue": "NeurIPS 2017",
            }
        }
    )

    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    year: int | None = Field(None, description="Publication year")
    doi: str | None = Field(None, description="Digital Object Identifier")
    url: str | None = Field(None, description="Paper URL")
    abstract: str = Field(default="", description="Paper abstract")
    external_id: str | None = Field(None, description="Source-native paper identifier")
    source: Literal["semantic_scholar"] = Field(
        ..., description="Source database"
    )
    citations_count: int | None = Field(None, description="Number of citations")
    venue: str | None = Field(None, description="Publication venue")


class ExternalDBBase(ABC):
    """Abstract base class for external academic databases."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Database name identifier."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable database name."""
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search for papers.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of PaperSearchResult objects
        """
        pass

    @abstractmethod
    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            PaperSearchResult if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Get papers that cite this paper.

        Args:
            paper_id: Provider-native paper identifier
            limit: Maximum number of citations to return

        Returns:
            List of citing papers
        """
        pass

    def _normalize_authors(self, authors: Any) -> list[str]:
        """Normalize author list to list of strings.

        Args:
            authors: Author data (various formats)

        Returns:
            List of author name strings
        """
        if not authors:
            return []
        if isinstance(authors, list):
            return [
                str(a) if isinstance(a, str) else a.get("name", str(a))
                for a in authors
            ]
        return [str(authors)]

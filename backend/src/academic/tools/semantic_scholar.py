"""Semantic Scholar search tool for academic paper discovery."""

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.config import settings


class SemanticScholarInput(BaseModel):
    """Input for Semantic Scholar search."""
    query: str = Field(description="Search query for academic papers")
    limit: int = Field(default=10, description="Maximum number of results")
    year_range: Optional[str] = Field(default=None, description="Year range, e.g., '2020-2024'")


@tool(args_schema=SemanticScholarInput)
async def semantic_scholar_search_tool(
    query: str,
    limit: int = 10,
    year_range: Optional[str] = None,
) -> str:
    """Search for academic papers using Semantic Scholar.

    Use this tool to find relevant academic papers on a topic.
    Returns paper titles, authors, year, venue, and abstract.

    Args:
        query: Search query
        limit: Maximum results (default 10)
        year_range: Optional year range filter

    Returns:
        Formatted search results with paper details
    """
    try:
        # Import Semantic Scholar client
        from semanticscholar import SemanticScholar

        client = SemanticScholar(api_key=settings.semantic_scholar_api_key)

        # Build search parameters
        search_params = {
            "query": query,
            "limit": limit,
        }

        if year_range:
            search_params["year"] = year_range

        # Perform search
        results = client.search_paper(**search_params)

        if not results:
            return f"No papers found for query: '{query}'"

        # Format results
        formatted = [f"Found {len(results)} papers for '{query}':\n"]

        for i, paper in enumerate(results, 1):
            # Extract authors
            authors = []
            if paper.authors:
                authors = [a.get("name", "Unknown") for a in paper.authors[:3]]
                if len(paper.authors) > 3:
                    authors.append("et al.")
            authors_str = ", ".join(authors) if authors else "Unknown Authors"

            # Format paper info
            formatted.append(f"\n[{i}] {paper.title}")
            formatted.append(f"    Authors: {authors_str}")
            if paper.year:
                formatted.append(f"    Year: {paper.year}")
            if paper.venue:
                formatted.append(f"    Venue: {paper.venue}")
            if paper.citationCount is not None:
                formatted.append(f"    Citations: {paper.citationCount}")
            if paper.abstract:
                abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                formatted.append(f"    Abstract: {abstract}")
            if paper.url:
                formatted.append(f"    URL: {paper.url}")
            if paper.externalIds and "DOI" in paper.externalIds:
                formatted.append(f"    DOI: {paper.externalIds['DOI']}")

        return "\n".join(formatted)

    except ImportError:
        return "Error: semanticscholar package not installed. Run: uv add semanticscholar"
    except Exception as e:
        return f"Error searching Semantic Scholar: {str(e)}"

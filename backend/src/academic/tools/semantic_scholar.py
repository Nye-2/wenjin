"""Semantic Scholar search tool for academic paper discovery."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.academic.literature.external.semantic_scholar import SemanticScholarClient

_MAX_QUERY_CHARS = 240


class SemanticScholarInput(BaseModel):
    """Input for Semantic Scholar search."""
    query: str = Field(description="Search query for academic papers")
    limit: int = Field(default=10, description="Maximum number of results")
    year_range: str | None = Field(default=None, description="Year range, e.g., '2020-2024'")


@tool(args_schema=SemanticScholarInput)
async def semantic_scholar_search_tool(
    query: str,
    limit: int = 10,
    year_range: str | None = None,
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
    normalized_query = " ".join(str(query or "").split()).strip()
    if not normalized_query:
        return "Error searching Semantic Scholar: query is empty"

    # Long free-form prompts degrade the API badly; keep the search query focused.
    if len(normalized_query) > _MAX_QUERY_CHARS:
        normalized_query = normalized_query[:_MAX_QUERY_CHARS].rstrip()

    if year_range:
        normalized_query = f"{normalized_query} {year_range}"

    try:
        client = SemanticScholarClient()
        results = await client.search(normalized_query, limit=max(1, min(limit, 10)))

        if not results:
            return f"No papers found for query: '{normalized_query}'"

        formatted = [f"Found {len(results)} papers for '{normalized_query}':\n"]

        for i, paper in enumerate(results, 1):
            authors = paper.authors[:3]
            authors_str = ", ".join(authors) if authors else "Unknown Authors"
            if len(paper.authors) > 3:
                authors_str += ", et al."

            formatted.append(f"\n[{i}] {paper.title}")
            formatted.append(f"    Authors: {authors_str}")
            if paper.year:
                formatted.append(f"    Year: {paper.year}")
            if paper.venue:
                formatted.append(f"    Venue: {paper.venue}")
            if paper.citations_count is not None:
                formatted.append(f"    Citations: {paper.citations_count}")
            if paper.abstract:
                abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                formatted.append(f"    Abstract: {abstract}")
            if paper.url:
                formatted.append(f"    URL: {paper.url}")
            if paper.doi:
                formatted.append(f"    DOI: {paper.doi}")

        return "\n".join(formatted)
    except Exception as exc:
        return f"Error searching Semantic Scholar: {exc}"

"""Literature navigation tools for index-based paper exploration.

This module provides LangChain tools for navigating academic literature
using table of contents (TOC) and section-level retrieval. This is an
index-based approach that does not rely on vector embeddings.

Tools:
    - get_paper_toc: Get table of contents for a paper
    - get_paper_section: Get content of a specific section
    - search_papers_by_metadata: Search papers by title/author
"""

from typing import Optional, List

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, PaperSection, WorkspacePaper


# Input Schemas
class GetPaperTocInput(BaseModel):
    """Input schema for get_paper_toc tool."""

    paper_id: str = Field(description="UUID of the paper to get TOC for")


class GetPaperSectionInput(BaseModel):
    """Input schema for get_paper_section tool."""

    paper_id: str = Field(description="UUID of the paper")
    section_path: str = Field(
        description="Section path identifier (e.g., '1', '2.1', '3.2.1')"
    )


class SearchPapersInput(BaseModel):
    """Input schema for search_papers_by_metadata tool."""

    query: str = Field(description="Search query for title or author")
    workspace_id: Optional[str] = Field(
        default=None, description="Optional workspace ID to limit search scope"
    )


# Formatting helper functions (exposed for testing)
def format_toc_output(paper: Paper) -> str:
    """Format a paper's TOC for display.

    Args:
        paper: Paper object with toc field

    Returns:
        Formatted TOC string
    """
    if not paper.toc or len(paper.toc) == 0:
        return f"No table of contents available for '{paper.title}'."

    lines = [f"## Table of Contents: {paper.title}"]
    if paper.year:
        lines[0] += f" ({paper.year})"
    lines.append("")

    for item in paper.toc:
        number = item.get("number", "")
        title = item.get("title", "")
        level = item.get("level", 1)

        # Indent based on level
        indent = "  " * (level - 1)
        lines.append(f"{indent}{number}. {title}")

    return "\n".join(lines)


def format_section_output(section: PaperSection) -> str:
    """Format a paper section for display.

    Args:
        section: PaperSection object

    Returns:
        Formatted section string
    """
    lines = [
        f"## {section.section_title}",
        f"**Section:** {section.section_path}",
        f"**Pages:** {section.page_start}-{section.page_end}",
        "",
        section.content,
    ]

    return "\n".join(lines)


def format_search_results(
    papers: List[Paper],
    query: str,
    workspace_id: Optional[str],
) -> str:
    """Format search results for display.

    Args:
        papers: List of Paper objects
        query: Original search query
        workspace_id: Optional workspace ID that was searched

    Returns:
        Formatted search results string
    """
    if not papers:
        scope = f" in workspace '{workspace_id}'" if workspace_id else ""
        return f"No papers found matching '{query}'{scope}."

    lines = [f"## Search Results: {len(papers)} paper(s) found", ""]

    for idx, paper in enumerate(papers, 1):
        year_str = f" ({paper.year})" if paper.year else ""
        authors_str = ", ".join(paper.author_names[:3])
        if len(paper.author_names) > 3:
            authors_str += " et al."

        lines.append(f"### [{idx}] {paper.title}{year_str}")
        if authors_str:
            lines.append(f"**Authors:** {authors_str}")
        if paper.venue:
            lines.append(f"**Venue:** {paper.venue}")
        lines.append(f"**ID:** {paper.id}")
        lines.append("")

    return "\n".join(lines)


# Helper functions for database access
async def _get_paper_by_id(db: AsyncSession, paper_id: str) -> Optional[Paper]:
    """Retrieve a paper by ID.

    Args:
        db: Database session
        paper_id: Paper UUID

    Returns:
        Paper object or None if not found
    """
    query = select(Paper).where(Paper.id == paper_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _get_section_by_path(
    db: AsyncSession,
    paper_id: str,
    section_path: str,
    workspace_id: Optional[str] = None,
) -> Optional[PaperSection]:
    """Retrieve a paper section by path.

    Args:
        db: Database session
        paper_id: Paper UUID
        section_path: Section path (e.g., "3.2.1")
        workspace_id: Optional workspace ID for filtering

    Returns:
        PaperSection object or None if not found
    """
    query = select(PaperSection).where(
        PaperSection.paper_id == paper_id,
        PaperSection.section_path == section_path,
    )
    if workspace_id:
        query = query.where(PaperSection.workspace_id == workspace_id)

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _search_papers_in_db(
    db: AsyncSession,
    query: str,
    workspace_id: Optional[str] = None,
) -> list[Paper]:
    """Search papers by title or author.

    Args:
        db: Database session
        query: Search query string
        workspace_id: Optional workspace ID to limit search

    Returns:
        List of matching Paper objects
    """
    # Build search condition for title (case-insensitive)
    search_pattern = f"%{query}%"

    if workspace_id:
        # Search within workspace
        db_query = (
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == workspace_id)
            .where(Paper.title.ilike(search_pattern))
            .order_by(Paper.year.desc().nulls_last())
            .limit(20)
        )
    else:
        # Global search
        db_query = (
            select(Paper)
            .where(Paper.title.ilike(search_pattern))
            .order_by(Paper.year.desc().nulls_last())
            .limit(20)
        )

    result = await db.execute(db_query)
    return list(result.scalars().all())


# Tool implementations
# Note: These tools require database session injection.
# In production, use dependency injection or context variables.


@tool(args_schema=GetPaperTocInput)
async def get_paper_toc(paper_id: str) -> str:
    """Get the table of contents for a specific paper.

    Use this tool to understand the structure of a paper and identify
    relevant sections to read. Returns a formatted list of all sections
    with their section numbers and titles.

    Args:
        paper_id: UUID of the paper

    Returns:
        Formatted table of contents string, or error message if not found
    """
    # Import here to avoid circular imports and allow for session injection
    from src.academic.database.session import get_db_session

    async with get_db_session() as db:
        paper = await _get_paper_by_id(db, paper_id)

        if not paper:
            return f"Paper with ID '{paper_id}' not found."

        return format_toc_output(paper)


@tool(args_schema=GetPaperSectionInput)
async def get_paper_section(paper_id: str, section_path: str) -> str:
    """Get the full content of a specific section from a paper.

    Use this tool after identifying relevant sections via get_paper_toc.
    Returns the complete text content of the specified section.

    Args:
        paper_id: UUID of the paper
        section_path: Section identifier (e.g., '1', '2.1', '3.2.1')

    Returns:
        Section content with title, or error message if not found
    """
    from src.academic.database.session import get_db_session

    async with get_db_session() as db:
        # First verify paper exists
        paper = await _get_paper_by_id(db, paper_id)
        if not paper:
            return f"Paper with ID '{paper_id}' not found."

        # Get the section
        section = await _get_section_by_path(db, paper_id, section_path)

        if not section:
            return f"Section '{section_path}' not found in '{paper.title}'."

        return format_section_output(section)


@tool(args_schema=SearchPapersInput)
async def search_papers_by_metadata(
    query: str,
    workspace_id: Optional[str] = None,
) -> str:
    """Search for papers by title.

    Use this tool to find papers in the database by searching their titles.
    Optionally limit the search to a specific workspace.

    Args:
        query: Search query (searches paper titles)
        workspace_id: Optional workspace UUID to limit search scope

    Returns:
        Formatted list of matching papers with metadata
    """
    from src.academic.database.session import get_db_session

    async with get_db_session() as db:
        papers = await _search_papers_in_db(db, query, workspace_id)
        return format_search_results(papers, query, workspace_id)


# Export tools for agent registration
LITERATURE_TOOLS = [
    get_paper_toc,
    get_paper_section,
    search_papers_by_metadata,
]

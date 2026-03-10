# src/academic/literature/tools.py
"""LLM tools for literature management."""

import logging
from typing import Literal

from langchain_core.tools import tool, InjectedToolArg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, WorkspacePaper, Workspace, WorkspaceType
from src.academic.services.workspace_service import WorkspaceService
from src.academic.services.paper_service import PaperService
from .navigation.models import PaperTOC
from .navigation.toc_service import TocService
from .navigation.section_loader import SectionLoader
from .external import (
    SemanticScholarClient,
    ArxivClient,
    CrossrefClient,
    OpenAlexClient,
    PaperSearchResult,
)

logger = logging.getLogger(__name__)


@tool
async def list_papers(
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> list[dict]:
    """List all papers in a workspace with their TOC.

    Args:
        workspace_id: Workspace ID

    Returns:
        List of papers with their table of contents
    """
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
    )
    papers = result.scalars().all()

    toc_service = TocService(db)
    paper_list = []

    for paper in papers:
        toc = await toc_service.get_paper_toc(paper.id)
        paper_list.append({
            "paper_id": str(paper.id),
            "title": paper.title,
            "toc": [
                {"title": e.title, "level": e.level}
                for e in (toc.entries if toc else [])
            ],
        })

    return paper_list


@tool
async def get_section(
    paper_id: str,
    section_title: str,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Get content of a specific paper section.

    Args:
        paper_id: Paper ID
        section_title: Section title (e.g., "3. Methodology")

    Returns:
        Section content in markdown format
    """
    toc_service = TocService(db)
    section_loader = SectionLoader(db)

    toc = await toc_service.get_paper_toc(paper_id)
    if not toc:
        return f"Paper {paper_id} not found"

    if section_title.lower() == "abstract":
        content = await section_loader.get_abstract(toc)
        return content.content if content else "Abstract not available"

    content = await section_loader.load_section(toc, section_title)
    if not content:
        return f"Section '{section_title}' not found. Available sections: {[e.title for e in toc.entries]}"

    return content.content


@tool
async def search_external(
    query: str,
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex", "all"] = "all",
    limit: int = 10,
) -> list[dict]:
    """Search external academic databases.

    Args:
        query: Search keywords
        source: Database to search (default: all)
        limit: Maximum results per source

    Returns:
        List of matching papers
    """
    clients = {
        "semantic_scholar": SemanticScholarClient(),
        "arxiv": ArxivClient(),
        "crossref": CrossrefClient(),
        "openalex": OpenAlexClient(),
    }

    results = []

    if source == "all":
        # Search all sources
        for name, client in clients.items():
            try:
                found = await client.search(query, limit=min(5, limit))
                results.extend([r.model_dump() for r in found])
            except Exception as e:
                logger.warning(f"{name} search failed: {e}")
    else:
        client = clients.get(source)
        if client:
            try:
                found = await client.search(query, limit=limit)
                results = [r.model_dump() for r in found]
            except Exception as e:
                logger.error(f"{source} search failed: {e}")

    return results


@tool
async def get_paper_by_doi(doi: str) -> dict | None:
    """Get paper metadata by DOI.

    Args:
        doi: Paper DOI

    Returns:
        Paper metadata or None if not found
    """
    clients = [
        SemanticScholarClient(),
        CrossrefClient(),
        OpenAlexClient(),
    ]

    for client in clients:
        try:
            result = await client.get_by_doi(doi)
            if result:
                return result.model_dump()
        except Exception as e:
            logger.debug(f"{client.__class__.__name__} DOI lookup failed: {e}")

    return None


@tool
async def create_workspace(
    name: str,
    type: str,
    db: AsyncSession = InjectedToolArg,
    discipline: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a new workspace.

    Args:
        name: Workspace name
        type: Workspace type (sci, thesis, proposal, grant, literature_review)
        discipline: Academic discipline (optional, e.g., computer_science)
        description: Workspace description (optional)

    Returns:
        Created workspace info with id, name, type
    """
    # Default user_id for now (should be injected from context in production)
    user_id = "default-user"

    service = WorkspaceService(db)
    try:
        workspace = await service.create(
            user_id=user_id,
            name=name,
            type=type,
            discipline=discipline,
            description=description,
        )
        return {
            "id": str(workspace.id),
            "name": workspace.name,
            "type": workspace.type.value,
            "discipline": workspace.discipline,
            "description": workspace.description,
        }
    except ValueError as e:
        return {"error": str(e)}


@tool
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> dict | None:
    """Get workspace details.

    Args:
        workspace_id: Workspace ID

    Returns:
        Workspace info including paper count, or None if not found
    """
    from sqlalchemy import func, select

    service = WorkspaceService(db)
    workspace = await service.get(workspace_id)

    if not workspace:
        return None

    # Count papers in workspace
    result = await db.execute(
        select(func.count()).where(WorkspacePaper.workspace_id == workspace_id)
    )
    paper_count = result.scalar() or 0

    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "type": workspace.type.value,
        "discipline": workspace.discipline,
        "description": workspace.description,
        "paper_count": paper_count,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
    }


@tool
async def add_paper_to_workspace(
    paper_id: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Add an existing paper to workspace.

    Args:
        paper_id: Paper ID
        workspace_id: Target workspace ID
        notes: User notes (optional)
        tags: Tags for categorization (optional)

    Returns:
        Status message
    """
    service = PaperService(db)

    # Check if paper exists
    paper = await service.get(paper_id)
    if not paper:
        return f"Error: Paper {paper_id} not found"

    # Add to workspace
    try:
        await service.add_to_workspace(
            paper_id=paper_id,
            workspace_id=workspace_id,
            notes=notes,
            tags=tags,
        )
        return f"Successfully added '{paper.title}' to workspace"
    except Exception as e:
        return f"Error: {str(e)}"

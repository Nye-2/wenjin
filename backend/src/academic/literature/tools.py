# src/academic/literature/tools.py
"""LLM tools for literature management."""

import logging
from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.database import Paper, PaperExtraction, PaperSection, WorkspacePaper

from .external import (
    ArxivClient,
    CrossrefClient,
    ExternalDBBase,
    OpenAlexClient,
    SemanticScholarClient,
)
from .navigation.section_loader import SectionLoader
from .navigation.toc_service import TocService

logger = logging.getLogger(__name__)

InjectedSession = Annotated[AsyncSession, InjectedToolArg]
JsonObject = dict[str, Any]


def _coerce_section_summaries(value: object) -> dict[str, str]:
    """Normalize extracted section summaries to a string-keyed mapping."""
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _build_import_client(
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex"],
) -> ExternalDBBase:
    """Construct the external literature client for the selected source."""
    if source == "semantic_scholar":
        return SemanticScholarClient()
    if source == "arxiv":
        return ArxivClient()
    if source == "crossref":
        return CrossrefClient()
    return OpenAlexClient()


def _serialize_import_author(author: object) -> dict[str, str | None]:
    """Convert external author payloads to PaperService author dictionaries."""
    if isinstance(author, str):
        return {"name": author, "affiliation": None}

    name = getattr(author, "name", None)
    affiliation = getattr(author, "affiliation", None)
    return {
        "name": str(name) if name else str(author),
        "affiliation": str(affiliation) if affiliation is not None else None,
    }


@tool
async def list_papers(
    workspace_id: str,
    db: InjectedSession,
) -> list[JsonObject]:
    """List all papers in a workspace with enriched TOC.

    Args:
        workspace_id: Workspace ID

    Returns:
        List of papers with their table of contents including
        word_count, page_range, and summary per section
    """
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
    )
    papers = result.scalars().all()

    toc_service = TocService(db)
    paper_list: list[JsonObject] = []

    for paper in papers:
        toc = await toc_service.get_paper_toc(paper.id)

        # Try to get Tier 2 section summaries
        section_summaries: dict[str, str] = {}
        tier2_result = await db.execute(
            select(PaperExtraction.structured_data)
            .where(PaperExtraction.paper_id == str(paper.id))
            .where(PaperExtraction.tier == 2)
            .order_by(PaperExtraction.created_at.desc())
            .limit(1)
        )
        tier2_data = tier2_result.scalar_one_or_none()
        if isinstance(tier2_data, dict):
            section_summaries = _coerce_section_summaries(
                tier2_data.get("section_summaries")
            )

        enriched_toc: list[JsonObject] = []
        if toc:
            for entry in toc.entries:
                word_count = (entry.char_end - entry.char_start) // 5
                toc_item = {
                    "title": entry.title,
                    "level": entry.level,
                    "word_count": word_count,
                    "page_range": (
                        f"{entry.page_start or '?'}-?"
                        if entry.page_start
                        else None
                    ),
                    "summary": section_summaries.get(entry.title, ""),
                }
                enriched_toc.append(toc_item)

        paper_list.append({
            "paper_id": str(paper.id),
            "title": paper.title,
            "toc": enriched_toc,
        })

    return paper_list


@tool
async def get_section(
    paper_id: str,
    section_title: str,
    db: InjectedSession,
) -> str:
    """Get content of a specific paper section.

    Args:
        paper_id: Paper ID
        section_title: Section title (e.g., "3. Methodology") or section path (e.g., "3.2.1")

    Returns:
        Section content in markdown format
    """
    toc_service = TocService(db)
    section_loader = SectionLoader(db)

    toc = await toc_service.get_paper_toc(paper_id)
    if not toc:
        return f"Paper {paper_id} not found"

    if section_title.lower() == "abstract":
        abstract_content = await section_loader.get_abstract(toc)
        return abstract_content.content

    # Section path lookup (e.g., "3.2.1") uses exact TOC entry loading.
    if section_title.replace(".", "").isdigit():
        entry = toc.find_entry_by_path(section_title)
        if not entry:
            available = [e.title for e in toc.entries]
            return f"Section '{section_title}' not found. Available sections: {available}"

        entry_content = await section_loader.load_section_by_entry(toc, entry)
        if not entry_content:
            return f"Content not available for section '{section_title}'"
        return entry_content.content

    # Title lookup uses the section loader's built-in fuzzy logic.
    matched_content = await section_loader.load_section(toc, section_title)
    if matched_content:
        return matched_content.content

    # Distinguish "missing section" from "section exists but content missing".
    if toc.find_entry(section_title) is None:
        available = [e.title for e in toc.entries]
        return f"Section '{section_title}' not found. Available sections: {available}"
    return f"Content not available for section '{section_title}'"


@tool
async def search_external(
    query: str,
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex", "all"] = "all",
    limit: int = 10,
) -> list[JsonObject]:
    """Search external academic databases.

    Args:
        query: Search keywords
        source: Database to search (default: all)
        limit: Maximum results per source

    Returns:
        List of matching papers
    """
    clients: dict[str, ExternalDBBase] = {
        "semantic_scholar": SemanticScholarClient(),
        "arxiv": ArxivClient(),
        "crossref": CrossrefClient(),
        "openalex": OpenAlexClient(),
    }

    results: list[JsonObject] = []

    if source == "all":
        # Search all sources
        for name, source_client in clients.items():
            try:
                found = await source_client.search(query, limit=min(5, limit))
                results.extend([r.model_dump() for r in found])
            except Exception as e:
                logger.warning(f"{name} search failed: {e}")
    else:
        selected_client = clients.get(source)
        if selected_client is not None:
            try:
                found = await selected_client.search(query, limit=limit)
                results = [r.model_dump() for r in found]
            except Exception as e:
                logger.error(f"{source} search failed: {e}")

    return results


@tool
async def get_paper_by_doi(doi: str) -> JsonObject | None:
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
    db: InjectedSession,
    discipline: str | None = None,
    description: str | None = None,
) -> JsonObject:
    """Create a new workspace.

    Args:
        name: Workspace name
        type: Workspace type (sci, thesis, proposal, software_copyright, patent)
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
    db: InjectedSession,
) -> JsonObject | None:
    """Get workspace details.

    Args:
        workspace_id: Workspace ID

    Returns:
        Workspace info including paper count, or None if not found
    """
    from sqlalchemy import func

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
async def list_workspaces(
    db: InjectedSession,
    user_id: str | None = None,
) -> list[JsonObject]:
    """List all workspaces for current user.

    Args:
        user_id: User ID (optional, uses default if not provided)

    Returns:
        List of workspaces with id, name, type, paper_count
    """
    from sqlalchemy import func

    # Default user_id for now
    target_user_id = user_id or "default-user"

    service = WorkspaceService(db)
    workspaces = await service.list_by_user(target_user_id)

    result: list[JsonObject] = []
    for ws in workspaces:
        # Count papers for each workspace
        count_result = await db.execute(
            select(func.count()).where(WorkspacePaper.workspace_id == str(ws.id))
        )
        paper_count = count_result.scalar() or 0

        result.append({
            "id": str(ws.id),
            "name": ws.name,
            "type": ws.type.value,
            "discipline": ws.discipline,
            "paper_count": paper_count,
        })

    return result


@tool
async def add_paper_to_workspace(
    paper_id: str,
    workspace_id: str,
    db: InjectedSession,
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


@tool
async def remove_paper_from_workspace(
    paper_id: str,
    workspace_id: str,
    db: InjectedSession,
) -> str:
    """Remove paper from workspace.

    Args:
        paper_id: Paper ID
        workspace_id: Workspace ID

    Returns:
        Status message
    """
    service = PaperService(db)

    # Remove from workspace
    removed = await service.remove_from_workspace(
        paper_id=paper_id,
        workspace_id=workspace_id,
    )

    if removed:
        return f"Successfully removed paper {paper_id} from workspace"
    else:
        return f"Error: Paper {paper_id} not found in workspace"


@tool
async def import_paper(
    query: str,
    workspace_id: str,
    db: InjectedSession,
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex"] = "semantic_scholar",
) -> str:
    """Search external database and import paper to workspace.

    Args:
        query: Search query (title, DOI, or keywords)
        workspace_id: Target workspace ID
        source: External database to search (default: semantic_scholar)

    Returns:
        Import status with paper info
    """
    client = _build_import_client(source)

    # Search for paper
    try:
        results = await client.search(query, limit=1)
        if not results:
            return f"No papers found for query: {query}"

        paper_data = results[0]
    except Exception as e:
        return f"Error searching {source}: {str(e)}"

    # Create paper record
    paper_service = PaperService(db)

    try:
        paper = await paper_service.create(
            title=paper_data.title,
            authors=[_serialize_import_author(author) for author in paper_data.authors],
            doi=paper_data.doi,
            year=paper_data.year,
            venue=paper_data.venue,
            abstract=paper_data.abstract,
            source=source,
            source_url=paper_data.url,
        )

        # Add to workspace
        await paper_service.add_to_workspace(
            paper_id=str(paper.id),
            workspace_id=workspace_id,
        )

        return f"Successfully imported: {paper.title} (from {source})"
    except Exception as e:
        return f"Error importing paper: {str(e)}"


@tool
async def search_workspace(
    query: str,
    workspace_id: str,
    db: InjectedSession,
    limit: int = 10,
) -> list[JsonObject]:
    """Search section content across all papers in a workspace.

    Uses PostgreSQL full-text search to find relevant sections.
    Supports Chinese + English mixed search.

    Args:
        query: Search keywords
        workspace_id: Workspace ID to search within
        limit: Maximum results (default 10)

    Returns:
        List of matching sections with paper title, section title, snippet, and relevance score
    """
    from sqlalchemy import func
    from sqlalchemy import text as sa_text

    # Build tsquery from the search query
    # Use 'simple' config for Chinese+English mixed support
    # Split query into words and join with & for AND matching
    words = query.strip().split()
    if not words:
        return []

    ts_query_str = " & ".join(words)

    # Query using PostgreSQL full-text search
    stmt = (
        select(
            PaperSection.paper_id,
            PaperSection.section_title,
            PaperSection.section_path,
            PaperSection.content,
            func.ts_rank(
                func.to_tsvector(sa_text("'simple'"), PaperSection.content),
                func.to_tsquery(sa_text("'simple'"), ts_query_str),
            ).label("relevance"),
        )
        .where(PaperSection.workspace_id == workspace_id)
        .where(
            func.to_tsvector(sa_text("'simple'"), PaperSection.content).match(
                ts_query_str, postgresql_regconfig="simple"
            )
        )
        .order_by(sa_text("relevance DESC"))
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Get paper titles for the results
    paper_ids = list({row.paper_id for row in rows})
    paper_titles: dict[str, str] = {}
    if paper_ids:
        papers_result = await db.execute(
            select(Paper.id, Paper.title).where(Paper.id.in_(paper_ids))
        )
        paper_titles = {str(r.id): r.title for r in papers_result.all()}

    # Build response with snippets
    results: list[JsonObject] = []
    for row in rows:
        # Create a snippet (first 300 chars of content)
        content = row.content or ""
        snippet = content[:300] + "..." if len(content) > 300 else content

        results.append({
            "paper_id": row.paper_id,
            "paper_title": paper_titles.get(row.paper_id, "Unknown"),
            "section_title": row.section_title,
            "section_path": row.section_path,
            "snippet": snippet,
            "relevance_score": float(row.relevance) if row.relevance else 0.0,
        })

    return results

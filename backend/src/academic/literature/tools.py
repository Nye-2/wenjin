# src/academic/literature/tools.py
"""LLM tools for literature management."""

import logging
from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, PaperExtraction, WorkspacePaper

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

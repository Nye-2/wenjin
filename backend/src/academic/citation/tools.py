"""LLM tools for citation management."""

import logging
from typing import Literal

from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.paper_service import PaperService
from src.database import Paper, WorkspacePaper

from .bibtex import BibTeXExporter, BibTeXParser
from .formatters import APAFormatter, ChicagoFormatter, IEEEFormatter, MLAFormatter
from .service import CitationService

logger = logging.getLogger(__name__)

# Formatter registry
FORMATTERS = {
    "apa": APAFormatter,
    "mla": MLAFormatter,
    "chicago": ChicagoFormatter,
    "ieee": IEEEFormatter,
}


def _paper_to_dict(paper: Paper) -> dict:
    """Convert Paper model to dict for formatter."""
    return {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "abstract": paper.abstract,
    }


@tool
async def format_citation(
    paper_id: str,
    style: Literal["apa", "mla", "chicago", "ieee"] = "apa",
    in_text: bool = False,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Format a paper citation in specified style.

    Args:
        paper_id: Paper ID to format
        style: Citation style (apa, mla, chicago, ieee)
        in_text: Return in-text citation format if True

    Returns:
        Formatted citation string
    """
    result = await db.execute(
        select(Paper).where(Paper.id == paper_id)
    )
    paper = result.scalar_one_or_none()

    if not paper:
        return f"Paper {paper_id} not found"

    formatter = FORMATTERS.get(style, APAFormatter)()
    return formatter.format_citation(_paper_to_dict(paper), in_text=in_text)


@tool
async def format_bibliography(
    workspace_id: str,
    style: Literal["apa", "mla", "chicago", "ieee"] = "apa",
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Format bibliography for all papers in workspace.

    Args:
        workspace_id: Workspace ID
        style: Citation style (apa, mla, chicago, ieee)

    Returns:
        Formatted bibliography as markdown string
    """
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
        .order_by(Paper.title)
    )
    papers = result.scalars().all()

    if not papers:
        return "No papers in workspace"

    formatter = FORMATTERS.get(style, APAFormatter)()
    entries = []

    for i, paper in enumerate(papers, 1):
        entry = formatter.format_bibliography_entry(_paper_to_dict(paper))
        entries.append(f"{i}. {entry}")

    return "\n\n".join(entries)


@tool
async def export_bibtex(
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Export workspace papers as BibTeX.

    Args:
        workspace_id: Workspace ID

    Returns:
        BibTeX formatted string
    """
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
        .order_by(Paper.title)
    )
    papers = result.scalars().all()

    if not papers:
        return "% No papers in workspace"

    exporter = BibTeXExporter()
    paper_dicts = [_paper_to_dict(p) for p in papers]
    return exporter.export(paper_dicts)


@tool
async def import_bibtex(
    bibtex_content: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Import papers from BibTeX content.

    Args:
        bibtex_content: BibTeX formatted content
        workspace_id: Target workspace ID

    Returns:
        Import status with count of imported papers
    """
    parser = BibTeXParser()
    entries = parser.parse(bibtex_content)

    if not entries:
        return "No valid BibTeX entries found"

    paper_service = PaperService(db)
    imported = 0
    errors = []

    for entry in entries:
        try:
            paper_dict = parser.to_paper_dict(entry)
            paper = await paper_service.create(**paper_dict)
            await paper_service.add_to_workspace(
                paper_id=str(paper.id),
                workspace_id=workspace_id,
            )
            imported += 1
        except Exception as e:
            logger.warning(f"Failed to import entry {entry.get('key')}: {e}")
            errors.append(entry.get("key", "unknown"))

    message = f"Successfully imported {imported} paper(s)"
    if errors:
        message += f". Failed to import: {', '.join(errors)}"

    return message


@tool
async def get_citation_graph(
    paper_id: str,
    depth: int = 1,
    db: AsyncSession = InjectedToolArg,
) -> dict:
    """Get citation graph for a paper.

    Args:
        paper_id: Paper ID to analyze
        depth: How many levels of citations to include (currently only depth=1 supported)

    Returns:
        Citation graph with nodes and edges
    """
    # Get workspace_id from paper's workspace association
    result = await db.execute(
        select(WorkspacePaper.workspace_id)
        .where(WorkspacePaper.paper_id == paper_id)
        .limit(1)
    )
    row = result.first()

    if not row:
        return {"nodes": [], "edges": [], "error": "Paper not found in any workspace"}

    workspace_id = row[0]

    service = CitationService(db)
    # Note: Currently only depth=1 is supported. Full recursive implementation
    # would require CTE or multiple queries.
    outgoing = await service.get_outgoing_citations(paper_id, workspace_id)
    incoming = await service.get_incoming_citations(paper_id, workspace_id)

    # Use set to deduplicate node IDs
    node_ids = {paper_id}
    edges = []

    for citation in outgoing:
        node_ids.add(str(citation.cited_paper_id))
        edges.append({
            "source": paper_id,
            "target": str(citation.cited_paper_id),
            "type": citation.citation_type,
        })

    for citation in incoming:
        node_ids.add(str(citation.paper_id))
        edges.append({
            "source": str(citation.paper_id),
            "target": paper_id,
            "type": citation.citation_type,
        })

    # Convert set to list of node dicts
    nodes = [{"id": nid} for nid in node_ids]

    return {"nodes": nodes, "edges": edges}


@tool
async def add_citation(
    paper_id: str,
    cited_paper_id: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
    citation_context: str | None = None,
    section: str | None = None,
) -> str:
    """Add citation relationship between papers.

    Args:
        paper_id: Source paper (the one that cites)
        cited_paper_id: Target paper (the one being cited)
        workspace_id: Workspace context
        citation_context: Text surrounding the citation (optional)
        section: Section where citation appears (optional)

    Returns:
        Status message
    """
    # Verify both papers exist
    for pid in [paper_id, cited_paper_id]:
        result = await db.execute(select(Paper.id).where(Paper.id == pid))
        if not result.first():
            return f"Paper {pid} not found"

    service = CitationService(db)
    await service.add_citation(
        paper_id=paper_id,
        cited_paper_id=cited_paper_id,
        workspace_id=workspace_id,
        citation_context=citation_context,
        section=section,
    )

    return f"Successfully added citation from {paper_id} to {cited_paper_id}"

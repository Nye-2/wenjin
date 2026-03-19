"""Citation management module.

This module provides citation management functionality including:
- Multi-format citation formatting (APA, MLA, Chicago, IEEE)
- BibTeX import/export
- Citation relationship storage and querying
- LLM tools for citation management

Example usage:

    from src.academic.citation import APAFormatter, CitationService

    # Format a citation
    formatter = APAFormatter()
    citation = formatter.format_citation(paper_dict)

    # Add citation relationship
    service = CitationService(db)
    await service.add_citation(paper_id, cited_paper_id, workspace_id)
"""

from .bibtex import BibTeXExporter, BibTeXParser
from .formatters import (
    APAFormatter,
    ChicagoFormatter,
    CitationFormatter,
    IEEEFormatter,
    MLAFormatter,
)
from .service import CitationService
from .tools import (
    add_citation,
    export_bibtex,
    format_bibliography,
    format_citation,
    get_citation_graph,
    import_bibtex,
)

__all__ = [
    # Service
    "CitationService",
    # Formatters
    "CitationFormatter",
    "APAFormatter",
    "MLAFormatter",
    "ChicagoFormatter",
    "IEEEFormatter",
    # BibTeX
    "BibTeXParser",
    "BibTeXExporter",
    # Tools
    "format_citation",
    "format_bibliography",
    "export_bibtex",
    "import_bibtex",
    "get_citation_graph",
    "add_citation",
]

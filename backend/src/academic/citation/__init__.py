"""Citation management module."""

from .service import CitationService
from .formatters import (
    CitationFormatter,
    APAFormatter,
    MLAFormatter,
    ChicagoFormatter,
    IEEEFormatter,
)
from .bibtex import BibTeXParser, BibTeXExporter
from .tools import (
    format_citation,
    format_bibliography,
    export_bibtex,
    import_bibtex,
    get_citation_graph,
    add_citation,
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

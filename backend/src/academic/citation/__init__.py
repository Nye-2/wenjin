"""Citation management module.

This module provides citation formatting functionality including:
- Multi-format citation formatting (APA, MLA, Chicago, IEEE)
- BibTeX parsing for Reference Library imports

Example usage:

    from src.academic.citation import APAFormatter

    # Format a citation
    formatter = APAFormatter()
    citation = formatter.format_citation(paper_dict)
"""

from .bibtex import BibTeXParser
from .formatters import (
    APAFormatter,
    ChicagoFormatter,
    CitationFormatter,
    IEEEFormatter,
    MLAFormatter,
)

__all__ = [
    # Formatters
    "CitationFormatter",
    "APAFormatter",
    "MLAFormatter",
    "ChicagoFormatter",
    "IEEEFormatter",
    # BibTeX
    "BibTeXParser",
]

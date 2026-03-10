# src/academic/literature/__init__.py
"""Literature module for TOC-based paper navigation."""

from .extraction.pdf_extractor import PDFExtractor
from .navigation import PaperTOC, SectionContent, TOCEntry, TocService, SectionLoader
from .tools import list_papers, get_section, search_external, get_paper_by_doi

__all__ = [
    # Extraction
    "PDFExtractor",
    # Navigation
    "PaperTOC",
    "SectionContent",
    "TOCEntry",
    "TocService",
    "SectionLoader",
    # Tools
    "list_papers",
    "get_section",
    "search_external",
    "get_paper_by_doi",
]

# src/academic/literature/__init__.py
"""Literature module for TOC-based paper navigation."""

from .extraction.pdf_extractor import PDFExtractor
from .navigation import PaperTOC, SectionContent, SectionLoader, TOCEntry, TocService
from .tools import get_paper_by_doi, get_section, list_papers, search_external

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

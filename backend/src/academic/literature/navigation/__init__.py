# src/academic/literature/navigation/__init__.py
"""TOC navigation module."""

from .models import PaperTOC, SectionContent, TOCEntry
from .section_loader import SectionLoader
from .toc_service import TocService

__all__ = ["PaperTOC", "SectionContent", "TOCEntry", "SectionLoader", "TocService"]

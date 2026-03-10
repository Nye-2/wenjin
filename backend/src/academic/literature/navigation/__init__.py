# src/academic/literature/navigation/__init__.py
"""TOC navigation module."""

from .models import PaperTOC, SectionContent, TOCEntry
from .toc_service import TocService

# TODO: Uncomment this import when SectionLoader is implemented (Task 4)
# from .section_loader import SectionLoader

__all__ = ["PaperTOC", "SectionContent", "TOCEntry", "TocService"]  # , "SectionLoader"]

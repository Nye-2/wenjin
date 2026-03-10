# src/academic/literature/navigation/__init__.py
"""TOC navigation module."""

from .models import PaperTOC, SectionContent, TOCEntry

# TODO: Uncomment these imports when TocService and SectionLoader are implemented (Tasks 3 & 4)
# from .toc_service import TocService
# from .section_loader import SectionLoader

__all__ = ["PaperTOC", "SectionContent", "TOCEntry"]  # , "TocService", "SectionLoader"]

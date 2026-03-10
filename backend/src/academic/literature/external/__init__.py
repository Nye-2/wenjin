# src/academic/literature/external/__init__.py
"""External academic database integration."""

from .base import ExternalDBBase, PaperSearchResult
from .semantic_scholar import SemanticScholarClient

__all__ = ["ExternalDBBase", "PaperSearchResult", "SemanticScholarClient"]

# src/academic/literature/external/__init__.py
"""External academic database integration."""

from .arxiv import ArxivClient
from .base import ExternalDBBase, PaperSearchResult
from .crossref import CrossrefClient
from .openalex import OpenAlexClient
from .semantic_scholar import SemanticScholarClient

__all__ = [
    "ArxivClient",
    "CrossrefClient",
    "ExternalDBBase",
    "OpenAlexClient",
    "PaperSearchResult",
    "SemanticScholarClient",
]

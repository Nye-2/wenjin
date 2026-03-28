"""Base class for citation formatters."""

from abc import ABC, abstractmethod
from typing import Any


class CitationFormatter(ABC):
    """Base class for citation formatters.

    All citation formatters (APA, MLA, Chicago, IEEE) should inherit
    from this class and implement the abstract methods.
    """

    @property
    @abstractmethod
    def style_name(self) -> str:
        """Return the style name (e.g., 'APA', 'MLA').

        Returns:
            The citation style name as a string
        """
        pass

    @abstractmethod
    def format_citation(self, paper: dict[str, Any], in_text: bool = False) -> str:
        """Format a single citation.

        Args:
            paper: Paper metadata dict with keys like 'title', 'authors', 'year', etc.
            in_text: If True, format for in-text citation (e.g., "(Smith, 2024)")

        Returns:
            Formatted citation string
        """
        pass

    @abstractmethod
    def format_bibliography_entry(self, paper: dict[str, Any]) -> str:
        """Format a bibliography/reference list entry.

        Args:
            paper: Paper metadata dict with keys like 'title', 'authors', 'year', etc.

        Returns:
            Formatted bibliography entry
        """
        pass

    def format_authors(self, authors: list[dict[str, Any]]) -> str:
        """Format author list.

        Default implementation - subclasses may override.

        Args:
            authors: List of author dicts with 'name' and optionally 'affiliation'

        Returns:
            Formatted author string
        """
        if not authors:
            return ""
        return ", ".join(a.get("name", "") for a in authors)

"""IEEE citation formatter."""

from typing import Any

from .base import CitationFormatter


class IEEEFormatter(CitationFormatter):
    """IEEE citation formatter."""

    @property
    def style_name(self) -> str:
        return "IEEE"

    def format_authors(self, authors: list[dict[str, Any]]) -> str:
        """IEEE author format: J. Smith and J. Doe.

        All authors: Initial. Last
        """
        if not authors:
            return ""

        formatted = []
        for author in authors:
            name = author.get("name", "")
            parts = name.split()
            if len(parts) >= 2:
                # Get initials from all parts except the last
                initials = ". ".join(p[0].upper() for p in parts[:-1]) + "."
                last = parts[-1]
                formatted.append(f"{initials} {last}")
            else:
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} and {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + ", and " + formatted[-1]

    def format_citation(self, paper: dict[str, Any], in_text: bool = False) -> str:
        """Format IEEE citation.

        In-text: [Author, Year] - author-year format for inline use
        Reference: J. Smith, "Title," *Journal*, 2024, doi: 10.xxx.
        """
        if in_text:
            # IEEE uses numeric references [1], but we return author-year
            # for standalone inline use (actual numbering at document level)
            authors = paper.get("authors", [])
            year = paper.get("year", "n.d.")
            first_author = self._get_first_author_lastname(authors)
            if len(authors) > 1:
                return f"[{first_author} et al., {year}]"
            return f"[{first_author}, {year}]"

        return self.format_bibliography_entry(paper)

    def _get_first_author_lastname(self, authors: list[dict[str, Any]]) -> str:
        """Get last name of first author."""
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"

    def format_bibliography_entry(self, paper: dict[str, Any]) -> str:
        """Format IEEE bibliography entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors) + ",")

        # Title in quotes
        title = paper.get("title", "")
        if title:
            parts.append(f'"{title},"')

        # Container (venue) italicized
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*,")

        # Year at end (before DOI)
        year = paper.get("year")
        if year:
            parts.append(f"{year},")

        # DOI
        doi = paper.get("doi")
        if doi:
            parts.append(f"doi: {doi}")

        result = " ".join(parts)
        # Clean up trailing comma and ensure period
        result = result.rstrip(",")
        result += "."
        return result

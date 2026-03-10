"""APA 7th Edition citation formatter."""

from .base import CitationFormatter


class APAFormatter(CitationFormatter):
    """APA 7th Edition citation formatter."""

    @property
    def style_name(self) -> str:
        return "APA"

    def format_authors(self, authors: list[dict]) -> str:
        """APA author format: Smith, J. A., & Jones, B. C."""
        if not authors:
            return ""

        formatted = []
        for author in authors:
            name = author.get("name", "")
            parts = name.split()
            if len(parts) >= 2:
                last = parts[-1]
                initials = ". ".join(p[0].upper() for p in parts[:-1]) + "."
                formatted.append(f"{last}, {initials}")
            else:
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} & {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + ", & " + formatted[-1]

    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format APA citation.

        In-text: (Smith, 2024) or (Vaswani et al., 2017)
        Reference: Smith, J. (2024). Title. Journal. DOI
        """
        authors = paper.get("authors", [])
        year = paper.get("year", "n.d.")

        if in_text:
            first_author = self._get_first_author_lastname(authors)
            if len(authors) > 1:
                return f"({first_author} et al., {year})"
            return f"({first_author}, {year})"

        return self.format_bibliography_entry(paper)

    def format_bibliography_entry(self, paper: dict) -> str:
        """Format APA bibliography entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors))

        # Year
        year = paper.get("year", "n.d.")
        parts.append(f"({year})")

        # Title
        title = paper.get("title", "")
        parts.append(f"{title}.")

        # Journal/Venue
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*")

        # DOI
        doi = paper.get("doi")
        if doi:
            parts.append(f"https://doi.org/{doi}")

        return " ".join(parts)

    def _get_first_author_lastname(self, authors: list[dict]) -> str:
        """Get last name of first author."""
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"

"""Chicago 17th Edition citation formatter."""

from .base import CitationFormatter


class ChicagoFormatter(CitationFormatter):
    """Chicago 17th Edition citation formatter."""

    @property
    def style_name(self) -> str:
        return "Chicago"

    def format_authors(self, authors: list[dict]) -> str:
        """Chicago author format: Smith, John, and Jane Doe.

        Same as MLA:
        First author: Last, First
        Additional authors: First Last
        """
        if not authors:
            return ""

        formatted = []
        for i, author in enumerate(authors):
            name = author.get("name", "")
            parts = name.split()
            if len(parts) >= 2:
                if i == 0:
                    # First author: Last, First
                    last = parts[-1]
                    first = " ".join(parts[:-1])
                    formatted.append(f"{last}, {first}")
                else:
                    # Other authors: First Last
                    formatted.append(name)
            else:
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]}, and {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + ", and " + formatted[-1]

    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format Chicago citation.

        In-text: (Smith 2024) - Author-Date style
        Bibliography: Smith, John. 2024. "Title." *Journal*. https://doi.org/10.xxx.
        """
        authors = paper.get("authors", [])
        year = paper.get("year", "n.d.")

        if in_text:
            first_author = self._get_first_author_lastname(authors)
            if year and year != "n.d.":
                return f"({first_author} {year})"
            return f"({first_author})"

        return self.format_bibliography_entry(paper)

    def format_bibliography_entry(self, paper: dict) -> str:
        """Format Chicago bibliography entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors) + ".")

        # Year first (after authors)
        year = paper.get("year")
        if year:
            parts.append(f"{year}.")

        # Title in quotes
        title = paper.get("title", "")
        if title:
            parts.append(f'"{title}."')

        # Container (venue) italicized
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*.")

        # DOI as full URL
        doi = paper.get("doi")
        if doi:
            parts.append(f"https://doi.org/{doi}")

        result = " ".join(parts)
        # Ensure trailing period
        result = result.rstrip(".")
        result += "."
        return result

    def _get_first_author_lastname(self, authors: list[dict]) -> str:
        """Get last name of first author."""
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"

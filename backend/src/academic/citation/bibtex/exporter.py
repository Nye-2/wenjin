"""BibTeX exporter for exporting references."""


def generate_citation_key(paper: dict) -> str:
    """Generate BibTeX citation key in simple format: FirstAuthorYear.

    This format (e.g., Smith2024) is designed for easy use with LaTeX \\cite{}.

    Args:
        paper: Paper dict with authors, year, title fields.

    Returns:
        Citation key string.
    """
    parts = []

    # First author lastname (preserve case for LaTeX)
    authors = paper.get("authors", [])
    if authors:
        name = authors[0].get("name", "")
        if name:
            # Get last name (last word)
            last_name = name.split()[-1]
            parts.append(last_name)

    # Year
    year = paper.get("year")
    if year:
        parts.append(str(year))
    else:
        parts.append("Nd")

    return "".join(parts) if parts else "Unknown"


class BibTeXExporter:
    """Export papers to BibTeX format."""

    def export(self, papers: list[dict]) -> str:
        """Export papers to BibTeX format.

        Args:
            papers: List of paper dicts

        Returns:
            BibTeX formatted string
        """
        entries = []

        for paper in papers:
            entry = self._format_entry(paper)
            entries.append(entry)

        return "\n\n".join(entries)

    def _format_entry(self, paper: dict) -> str:
        """Format single paper as BibTeX entry."""
        entry_type = self._determine_type(paper)
        key = self._generate_key(paper)

        lines = [f"@{entry_type}{{{key},"]

        # Required fields
        if paper.get("authors"):
            authors = " and ".join(
                a.get("name", "") for a in paper["authors"]
            )
            lines.append(f"  author = {{{authors}}},")

        if paper.get("title"):
            lines.append(f"  title = {{{paper['title']}}},")

        # Optional fields
        if paper.get("year"):
            lines.append(f"  year = {{{paper['year']}}},")

        if paper.get("venue"):
            if entry_type == "article":
                lines.append(f"  journal = {{{paper['venue']}}},")
            elif entry_type == "inproceedings":
                lines.append(f"  booktitle = {{{paper['venue']}}},")

        if paper.get("doi"):
            lines.append(f"  doi = {{{paper['doi']}}},")

        if paper.get("abstract"):
            lines.append(f"  abstract = {{{paper['abstract']}}},")

        lines.append("}")

        return "\n".join(lines)

    def _determine_type(self, paper: dict) -> str:
        """Determine BibTeX entry type from paper metadata."""
        venue = (paper.get("venue") or "").lower()
        if "conference" in venue or "workshop" in venue or "proceedings" in venue:
            return "inproceedings"
        elif "journal" in venue or "transactions" in venue:
            return "article"
        return "misc"

    def _generate_key(self, paper: dict) -> str:
        """Generate BibTeX citation key using standardized format."""
        return generate_citation_key(paper)

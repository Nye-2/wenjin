"""BibTeX parser for importing references."""

import re
from typing import Any, TypedDict


class BibTeXPaperPayload(TypedDict):
    """Structured payload compatible with ``PaperService.create``."""

    title: str
    authors: list[dict[str, Any]]
    year: int | None
    venue: str
    doi: str | None
    source: str


class BibTeXParser:
    """Parse BibTeX files into structured data."""

    ENTRY_PATTERN = re.compile(
        r"@(\w+)\s*\{\s*([^,]+)\s*,",
        re.MULTILINE
    )

    FIELD_PATTERN = re.compile(
        r"(\w+)\s*=\s*[{\"]([^}\"]+)[}\"]",
        re.MULTILINE
    )

    def parse(self, content: str) -> list[dict[str, str]]:
        """Parse BibTeX content into list of entries.

        Args:
            content: BibTeX file content

        Returns:
            List of entry dicts with 'type', 'key', and fields
        """
        entries = []

        for match in self.ENTRY_PATTERN.finditer(content):
            entry_type = match.group(1).lower()
            entry_key = match.group(2).strip()

            # Skip comments and string definitions
            if entry_type in ("comment", "string"):
                continue

            # Find entry body by counting braces
            start = match.end()
            brace_count = 1
            end = start
            while end < len(content) and brace_count > 0:
                if content[end] == "{":
                    brace_count += 1
                elif content[end] == "}":
                    brace_count -= 1
                end += 1

            body = content[start:end-1]

            # Parse fields
            fields = {"type": entry_type, "key": entry_key}
            for field_match in self.FIELD_PATTERN.finditer(body):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                fields[field_name] = field_value

            entries.append(fields)

        return entries

    def to_paper_dict(self, bibtex_entry: dict[str, str]) -> BibTeXPaperPayload:
        """Convert BibTeX entry to Paper-compatible dict.

        Args:
            bibtex_entry: Parsed BibTeX entry

        Returns:
            Paper-compatible dict
        """
        return {
            "title": bibtex_entry.get("title", ""),
            "authors": self._parse_authors(bibtex_entry.get("author", "")),
            "year": self._parse_year(bibtex_entry.get("year")),
            "venue": bibtex_entry.get("journal") or bibtex_entry.get("booktitle", ""),
            "doi": bibtex_entry.get("doi"),
            "source": "bibtex_import",
        }

    def _parse_authors(self, author_str: str) -> list[dict[str, str]]:
        """Parse BibTeX author string to list of dicts."""
        authors = []
        for name in author_str.split(" and "):
            name = name.strip()
            if name:
                authors.append({"name": name})
        return authors

    def _parse_year(self, year_str: str | None) -> int | None:
        """Parse year string to int."""
        if not year_str:
            return None
        try:
            return int(year_str)
        except ValueError:
            return None

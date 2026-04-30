"""Reference Library boundary constants shared by agent tool assembly."""

from __future__ import annotations

REFERENCE_LIBRARY_BYPASS_TOOL_NAMES = frozenset(
    {
        "semantic_scholar_search",
        "semantic_scholar_search_tool",
        "search_external",
        "get_paper_by_doi",
        "arxiv_search",
        "pubmed_search",
        "doi_resolve",
        "web_search",
        "crossref_search",
        "openalex_search",
    }
)


def is_reference_library_bypass_tool(tool_name: str | None) -> bool:
    """Return whether a tool can bypass workspace Reference Library SSOT."""
    return str(tool_name or "").strip() in REFERENCE_LIBRARY_BYPASS_TOOL_NAMES


"""SearcherSubagent -- calls configured search sources, deduplicates results."""

from __future__ import annotations

import logging
import re

from src.services.search import sources as _sources  # noqa: F401 — auto-register
from src.services.search.base import SearchResult
from src.services.search.registry import get_search_source

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent

logger = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/whitespace for dedup comparison."""
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    """Deduplicate by DOI (if present) then by normalised title."""
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    out: list[SearchResult] = []

    for r in results:
        if r.doi:
            doi_key = r.doi.lower().strip()
            if doi_key in seen_doi:
                continue
            seen_doi.add(doi_key)

        title_key = _normalize_title(r.title)
        if title_key in seen_title:
            continue
        seen_title.add(title_key)

        out.append(r)

    return out


@subagent("searcher")
class SearcherSubagent(SubagentBase):
    """Searches academic sources using configured search APIs.

    Required inputs:
        query (str): The search query string.

    Skill config keys:
        sources (list[str]): Names of search sources to call.

    Output shape::

        {
            "papers": [
                {"title": str, "authors": [str], "year": int | None, ...},
                ...
            ]
        }
    """

    allowed_tools: list[str] = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        """Execute search across configured sources and deduplicate."""
        if ctx.skill is None:
            return SubagentResult(output={"papers": []})

        config = ctx.skill.config
        source_names: list[str] = config.get("sources", [])
        query: str = ctx.inputs.get("query", "")
        limit: int = int(config.get("max_results", 30))

        year_range: tuple[int, int] | None = None
        year_min = config.get("year_min")
        if year_min:
            from datetime import datetime
            year_range = (int(year_min), datetime.now().year)

        all_results: list[SearchResult] = []

        for src_name in source_names:
            try:
                source = get_search_source(src_name)
                results = await source.search(query, year_range=year_range, limit=limit)
                all_results.extend(results)
            except Exception:
                logger.warning("Search source %r failed", src_name, exc_info=True)

        deduped = _deduplicate(all_results)

        return SubagentResult(
            output={"papers": [r.model_dump() for r in deduped]},
            tool_calls=[],
            token_usage={"input": 0, "output": 0},
        )

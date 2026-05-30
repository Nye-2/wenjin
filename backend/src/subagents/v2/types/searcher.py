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


def _normalize_search_query(query: str) -> str:
    """Extract an academic search query from a natural-language task request."""
    text = query.strip()
    if not text:
        return ""

    marker_match = re.search(r"(?:主题|topic|query)\s*[:：]\s*(.+)", text, flags=re.IGNORECASE)
    if marker_match:
        text = marker_match.group(1)

    stop_match = re.search(
        r"(?:。|；|;)?\s*(?:请输出|输出[:：]|请把|请将|并给|后续|保存进|保存到)",
        text,
    )
    if stop_match:
        text = text[: stop_match.start()]

    # Semantic Scholar performs best with compact English academic terms.  When
    # the user request is bilingual, keep the English spans and discard UI/task
    # instructions around them.
    ascii_spans = re.findall(r"[A-Za-z0-9][A-Za-z0-9\s+/#&.,:;()'’_-]*", text)
    english = " ".join(span.strip(" ,.;:()'’_-") for span in ascii_spans if span.strip())
    if english:
        text = english

    text = re.sub(r"[/,_:;()'’\"“”]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


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
            ],
            "text": str,
            "quality_gates_checked": [str],
            "query_log": [object],
            "included_sources": [object],
            "borderline_sources": [object],
            "rejected_sources": [object],
            "source_gaps": [object]
        }
    """

    allowed_tools: list[str] = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        """Execute search across configured sources and deduplicate.

        Raises on missing query or when *every* configured source fails so the
        runner records a real error in ``node_results`` instead of silently
        returning an empty paper list (which the user would see as
        "completed, but no results" with no actionable signal).
        """
        if ctx.skill is None:
            return SubagentResult(output={"papers": []})

        config = ctx.skill.config
        search_config = config.get("search")
        if not isinstance(search_config, dict):
            extensions = config.get("extensions")
            search_config = extensions.get("search") if isinstance(extensions, dict) else None
        if not isinstance(search_config, dict):
            search_config = config

        source_names: list[str] = list(search_config.get("sources") or [])
        raw_query: str = (ctx.inputs.get("query") or "").strip()
        query = _normalize_search_query(raw_query)
        limit: int = int(search_config.get("max_results", 30))

        if not source_names:
            raise ValueError(
                "searcher subagent invoked without configured search sources"
            )

        if not query:
            raise ValueError(
                "searcher subagent invoked with empty query — check the "
                "capability YAML 'inputs.query' template renders against the brief"
            )

        year_range: tuple[int, int] | None = None
        year_min = search_config.get("year_min")
        if year_min:
            from datetime import datetime
            year_range = (int(year_min), datetime.now().year)

        all_results: list[SearchResult] = []
        source_errors: list[tuple[str, str]] = []

        for src_name in source_names:
            try:
                source = get_search_source(src_name)
                results = await source.search(query, year_range=year_range, limit=limit)
                all_results.extend(results)
            except Exception as exc:
                logger.warning("Search source %r failed", src_name, exc_info=True)
                source_errors.append((src_name, str(exc)))

        # All configured sources failed → propagate so the run shows failed_partial
        # instead of "completed with 0 papers".
        if source_names and len(source_errors) == len(source_names):
            joined = "; ".join(f"{n}: {e}" for n, e in source_errors)
            raise RuntimeError(f"all search sources failed ({joined})")

        deduped = _deduplicate(all_results)
        papers = [r.model_dump() for r in deduped]
        source_error_records = [
            {"source": name, "error": error}
            for name, error in source_errors
        ]

        return SubagentResult(
            output={
                "papers": papers,
                "text": _search_summary(query, papers, source_error_records),
                "quality_gates_checked": _checked_quality_gates(ctx, config),
                "query_log": [
                    {
                        "raw_query": raw_query,
                        "normalized_query": query,
                        "sources": source_names,
                        "max_results": limit,
                        "year_range": list(year_range) if year_range else None,
                        "source_errors": source_error_records,
                    }
                ],
                "included_sources": papers,
                "borderline_sources": [],
                "rejected_sources": [],
                "source_gaps": _source_gaps(papers, source_error_records),
            },
            tool_calls=[],
            token_usage={"input": 0, "output": 0},
        )


def _checked_quality_gates(ctx: SubagentContext, config: dict) -> list[str]:
    contract = ctx.inputs.get("quality_contract")
    if isinstance(contract, dict):
        gates = contract.get("acknowledgement_required_gates") or contract.get("quality_gates")
        return _string_list(gates)
    return _string_list(config.get("quality_gates"))


def _search_summary(query: str, papers: list[dict], source_errors: list[dict]) -> str:
    parts = [f"Search query `{query}` returned {len(papers)} deduplicated source(s)."]
    if source_errors:
        failed = ", ".join(str(item.get("source")) for item in source_errors)
        parts.append(f"Source failures recorded: {failed}.")
    return " ".join(parts)


def _source_gaps(papers: list[dict], source_errors: list[dict]) -> list[dict]:
    gaps: list[dict] = []
    if not papers:
        gaps.append({"type": "no_results", "message": "No sources were returned."})
    for item in source_errors:
        gaps.append(
            {
                "type": "source_error",
                "source": item.get("source"),
                "message": item.get("error"),
            }
        )
    return gaps


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]

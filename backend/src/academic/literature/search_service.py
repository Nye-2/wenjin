"""Multi-source literature search service."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.services.search import sources as _sources  # noqa: F401 - auto-register sources
from src.services.search.base import SearchResult, SearchSource
from src.services.search.registry import get_search_source

logger = logging.getLogger(__name__)

DEFAULT_LITERATURE_SEARCH_LIMIT = 10
DEFAULT_LITERATURE_SEARCH_SOURCES = ("semantic_scholar", "web_search", "curated_academic")


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _normalize_query(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_doi(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("https://doi.org/"):
        normalized = normalized.removeprefix("https://doi.org/")
    if normalized.startswith("http://dx.doi.org/"):
        normalized = normalized.removeprefix("http://dx.doi.org/")
    return normalized or None


def _normalize_title(value: str) -> str:
    normalized = re.sub(r"\W+", " ", str(value or "").lower(), flags=re.UNICODE)
    return " ".join(normalized.split())


def _dedupe_key(paper: SearchResult) -> str:
    doi = _normalize_doi(paper.doi)
    if doi:
        return f"doi:{doi}"
    if paper.external_id:
        return f"{paper.source}:{paper.external_id}"
    return f"title:{_normalize_title(paper.title)}:{paper.year or ''}"


def _verified_paper_dict(
    paper: SearchResult,
    *,
    retrieval_query: str,
    verified_at: str,
) -> dict[str, Any]:
    source = paper.source or "unknown"
    return {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "doi": _normalize_doi(paper.doi),
        "url": paper.url,
        "abstract": paper.abstract,
        "citations_count": paper.citations,
        "source": source,
        "external_id": paper.external_id,
        "verified_at": verified_at,
        "evidence_level": _evidence_level_for_source(paper),
        "retrieval_query": retrieval_query,
        "raw": paper.raw,
    }


class LiteratureSearchService:
    """Canonical literature search over registered academic and web sources.

    This service owns verified paper retrieval. LLM callers may synthesize over
    the returned evidence, but they should not create additional paper records.
    """

    def __init__(
        self,
        *,
        sources: list[SearchSource] | None = None,
        source_names: list[str] | None = None,
    ) -> None:
        self._sources = sources
        self._source_names = list(source_names or DEFAULT_LITERATURE_SEARCH_SOURCES)

    async def search(
        self,
        *,
        query: str,
        discipline: str | None = None,
        limit: int = DEFAULT_LITERATURE_SEARCH_LIMIT,
    ) -> dict[str, Any]:
        normalized_query = _normalize_query(query)
        if not normalized_query:
            normalized_query = "research topic"
        normalized_limit = max(1, min(int(limit or DEFAULT_LITERATURE_SEARCH_LIMIT), 20))
        verified_at = _utc_now_iso()

        raw_results: list[SearchResult] = []
        source_records: list[dict[str, Any]] = []
        source_errors: list[dict[str, str]] = []
        for source in self._resolved_sources():
            try:
                source_results = await source.search(
                    normalized_query,
                    year_range=None,
                    limit=normalized_limit,
                )
                raw_results.extend(source_results)
                source_records.append(
                    {
                        "source": source.name,
                        "status": "ok",
                        "returned": len(source_results),
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Literature search source '%s' failed for query '%s': %s",
                    source.name,
                    normalized_query,
                    exc,
                )
                source_records.append(
                    {
                        "source": source.name,
                        "status": "failed",
                        "returned": 0,
                        "error": str(exc),
                    }
                )
                source_errors.append({"source": source.name, "error": str(exc)})

        if raw_results and source_errors:
            status = "partial"
        elif raw_results:
            status = "ok"
        else:
            status = "failed" if source_errors else "empty"

        verified_papers: list[dict[str, Any]] = []
        seen: set[str] = set()
        for paper in raw_results:
            if not paper.title.strip():
                continue
            key = _dedupe_key(paper)
            if key in seen:
                continue
            seen.add(key)
            verified_papers.append(
                _verified_paper_dict(
                    paper,
                    retrieval_query=normalized_query,
                    verified_at=verified_at,
                )
            )

        return {
            "query": normalized_query,
            "discipline": discipline,
            "source": "literature_search",
            "verified_papers": verified_papers,
            "retrieval": {
                "source": "literature_search",
                "sources": source_records,
                "query": normalized_query,
                "limit": normalized_limit,
                "returned": len(raw_results),
                "verified": len(verified_papers),
                "status": status,
                "source_errors": source_errors,
                "verified_at": verified_at,
            },
        }

    def _resolved_sources(self) -> list[SearchSource]:
        if self._sources is not None:
            return list(self._sources)
        return [get_search_source(name) for name in self._source_names]


def _evidence_level_for_source(paper: SearchResult) -> str:
    raw_level = paper.raw.get("evidence_level") if isinstance(paper.raw, dict) else None
    if isinstance(raw_level, str) and raw_level.strip():
        return raw_level.strip()
    if paper.source == "semantic_scholar":
        return "semantic_scholar_metadata"
    if paper.source == "web_search":
        return "web_search_result_snippet"
    return f"{paper.source or 'unknown'}_metadata"

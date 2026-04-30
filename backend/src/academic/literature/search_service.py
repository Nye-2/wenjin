"""Semantic Scholar backed literature search service."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from .external import PaperSearchResult, SemanticScholarClient

logger = logging.getLogger(__name__)

DEFAULT_SEMANTIC_SCHOLAR_LIMIT = 10


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


def _dedupe_key(paper: PaperSearchResult) -> str:
    doi = _normalize_doi(paper.doi)
    if doi:
        return f"doi:{doi}"
    if paper.external_id:
        return f"{paper.source}:{paper.external_id}"
    return f"title:{_normalize_title(paper.title)}:{paper.year or ''}"


def _verified_paper_dict(
    paper: PaperSearchResult,
    *,
    retrieval_query: str,
    verified_at: str,
) -> dict[str, Any]:
    return {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "doi": _normalize_doi(paper.doi),
        "url": paper.url,
        "abstract": paper.abstract,
        "citations_count": paper.citations_count,
        "source": "semantic_scholar",
        "external_id": paper.external_id,
        "verified_at": verified_at,
        "evidence_level": "semantic_scholar_metadata",
        "retrieval_query": retrieval_query,
    }


class LiteratureSearchService:
    """Canonical single-source literature search backed by Semantic Scholar.

    This service owns verified paper retrieval. LLM callers may synthesize over
    the returned evidence, but they should not create additional paper records.
    """

    def __init__(self, client: SemanticScholarClient | None = None):
        self.client = client or SemanticScholarClient()

    async def search(
        self,
        *,
        query: str,
        discipline: str | None = None,
        limit: int = DEFAULT_SEMANTIC_SCHOLAR_LIMIT,
    ) -> dict[str, Any]:
        normalized_query = _normalize_query(query)
        if not normalized_query:
            normalized_query = "research topic"
        normalized_limit = max(1, min(int(limit or DEFAULT_SEMANTIC_SCHOLAR_LIMIT), 20))
        verified_at = _utc_now_iso()

        try:
            raw_results = await self.client.search(normalized_query, limit=normalized_limit)
            status = "ok"
            error = None
        except Exception as exc:
            logger.warning("Semantic Scholar search failed for query '%s': %s", normalized_query, exc)
            raw_results = []
            status = "failed"
            error = str(exc)

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
            "source": "semantic_scholar",
            "verified_papers": verified_papers,
            "retrieval": {
                "source": "semantic_scholar",
                "query": normalized_query,
                "limit": normalized_limit,
                "returned": len(raw_results),
                "verified": len(verified_papers),
                "status": status,
                "error": error,
                "verified_at": verified_at,
            },
        }

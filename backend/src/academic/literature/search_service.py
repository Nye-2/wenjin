"""Literature projection over the canonical model-native search tool."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.services.search.model_native import MODEL_NATIVE_SEARCH_TOOL_ID
from src.tools.orchestrator import (
    ResearchToolOutcome,
    ToolInvocationContext,
    ToolOrchestrator,
    ToolOutcomeStatus,
    ToolPolicy,
)

DEFAULT_LITERATURE_SEARCH_LIMIT = 10


def _normalize_query(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


class LiteratureSearchService:
    """Build paper candidates only from ToolOrchestrator source receipts."""

    def __init__(
        self,
        *,
        orchestrator: ToolOrchestrator | None = None,
        invocation_context: ToolInvocationContext | None = None,
        tool_policy: ToolPolicy | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._invocation_context = invocation_context
        self._tool_policy = tool_policy

    async def search(
        self,
        *,
        query: str,
        discipline: str | None = None,
        limit: int = DEFAULT_LITERATURE_SEARCH_LIMIT,
    ) -> dict[str, Any]:
        normalized_query = _normalize_query(query) or "research topic"
        normalized_limit = max(1, min(int(limit or DEFAULT_LITERATURE_SEARCH_LIMIT), 20))
        if (
            self._orchestrator is None
            or self._invocation_context is None
            or self._tool_policy is None
        ):
            return _unavailable_result(
                query=normalized_query,
                discipline=discipline,
                limit=normalized_limit,
                reason="mission_tool_context_required",
            )

        outcome = await self._orchestrator.invoke(
            MODEL_NATIVE_SEARCH_TOOL_ID,
            {"query": normalized_query, "limit": normalized_limit},
            context=self._invocation_context,
            policy=self._tool_policy,
        )
        return _result_from_outcome(
            query=normalized_query,
            discipline=discipline,
            limit=normalized_limit,
            outcome=outcome,
        )


def _result_from_outcome(
    *,
    query: str,
    discipline: str | None,
    limit: int,
    outcome: ResearchToolOutcome,
) -> dict[str, Any]:
    verified_at = outcome.observed_at.astimezone(UTC).isoformat()
    papers = [
        {
            "title": source.title,
            "authors": list(source.authors),
            "year": None,
            "venue": source.publisher,
            "doi": None,
            "url": source.canonical_url,
            "abstract": None,
            "citations_count": None,
            "source": "web_page",
            "external_id": source.source_id,
            "verified_at": verified_at,
            "evidence_level": "provider_search_receipt",
            "retrieval_query": query,
            "raw": {
                "producer_tool_id": outcome.tool_id,
                "producer_tool_version": outcome.tool_version,
                "operation_id": outcome.operation_id,
                "verification_status": source.verification_status.value,
                "supported_claim_refs": list(source.supported_claim_refs),
            },
        }
        for source in outcome.source_refs[:limit]
    ]
    if outcome.status is ToolOutcomeStatus.SUCCESS:
        status = "ok"
    elif outcome.status is ToolOutcomeStatus.PARTIAL:
        status = "partial"
    else:
        status = "failed"
    return {
        "query": query,
        "discipline": discipline,
        "source": "literature_search",
        "verified_papers": papers,
        "retrieval": {
            "source": "literature_search",
            "tool_id": outcome.tool_id,
            "operation_id": outcome.operation_id,
            "query": query,
            "limit": limit,
            "returned": len(outcome.source_refs),
            "verified": len(papers),
            "status": status,
            "evidence_gaps": [
                ref.model_dump(mode="json")
                for ref in outcome.evidence_refs
                if ref.kind == "evidence_gap"
            ],
            "verified_at": verified_at,
            "summary": outcome.summary,
        },
    }


def _unavailable_result(
    *,
    query: str,
    discipline: str | None,
    limit: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "query": query,
        "discipline": discipline,
        "source": "literature_search",
        "verified_papers": [],
        "retrieval": {
            "source": "literature_search",
            "tool_id": MODEL_NATIVE_SEARCH_TOOL_ID,
            "query": query,
            "limit": limit,
            "returned": 0,
            "verified": 0,
            "status": "partial",
            "evidence_gaps": [
                {
                    "kind": "evidence_gap",
                    "reason": reason,
                    "message": (
                        "Verified web search requires an active Mission Runtime tool context."
                    ),
                }
            ],
            "verified_at": datetime.now(UTC).isoformat(),
        },
    }


__all__ = ["LiteratureSearchService"]

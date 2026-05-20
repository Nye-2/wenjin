"""Review handlers for source materialization."""

from __future__ import annotations

from typing import Any

from src.dataservice.domains.review.contracts import ReviewItemProjection
from src.dataservice.domains.source.contracts import SourceCreateCommand
from src.dataservice.domains.source.service import SourceDataDomainService


def build_source_candidate_review_handler(source_service: SourceDataDomainService):
    """Build a review handler that creates a source from accepted payload."""

    async def handler(item: ReviewItemProjection) -> dict[str, Any]:
        payload = dict(item.payload_json or {})
        payload.setdefault("workspace_id", item.workspace_id)
        source = await source_service.create_source(SourceCreateCommand(**payload))
        return {"source_id": source.id, "citation_key": source.citation_key}

    return handler

"""Review handlers for Prism materialization."""

from __future__ import annotations

from typing import Any

from src.dataservice.domains.prism.contracts import PrismFileVersionCreateCommand
from src.dataservice.domains.prism.service import PrismDataDomainService
from src.dataservice.domains.review.contracts import ReviewItemProjection


def build_prism_file_change_review_handler(prism_service: PrismDataDomainService):
    """Build a review handler that appends a Prism file version."""

    async def handler(item: ReviewItemProjection) -> dict[str, Any]:
        payload = dict(item.payload_json or {})
        command = PrismFileVersionCreateCommand(
            file_id=str(payload["file_id"]),
            review_item_id=item.id,
            content_inline=payload.get("content_inline"),
            content_asset_id=payload.get("content_asset_id"),
            content_hash=str(payload["content_hash"]),
            created_by=str(payload.get("created_by") or "review"),
        )
        version = await prism_service.append_file_version(command)
        if version is None:
            return {"applied": False, "reason": "file_not_found"}
        return {
            "applied": True,
            "file_id": version.file_id,
            "version_id": version.id,
            "version_no": version.version_no,
        }

    return handler

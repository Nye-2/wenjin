"""Review handlers for sandbox artifact materialization."""

from __future__ import annotations

from typing import Any

from src.dataservice.domains.review.contracts import ReviewItemProjection
from src.dataservice.domains.sandbox.service import SandboxDataDomainService


def build_sandbox_artifact_review_handler(service: SandboxDataDomainService):
    """Build a review handler that marks an accepted sandbox artifact as materialized."""

    async def handler(item: ReviewItemProjection) -> dict[str, Any]:
        payload = dict(item.payload_json or {})
        artifact_id = payload.get("sandbox_artifact_id") or item.target_ref_json.get("sandbox_artifact_id")
        if not artifact_id:
            return {"applied": False, "reason": "missing_sandbox_artifact_id"}
        artifact = await service.mark_artifact_materialized(str(artifact_id), review_item_id=item.id)
        if artifact is None:
            return {"applied": False, "reason": "sandbox_artifact_not_found"}
        return {
            "applied": True,
            "sandbox_artifact_id": artifact.id,
            "workspace_asset_id": artifact.workspace_asset_id,
            "materialization_status": artifact.materialization_status,
        }

    return handler

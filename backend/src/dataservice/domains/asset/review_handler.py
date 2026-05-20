"""Review handlers for workspace asset materialization."""

from __future__ import annotations

from typing import Any

from src.dataservice.domains.asset.contracts import WorkspaceAssetCreateCommand
from src.dataservice.domains.asset.service import WorkspaceAssetService
from src.dataservice.domains.review.contracts import ReviewItemProjection


def build_workspace_asset_review_handler(asset_service: WorkspaceAssetService):
    """Build a review handler that registers an accepted asset payload."""

    async def handler(item: ReviewItemProjection) -> dict[str, Any]:
        payload = dict(item.payload_json or {})
        payload.setdefault("workspace_id", item.workspace_id)
        payload.setdefault("source_kind", "review_item")
        payload.setdefault("source_id", item.id)
        asset = await asset_service.register_asset(WorkspaceAssetCreateCommand(**payload))
        return {"asset_id": asset.id, "storage_path": asset.storage_path}

    return handler

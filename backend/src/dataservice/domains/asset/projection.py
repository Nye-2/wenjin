"""Workspace asset projection helpers."""

from __future__ import annotations

from src.dataservice.domains.asset.contracts import (
    WorkspaceAssetDownloadProjection,
    WorkspaceAssetProjection,
)
from src.dataservice.domains.asset.models import WorkspaceAssetRecord


def asset_to_projection(record: WorkspaceAssetRecord) -> WorkspaceAssetProjection:
    return WorkspaceAssetProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        asset_kind=record.asset_kind,
        name=record.name,
        title=record.title,
        mime_type=record.mime_type,
        storage_backend=record.storage_backend,
        storage_path=record.storage_path,
        size_bytes=record.size_bytes,
        content_hash=record.content_hash,
        parent_asset_id=record.parent_asset_id,
        created_by=record.created_by,
        source_kind=record.source_kind,
        source_id=record.source_id,
        metadata_json=dict(record.metadata_json or {}),
        deleted_at=record.deleted_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def asset_to_download_projection(record: WorkspaceAssetRecord) -> WorkspaceAssetDownloadProjection:
    asset = asset_to_projection(record)
    return WorkspaceAssetDownloadProjection(
        asset=asset,
        storage_backend=asset.storage_backend,
        storage_path=asset.storage_path,
        mime_type=asset.mime_type,
        filename=asset.name,
    )

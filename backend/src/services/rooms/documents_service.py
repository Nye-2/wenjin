"""Workspace document facade backed by DataService Asset."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.asset_api import AssetDataService, WorkspaceAssetProjection, WorkspaceAssetUpdateCommand

_DOCUMENT_SOURCE_KIND = "documents_room"
_MIGRATED_DOCUMENT_SOURCE_KIND = "documents_v2"
_DOCUMENT_SOURCE_KINDS = {_DOCUMENT_SOURCE_KIND, _MIGRATED_DOCUMENT_SOURCE_KIND}


@dataclass
class DocumentAssetView:
    """Document-room projection over a canonical workspace asset."""

    id: str
    workspace_id: str
    name: str
    kind: str
    mime_type: str | None = None
    storage_path: str | None = None
    size_bytes: int | None = None
    parent_id: str | None = None
    version: int = 1
    metadata_json: dict[str, Any] = field(default_factory=dict)
    added_by: str = "system"
    created_at: Any = None
    updated_at: Any = None
    deleted_at: Any = None


class DocumentsService:
    """Asset-backed workspace document service."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._assets = AssetDataService(db)

    async def add(self, workspace_id: str, data: dict[str, Any]) -> DocumentAssetView:
        """Add a new document asset."""

        if parent_id := data.get("parent_id"):
            version_data = dict(data)
            version_data.pop("parent_id", None)
            return await self.commit_version(workspace_id, str(parent_id), version_data)

        metadata = dict(data.get("metadata_json") or {})
        kind = str(data.get("kind") or "document")
        metadata.setdefault("kind", kind)
        metadata.setdefault("version", 1)
        storage_path = data.get("storage_path") or _inline_storage_path(data)
        asset = await self._assets.register_asset_record(
            workspace_id=workspace_id,
            asset_kind=kind,
            name=str(data["name"]),
            title=str(data.get("name") or ""),
            mime_type=data.get("mime_type") or "text/markdown",
            storage_backend="local",
            storage_path=storage_path,
            size_bytes=data.get("size_bytes") or _inline_size(metadata),
            created_by=str(data.get("added_by") or "user"),
            source_kind=_DOCUMENT_SOURCE_KIND,
            source_id=None,
            metadata_json=metadata,
        )
        return _asset_to_document(asset)

    async def commit_version(
        self,
        workspace_id: str,
        parent_id: str,
        data: dict[str, Any],
    ) -> DocumentAssetView:
        """Create a new document asset version linked to parent_id."""

        parent = await self.get(workspace_id, parent_id)
        if parent is None:
            raise ValueError(f"Parent document {parent_id} not found")
        metadata = dict(data.get("metadata_json") or {})
        version = int(parent.version or 1) + 1
        metadata.setdefault("kind", data.get("kind") or parent.kind)
        metadata["version"] = version
        metadata["parent_id"] = parent_id
        asset = await self._assets.register_asset_record(
            workspace_id=workspace_id,
            asset_kind=str(metadata["kind"]),
            name=str(data.get("name") or parent.name),
            title=str(data.get("name") or parent.name),
            mime_type=data.get("mime_type") or parent.mime_type,
            storage_backend="local",
            storage_path=data.get("storage_path") or _inline_storage_path(data),
            size_bytes=data.get("size_bytes") or _inline_size(metadata),
            parent_asset_id=parent_id,
            created_by=str(data.get("added_by") or parent.added_by),
            source_kind=_DOCUMENT_SOURCE_KIND,
            source_id=parent_id,
            metadata_json=metadata,
        )
        return _asset_to_document(asset)

    async def list(self, workspace_id: str, limit: int = 100) -> list[DocumentAssetView]:
        """List active document assets for a workspace."""

        room_assets = await self._assets.list_assets(
            workspace_id=workspace_id,
            source_kind=_DOCUMENT_SOURCE_KIND,
            include_deleted=False,
            limit=limit,
        )
        migrated_assets = await self._assets.list_assets(
            workspace_id=workspace_id,
            source_kind=_MIGRATED_DOCUMENT_SOURCE_KIND,
            include_deleted=False,
            limit=max(0, limit - len(room_assets)),
        )
        assets = sorted(
            [*room_assets, *migrated_assets],
            key=_asset_sort_value,
            reverse=True,
        )
        return [_asset_to_document(asset) for asset in assets[:limit]]

    async def get(self, workspace_id: str, doc_id: str) -> DocumentAssetView | None:
        """Get one active document asset."""

        asset = await self._assets.get_asset(doc_id)
        if asset is None or asset.workspace_id != workspace_id or asset.deleted_at is not None:
            return None
        if asset.source_kind not in _DOCUMENT_SOURCE_KINDS:
            return None
        return _asset_to_document(asset)

    async def update(self, workspace_id: str, doc_id: str, data: dict[str, Any]) -> DocumentAssetView | None:
        """Update mutable document metadata."""

        current = await self.get(workspace_id, doc_id)
        if current is None:
            return None
        metadata = dict(current.metadata_json or {})
        if data.get("kind") is not None:
            metadata["kind"] = data["kind"]
        if data.get("metadata_json") is not None:
            metadata.update(dict(data["metadata_json"] or {}))
        asset = await self._assets.update_asset(
            doc_id,
            WorkspaceAssetUpdateCommand(
                name=data.get("name"),
                title=data.get("name"),
                mime_type=data.get("mime_type"),
                metadata_json=metadata,
            ),
        )
        return _asset_to_document(asset) if asset is not None else None

    async def delete(self, workspace_id: str, doc_id: str) -> bool:
        """Soft-delete a document asset."""

        current = await self.get(workspace_id, doc_id)
        if current is None:
            return False
        deleted = await self._assets.mark_deleted(doc_id)
        return deleted is not None


def _asset_to_document(asset: WorkspaceAssetProjection) -> DocumentAssetView:
    metadata = dict(asset.metadata_json or {})
    return DocumentAssetView(
        id=asset.id,
        workspace_id=asset.workspace_id,
        name=asset.name,
        kind=str(metadata.get("kind") or metadata.get("legacy_kind") or asset.asset_kind or "document"),
        mime_type=asset.mime_type,
        storage_path=asset.storage_path,
        size_bytes=asset.size_bytes,
        parent_id=asset.parent_asset_id or metadata.get("parent_id") or metadata.get("legacy_parent_id"),
        version=int(metadata.get("version") or metadata.get("legacy_version") or 1),
        metadata_json=metadata,
        added_by=asset.created_by,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        deleted_at=asset.deleted_at,
    )


def _asset_sort_value(asset: WorkspaceAssetProjection) -> float:
    stamp = asset.created_at or asset.updated_at
    return stamp.timestamp() if hasattr(stamp, "timestamp") else 0.0


def _inline_storage_path(data: dict[str, Any]) -> str:
    name = str(data.get("name") or "document").lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-") or "document"
    return f"inline://documents/{slug}"


def _inline_size(metadata: dict[str, Any]) -> int | None:
    content = metadata.get("content")
    return len(content.encode("utf-8")) if isinstance(content, str) else None

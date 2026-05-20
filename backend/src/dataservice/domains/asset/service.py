"""Workspace asset domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.asset.contracts import (
    WorkspaceAssetCreateCommand,
    WorkspaceAssetDownloadProjection,
    WorkspaceAssetProjection,
    WorkspaceAssetUpdateCommand,
)
from src.dataservice.domains.asset.projection import (
    asset_to_download_projection,
    asset_to_projection,
)
from src.dataservice.domains.asset.repository import WorkspaceAssetRepository


class WorkspaceAssetService:
    """DataService-owned workspace asset operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = WorkspaceAssetRepository(session)

    async def register_asset(self, command: WorkspaceAssetCreateCommand) -> WorkspaceAssetProjection:
        record = self.repository.create_asset(
            {
                "workspace_id": command.workspace_id,
                "asset_kind": command.asset_kind,
                "name": command.name,
                "title": command.title,
                "mime_type": command.mime_type,
                "storage_backend": command.storage_backend,
                "storage_path": command.storage_path,
                "size_bytes": command.size_bytes,
                "content_hash": command.content_hash,
                "parent_asset_id": command.parent_asset_id,
                "created_by": command.created_by,
                "source_kind": command.source_kind,
                "source_id": command.source_id,
                "metadata_json": dict(command.metadata_json or {}),
            }
        )
        await self._finish()
        return asset_to_projection(record)

    async def register_derivative(
        self,
        *,
        parent_asset_id: str,
        command: WorkspaceAssetCreateCommand,
    ) -> WorkspaceAssetProjection:
        return await self.register_asset(command.model_copy(update={"parent_asset_id": parent_asset_id}))

    async def get_asset(
        self,
        asset_id: str,
        *,
        include_deleted: bool = False,
    ) -> WorkspaceAssetProjection | None:
        record = await self.repository.get_asset(asset_id)
        if record is None or (record.deleted_at is not None and not include_deleted):
            return None
        return asset_to_projection(record)

    async def list_assets(
        self,
        *,
        workspace_id: str,
        asset_kind: str | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[WorkspaceAssetProjection]:
        return [
            asset_to_projection(record)
            for record in await self.repository.list_assets(
                workspace_id=workspace_id,
                asset_kind=asset_kind,
                source_kind=source_kind,
                source_id=source_id,
                include_deleted=include_deleted,
                limit=limit,
            )
        ]

    async def update_asset(
        self,
        asset_id: str,
        command: WorkspaceAssetUpdateCommand,
    ) -> WorkspaceAssetProjection | None:
        record = await self.repository.get_asset(asset_id)
        if record is None or record.deleted_at is not None:
            return None
        for field in ("name", "title", "mime_type", "metadata_json"):
            value = getattr(command, field)
            if value is not None:
                setattr(record, field, dict(value) if field == "metadata_json" else value)
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return asset_to_projection(record)

    async def mark_deleted(self, asset_id: str) -> WorkspaceAssetProjection | None:
        record = await self.repository.get_asset(asset_id)
        if record is None:
            return None
        record.deleted_at = datetime.now(UTC)
        record.updated_at = record.deleted_at
        await self._finish()
        return asset_to_projection(record)

    async def resolve_download(
        self,
        asset_id: str,
    ) -> WorkspaceAssetDownloadProjection | None:
        record = await self.repository.get_asset(asset_id)
        if record is None or record.deleted_at is not None:
            return None
        return asset_to_download_projection(record)

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

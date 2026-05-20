"""Workspace asset repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.asset.models import WorkspaceAssetRecord


class WorkspaceAssetRepository:
    """Persistence operations for workspace assets."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_asset(self, values: dict[str, Any]) -> WorkspaceAssetRecord:
        record = WorkspaceAssetRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_asset(self, asset_id: str) -> WorkspaceAssetRecord | None:
        result = await self.session.execute(
            select(WorkspaceAssetRecord).where(WorkspaceAssetRecord.id == asset_id)
        )
        return result.scalar_one_or_none()

    async def list_assets(
        self,
        *,
        workspace_id: str,
        asset_kind: str | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[WorkspaceAssetRecord]:
        query = (
            select(WorkspaceAssetRecord)
            .where(WorkspaceAssetRecord.workspace_id == workspace_id)
            .order_by(WorkspaceAssetRecord.created_at.desc())
            .limit(limit)
        )
        if asset_kind is not None:
            query = query.where(WorkspaceAssetRecord.asset_kind == asset_kind)
        if source_kind is not None:
            query = query.where(WorkspaceAssetRecord.source_kind == source_kind)
        if source_id is not None:
            query = query.where(WorkspaceAssetRecord.source_id == source_id)
        if not include_deleted:
            query = query.where(WorkspaceAssetRecord.deleted_at.is_(None))
        result = await self.session.execute(query)
        return list(result.scalars().all())

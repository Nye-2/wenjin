"""Workspace asset repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.artifact import Artifact
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

    def create_workspace_artifact(self, values: dict[str, Any]) -> Artifact:
        record = Artifact(**values)
        self.session.add(record)
        return record

    async def get_workspace_artifact(self, artifact_id: str) -> Artifact | None:
        result = await self.session.execute(
            select(Artifact).where(Artifact.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def find_latest_workspace_artifact(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> Artifact | None:
        result = await self.session.execute(
            select(Artifact)
            .where(
                and_(
                    Artifact.workspace_id == workspace_id,
                    Artifact.type == artifact_type,
                    Artifact.title == title,
                )
            )
            .order_by(Artifact.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_workspace_artifacts(
        self,
        *,
        workspace_id: str,
        artifact_type: str | None = None,
        artifact_types: list[str] | None = None,
        status: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        query = (
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .order_by(Artifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if artifact_type:
            query = query.where(Artifact.type == artifact_type)
        if artifact_types:
            query = query.where(Artifact.type.in_(artifact_types))
        if status:
            query = query.where(Artifact.status == status)
        if created_by_skills:
            query = query.where(Artifact.created_by_skill.in_(created_by_skills))
        elif created_by_skill:
            query = query.where(Artifact.created_by_skill == created_by_skill)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_workspace_artifacts(
        self,
        *,
        workspace_id: str | None = None,
        artifact_type: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
    ) -> int:
        query = select(func.count()).select_from(Artifact)
        if workspace_id is not None:
            query = query.where(Artifact.workspace_id == workspace_id)
        if artifact_type is not None:
            query = query.where(Artifact.type == artifact_type)
        if created_by_skills:
            query = query.where(Artifact.created_by_skill.in_(created_by_skills))
        elif created_by_skill:
            query = query.where(Artifact.created_by_skill == created_by_skill)
        result = await self.session.execute(query)
        return int(result.scalar() or 0)

    async def list_workspace_artifact_versions(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> list[Artifact]:
        result = await self.session.execute(
            select(Artifact)
            .where(
                and_(
                    Artifact.workspace_id == workspace_id,
                    Artifact.type == artifact_type,
                    Artifact.title == title,
                )
            )
            .order_by(Artifact.version.desc())
        )
        return list(result.scalars().all())

    async def delete_workspace_artifact(self, artifact: Artifact) -> None:
        await self.session.delete(artifact)

"""Artifact service facade backed by DataService asset/artifact projections."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.asset_api import (
    AssetDataService,
    LegacyArtifactCreateCommand,
    LegacyArtifactProjection,
    LegacyArtifactUpdateCommand,
)


class ArtifactService:
    """Compatibility facade for legacy artifact routes during DataService cutover."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._assets = AssetDataService(db)

    async def create(
        self,
        workspace_id: str,
        type: str,
        content: dict[str, Any],
        title: str | None = None,
        created_by_skill: str | None = None,
        parent_artifact_id: str | None = None,
    ) -> LegacyArtifactProjection:
        return await self._assets.create_legacy_artifact(
            LegacyArtifactCreateCommand(
                workspace_id=workspace_id,
                artifact_type=type,
                content=dict(content or {}),
                title=title,
                created_by_skill=created_by_skill,
                parent_artifact_id=parent_artifact_id,
            )
        )

    async def _lock_workspace_for_artifact_versioning(self, workspace_id: str) -> None:
        """Serialize version assignment for artifacts within one workspace."""
        from src.dataservice.workspace_api import WorkspaceDataService

        await WorkspaceDataService(self.db, autocommit=False).lock_workspace_for_update(
            workspace_id
        )

    async def _find_latest_version(
        self,
        workspace_id: str,
        type: str,
        title: str,
    ) -> LegacyArtifactProjection | None:
        return await self._assets.find_latest_legacy_artifact(
            workspace_id=workspace_id,
            artifact_type=type,
            title=title,
        )

    async def list_versions(
        self,
        workspace_id: str,
        type: str,
        title: str,
    ) -> list[LegacyArtifactProjection]:
        return await self._assets.list_legacy_artifact_versions(
            workspace_id=workspace_id,
            artifact_type=type,
            title=title,
        )

    async def get(self, artifact_id: str) -> LegacyArtifactProjection | None:
        return await self._assets.get_legacy_artifact(artifact_id)

    async def list_by_workspace(
        self,
        workspace_id: str,
        type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LegacyArtifactProjection]:
        return await self._assets.list_legacy_artifacts(
            workspace_id=workspace_id,
            artifact_type=type,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        artifact_id: str,
        **kwargs: Any,
    ) -> LegacyArtifactProjection | None:
        return await self._assets.update_legacy_artifact(
            artifact_id,
            LegacyArtifactUpdateCommand(
                title=kwargs.get("title"),
                content=kwargs.get("content"),
                status=kwargs.get("status"),
                artifact_type=kwargs.get("type"),
                version=kwargs.get("version"),
                parent_artifact_id=kwargs.get("parent_artifact_id"),
            ),
        )

    async def delete(self, artifact_id: str) -> bool:
        return await self._assets.delete_legacy_artifact(artifact_id)

    async def list_by_type(
        self,
        workspace_id: str,
        artifact_type: str,
    ) -> list[LegacyArtifactProjection]:
        return await self.list_by_workspace(
            workspace_id=workspace_id,
            type=artifact_type,
        )

    async def get_lineage(self, artifact_id: str) -> list[LegacyArtifactProjection]:
        return await self._assets.get_legacy_artifact_lineage(artifact_id)

"""Artifact service facade backed by DataService asset/artifact projections."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import (
    LegacyArtifactCreatePayload,
    LegacyArtifactPayload,
    LegacyArtifactUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client


class ArtifactService:
    """Compatibility facade for legacy artifact routes during DataService cutover."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self.db = db
        self._dataservice = dataservice

    async def create(
        self,
        workspace_id: str,
        type: str,
        content: dict[str, Any],
        title: str | None = None,
        created_by_skill: str | None = None,
        parent_artifact_id: str | None = None,
    ) -> LegacyArtifactPayload:
        command = LegacyArtifactCreatePayload(
                workspace_id=workspace_id,
                artifact_type=type,
                content=dict(content or {}),
                title=title,
                created_by_skill=created_by_skill,
                parent_artifact_id=parent_artifact_id,
            )
        if self._dataservice is not None:
            return await self._dataservice.create_legacy_artifact(command)
        async with dataservice_client() as client:
            return await client.create_legacy_artifact(command)

    async def _lock_workspace_for_artifact_versioning(self, workspace_id: str) -> None:
        """Serialize version assignment for artifacts within one workspace."""
        return None

    async def _find_latest_version(
        self,
        workspace_id: str,
        type: str,
        title: str,
    ) -> LegacyArtifactPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.find_latest_legacy_artifact(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )
        async with dataservice_client() as client:
            return await client.find_latest_legacy_artifact(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )

    async def list_versions(
        self,
        workspace_id: str,
        type: str,
        title: str,
    ) -> list[LegacyArtifactPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_legacy_artifact_versions(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )
        async with dataservice_client() as client:
            return await client.list_legacy_artifact_versions(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )

    async def get(self, artifact_id: str) -> LegacyArtifactPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.get_legacy_artifact(artifact_id)
        async with dataservice_client() as client:
            return await client.get_legacy_artifact(artifact_id)

    async def list_by_workspace(
        self,
        workspace_id: str,
        type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LegacyArtifactPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_legacy_artifacts(
                workspace_id=workspace_id,
                artifact_type=type,
                status=status,
                limit=limit,
                offset=offset,
            )
        async with dataservice_client() as client:
            return await client.list_legacy_artifacts(
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
    ) -> LegacyArtifactPayload | None:
        command = LegacyArtifactUpdatePayload(
            title=kwargs.get("title"),
            content=kwargs.get("content"),
            status=kwargs.get("status"),
            artifact_type=kwargs.get("type"),
            version=kwargs.get("version"),
            parent_artifact_id=kwargs.get("parent_artifact_id"),
        )
        if self._dataservice is not None:
            return await self._dataservice.update_legacy_artifact(
                artifact_id,
                command,
            )
        async with dataservice_client() as client:
            return await client.update_legacy_artifact(
                artifact_id,
                command,
            )

    async def delete(self, artifact_id: str) -> bool:
        if self._dataservice is not None:
            return await self._dataservice.delete_legacy_artifact(artifact_id)
        async with dataservice_client() as client:
            return await client.delete_legacy_artifact(artifact_id)

    async def list_by_type(
        self,
        workspace_id: str,
        artifact_type: str,
    ) -> list[LegacyArtifactPayload]:
        return await self.list_by_workspace(
            workspace_id=workspace_id,
            type=artifact_type,
        )

    async def get_lineage(self, artifact_id: str) -> list[LegacyArtifactPayload]:
        if self._dataservice is not None:
            return await self._dataservice.get_legacy_artifact_lineage(artifact_id)
        async with dataservice_client() as client:
            return await client.get_legacy_artifact_lineage(artifact_id)

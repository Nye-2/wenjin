"""Artifact service facade backed by DataService asset/artifact projections."""

from __future__ import annotations

from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import (
    WorkspaceArtifactCreatePayload,
    WorkspaceArtifactPayload,
    WorkspaceArtifactUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client


class ArtifactService:
    """Runtime facade for workspace artifact DataService operations."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self._dataservice = dataservice

    async def create(
        self,
        workspace_id: str,
        type: str,
        content: dict[str, Any],
        title: str | None = None,
        created_by_skill: str | None = None,
        parent_artifact_id: str | None = None,
    ) -> WorkspaceArtifactPayload:
        command = WorkspaceArtifactCreatePayload(
            workspace_id=workspace_id,
            artifact_type=type,
            content=dict(content or {}),
            title=title,
            created_by_skill=created_by_skill,
            parent_artifact_id=parent_artifact_id,
        )
        if self._dataservice is not None:
            return await self._dataservice.create_workspace_artifact(command)
        async with dataservice_client() as client:
            return await client.create_workspace_artifact(command)

    async def _lock_workspace_for_artifact_versioning(self, workspace_id: str) -> None:
        """Serialize version assignment for artifacts within one workspace."""
        return None

    async def _find_latest_version(
        self,
        workspace_id: str,
        type: str,
        title: str,
    ) -> WorkspaceArtifactPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.find_latest_workspace_artifact(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )
        async with dataservice_client() as client:
            return await client.find_latest_workspace_artifact(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )

    async def list_versions(
        self,
        workspace_id: str,
        type: str,
        title: str,
    ) -> list[WorkspaceArtifactPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_workspace_artifact_versions(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )
        async with dataservice_client() as client:
            return await client.list_workspace_artifact_versions(
                workspace_id=workspace_id,
                artifact_type=type,
                title=title,
            )

    async def get(self, artifact_id: str) -> WorkspaceArtifactPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.get_workspace_artifact(artifact_id)
        async with dataservice_client() as client:
            return await client.get_workspace_artifact(artifact_id)

    async def list_by_workspace(
        self,
        workspace_id: str,
        type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkspaceArtifactPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_workspace_artifacts(
                workspace_id=workspace_id,
                artifact_type=type,
                status=status,
                limit=limit,
                offset=offset,
            )
        async with dataservice_client() as client:
            return await client.list_workspace_artifacts(
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
    ) -> WorkspaceArtifactPayload | None:
        command = WorkspaceArtifactUpdatePayload(
            title=kwargs.get("title"),
            content=kwargs.get("content"),
            status=kwargs.get("status"),
            artifact_type=kwargs.get("type"),
            version=kwargs.get("version"),
            parent_artifact_id=kwargs.get("parent_artifact_id"),
        )
        if self._dataservice is not None:
            return await self._dataservice.update_workspace_artifact(
                artifact_id,
                command,
            )
        async with dataservice_client() as client:
            return await client.update_workspace_artifact(
                artifact_id,
                command,
            )

    async def delete(self, artifact_id: str) -> bool:
        if self._dataservice is not None:
            return await self._dataservice.delete_workspace_artifact(artifact_id)
        async with dataservice_client() as client:
            return await client.delete_workspace_artifact(artifact_id)

    async def list_by_type(
        self,
        workspace_id: str,
        artifact_type: str,
    ) -> list[WorkspaceArtifactPayload]:
        return await self.list_by_workspace(
            workspace_id=workspace_id,
            type=artifact_type,
        )

    async def get_lineage(self, artifact_id: str) -> list[WorkspaceArtifactPayload]:
        if self._dataservice is not None:
            return await self._dataservice.get_workspace_artifact_lineage(artifact_id)
        async with dataservice_client() as client:
            return await client.get_workspace_artifact_lineage(artifact_id)

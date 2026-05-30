"""Public in-process asset API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.asset.contracts import (
    WorkspaceArtifactCreateCommand,
    WorkspaceArtifactProjection,
    WorkspaceArtifactUpdateCommand,
    WorkspaceAssetCreateCommand,
    WorkspaceAssetDownloadProjection,
    WorkspaceAssetProjection,
    WorkspaceAssetUpdateCommand,
)
from src.dataservice.domains.asset.service import WorkspaceAssetService


class AssetDataService:
    """Workspace asset API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = WorkspaceAssetService(session, autocommit=autocommit)

    async def register_asset(self, command: WorkspaceAssetCreateCommand) -> WorkspaceAssetProjection:
        return await self._domain.register_asset(command)

    async def register_asset_record(
        self,
        *,
        workspace_id: str,
        asset_kind: str,
        name: str,
        storage_path: str,
        storage_backend: str = "local",
        title: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        content_hash: str | None = None,
        parent_asset_id: str | None = None,
        created_by: str = "system",
        source_kind: str | None = None,
        source_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> WorkspaceAssetProjection:
        return await self._domain.register_asset(
            WorkspaceAssetCreateCommand(
                workspace_id=workspace_id,
                asset_kind=asset_kind,
                name=name,
                title=title,
                mime_type=mime_type,
                storage_backend=storage_backend,
                storage_path=storage_path,
                size_bytes=size_bytes,
                content_hash=content_hash,
                parent_asset_id=parent_asset_id,
                created_by=created_by,
                source_kind=source_kind,
                source_id=source_id,
                metadata_json=dict(metadata_json or {}),
            )
        )

    async def get_asset(
        self,
        asset_id: str,
        *,
        include_deleted: bool = False,
    ) -> WorkspaceAssetProjection | None:
        return await self._domain.get_asset(asset_id, include_deleted=include_deleted)

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
        return await self._domain.list_assets(
            workspace_id=workspace_id,
            asset_kind=asset_kind,
            source_kind=source_kind,
            source_id=source_id,
            include_deleted=include_deleted,
            limit=limit,
        )

    async def update_asset(
        self,
        asset_id: str,
        command: WorkspaceAssetUpdateCommand,
    ) -> WorkspaceAssetProjection | None:
        return await self._domain.update_asset(asset_id, command)

    async def mark_deleted(self, asset_id: str) -> WorkspaceAssetProjection | None:
        return await self._domain.mark_deleted(asset_id)

    async def resolve_download(self, asset_id: str) -> WorkspaceAssetDownloadProjection | None:
        return await self._domain.resolve_download(asset_id)

    async def create_workspace_artifact(
        self,
        command: WorkspaceArtifactCreateCommand,
    ) -> WorkspaceArtifactProjection:
        return await self._domain.create_workspace_artifact(command)

    async def get_workspace_artifact(self, artifact_id: str) -> WorkspaceArtifactProjection | None:
        return await self._domain.get_workspace_artifact(artifact_id)

    async def find_latest_workspace_artifact(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> WorkspaceArtifactProjection | None:
        return await self._domain.find_latest_workspace_artifact(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            title=title,
        )

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
    ) -> list[WorkspaceArtifactProjection]:
        return await self._domain.list_workspace_artifacts(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            artifact_types=artifact_types,
            status=status,
            created_by_skill=created_by_skill,
            created_by_skills=created_by_skills,
            limit=limit,
            offset=offset,
        )

    async def count_workspace_artifacts(
        self,
        *,
        workspace_id: str | None = None,
        artifact_type: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
    ) -> int:
        return await self._domain.count_workspace_artifacts(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            created_by_skill=created_by_skill,
            created_by_skills=created_by_skills,
        )

    async def list_workspace_artifact_versions(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> list[WorkspaceArtifactProjection]:
        return await self._domain.list_workspace_artifact_versions(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            title=title,
        )

    async def update_workspace_artifact(
        self,
        artifact_id: str,
        command: WorkspaceArtifactUpdateCommand,
    ) -> WorkspaceArtifactProjection | None:
        return await self._domain.update_workspace_artifact(artifact_id, command)

    async def delete_workspace_artifact(self, artifact_id: str) -> bool:
        return await self._domain.delete_workspace_artifact(artifact_id)

    async def get_workspace_artifact_lineage(
        self,
        artifact_id: str,
    ) -> list[WorkspaceArtifactProjection]:
        return await self._domain.get_workspace_artifact_lineage(artifact_id)

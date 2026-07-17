"""Workspace asset domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.types import ArtifactType
from src.dataservice.domains.asset.contracts import (
    WorkspaceArtifactCreateCommand,
    WorkspaceArtifactProjection,
    WorkspaceArtifactUpdateCommand,
    WorkspaceAssetCreateCommand,
    WorkspaceAssetDownloadProjection,
    WorkspaceAssetProjection,
    WorkspaceAssetUpdateCommand,
)
from src.dataservice.domains.asset.projection import (
    asset_to_download_projection,
    asset_to_projection,
    workspace_artifact_to_projection,
)
from src.dataservice.domains.asset.repository import WorkspaceAssetRepository
from src.dataservice.domains.mission.write_authority import assert_active_mission_write
from src.dataservice.domains.workspace.service import DataServiceWorkspaceService

_ARTIFACT_VERSION_UNIQUE_CONSTRAINT = "uq_artifacts_workspace_type_title_version"
_CREATE_RETRY_LIMIT = 3


class WorkspaceAssetService:
    """DataService-owned workspace asset operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = WorkspaceAssetRepository(session)

    async def register_asset(self, command: WorkspaceAssetCreateCommand) -> WorkspaceAssetProjection:
        mission_review_asset = command.source_kind == "mission_review_item"
        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=command.workspace_id,
            mission_review_item_id=command.source_id if mission_review_asset else None,
            required=mission_review_asset,
        )
        if mission_review_asset:
            if not command.source_id:
                raise ValueError("Mission review assets require source_id")
            await DataServiceWorkspaceService(
                self.session,
                autocommit=False,
            ).lock_workspace_for_update(command.workspace_id)
            existing = await self.repository.list_assets(
                workspace_id=command.workspace_id,
                source_kind=command.source_kind,
                source_id=command.source_id,
                include_deleted=True,
                limit=2,
            )
            if existing:
                record = existing[0]
                if record.deleted_at is not None:
                    raise ValueError("Mission review asset was already deleted")
                expected = (
                    command.asset_kind,
                    command.mime_type,
                    command.storage_path,
                    command.content_hash,
                )
                actual = (
                    record.asset_kind,
                    record.mime_type,
                    record.storage_path,
                    record.content_hash,
                )
                if actual != expected:
                    raise ValueError(
                        "Mission review asset source was reused with different content"
                    )
                return asset_to_projection(record)
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

    async def create_workspace_artifact(
        self,
        command: WorkspaceArtifactCreateCommand,
    ) -> WorkspaceArtifactProjection:
        self._validate_workspace_artifact_type(command.artifact_type)
        max_attempts = _CREATE_RETRY_LIMIT if command.title else 1

        for attempt in range(max_attempts):
            version = 1
            auto_parent_id = None
            if command.title:
                await DataServiceWorkspaceService(
                    self.session,
                    autocommit=False,
                ).lock_workspace_for_update(command.workspace_id)
                existing = await self.repository.find_latest_workspace_artifact(
                    workspace_id=command.workspace_id,
                    artifact_type=command.artifact_type,
                    title=command.title,
                )
                if existing is not None:
                    version = int(existing.version) + 1
                    auto_parent_id = str(existing.id)

            record = self.repository.create_workspace_artifact(
                {
                    "workspace_id": command.workspace_id,
                    "type": command.artifact_type,
                    "title": command.title,
                    "content": dict(command.content or {}),
                    "created_by_skill": command.created_by_skill,
                    "parent_artifact_id": command.parent_artifact_id or auto_parent_id,
                    "status": "draft",
                    "version": version,
                }
            )
            try:
                await self._finish()
            except IntegrityError as exc:
                await self.session.rollback()
                can_retry = (
                    command.title
                    and attempt < max_attempts - 1
                    and self._is_version_uniqueness_conflict(exc)
                )
                if can_retry:
                    continue
                raise
            if self.autocommit:
                await self.session.refresh(record)
            return workspace_artifact_to_projection(record)

        raise RuntimeError("Artifact create retry loop exhausted unexpectedly")

    async def get_workspace_artifact(self, artifact_id: str) -> WorkspaceArtifactProjection | None:
        record = await self.repository.get_workspace_artifact(artifact_id)
        return workspace_artifact_to_projection(record) if record is not None else None

    async def find_latest_workspace_artifact(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> WorkspaceArtifactProjection | None:
        record = await self.repository.find_latest_workspace_artifact(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            title=title,
        )
        return workspace_artifact_to_projection(record) if record is not None else None

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
        return [
            workspace_artifact_to_projection(record)
            for record in await self.repository.list_workspace_artifacts(
                workspace_id=workspace_id,
                artifact_type=artifact_type,
                artifact_types=artifact_types,
                status=status,
                created_by_skill=created_by_skill,
                created_by_skills=created_by_skills,
                limit=limit,
                offset=offset,
            )
        ]

    async def count_workspace_artifacts(
        self,
        *,
        workspace_id: str | None = None,
        artifact_type: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
    ) -> int:
        return await self.repository.count_workspace_artifacts(
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
        return [
            workspace_artifact_to_projection(record)
            for record in await self.repository.list_workspace_artifact_versions(
                workspace_id=workspace_id,
                artifact_type=artifact_type,
                title=title,
            )
        ]

    async def update_workspace_artifact(
        self,
        artifact_id: str,
        command: WorkspaceArtifactUpdateCommand,
    ) -> WorkspaceArtifactProjection | None:
        record = await self.repository.get_workspace_artifact(artifact_id)
        if record is None:
            return None
        if command.artifact_type is not None:
            self._validate_workspace_artifact_type(command.artifact_type)
            record.type = command.artifact_type
        if command.title is not None:
            record.title = command.title
        if command.content is not None:
            record.content = dict(command.content)
        if command.status is not None:
            record.status = command.status
        if command.version is not None:
            record.version = command.version
        if command.parent_artifact_id is not None:
            record.parent_artifact_id = command.parent_artifact_id
        await self._finish()
        if self.autocommit:
            await self.session.refresh(record)
        return workspace_artifact_to_projection(record)

    async def delete_workspace_artifact(self, artifact_id: str) -> bool:
        record = await self.repository.get_workspace_artifact(artifact_id)
        if record is None:
            return False
        await self.repository.delete_workspace_artifact(record)
        await self._finish()
        return True

    async def get_workspace_artifact_lineage(
        self,
        artifact_id: str,
    ) -> list[WorkspaceArtifactProjection]:
        current = await self.repository.get_workspace_artifact(artifact_id)
        if current is None:
            return []

        lineage = []
        while current is not None:
            lineage.append(current)
            if current.parent_artifact_id:
                current = await self.repository.get_workspace_artifact(current.parent_artifact_id)
            else:
                break
        return [workspace_artifact_to_projection(record) for record in reversed(lineage)]

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

    @staticmethod
    def _validate_workspace_artifact_type(artifact_type: str) -> None:
        try:
            ArtifactType(artifact_type)
        except ValueError:
            valid_types = [item.value for item in ArtifactType]
            raise ValueError(
                f"Invalid artifact type: {artifact_type}. Must be one of: {valid_types}"
            ) from None

    @staticmethod
    def _is_version_uniqueness_conflict(error: IntegrityError) -> bool:
        original = getattr(error, "orig", None)
        diag = getattr(original, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)
        if constraint_name == _ARTIFACT_VERSION_UNIQUE_CONSTRAINT:
            return True

        message = f"{error} {original}"
        return _ARTIFACT_VERSION_UNIQUE_CONSTRAINT in message

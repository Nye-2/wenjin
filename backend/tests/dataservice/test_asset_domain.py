"""DataService workspace asset domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from src.database.base import Base
from src.dataservice.domains.asset.contracts import (
    LegacyArtifactCreateCommand,
    LegacyArtifactUpdateCommand,
    WorkspaceAssetCreateCommand,
    WorkspaceAssetUpdateCommand,
)
from src.dataservice.domains.asset.models import WorkspaceAssetRecord
from src.dataservice.domains.asset.review_handler import build_workspace_asset_review_handler
from src.dataservice.domains.asset.service import WorkspaceAssetService
from src.dataservice.domains.review.contracts import ReviewItemProjection


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


def _asset(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = {
        "id": "asset-1",
        "workspace_id": "ws-1",
        "asset_kind": "upload",
        "name": "paper.pdf",
        "title": None,
        "mime_type": "application/pdf",
        "storage_backend": "local",
        "storage_path": "uploads/ws-1/paper.pdf",
        "size_bytes": 1024,
        "content_hash": "sha256:abc",
        "parent_asset_id": None,
        "created_by": "user-1",
        "source_kind": "upload",
        "source_id": "upload-1",
        "metadata_json": {},
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _legacy_artifact(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = {
        "id": "artifact-1",
        "workspace_id": "ws-1",
        "type": "research_idea",
        "title": "Idea",
        "content": {"body": "test"},
        "created_by_skill": None,
        "parent_artifact_id": None,
        "version": 1,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeAssetRepository:
    def __init__(self) -> None:
        self.assets: dict[str, SimpleNamespace] = {}
        self.artifacts: dict[str, SimpleNamespace] = {}

    def create_asset(self, values: dict[str, Any]) -> SimpleNamespace:
        asset_id = f"asset-{len(self.assets) + 1}"
        record = _asset({"id": asset_id, **values})
        self.assets[asset_id] = record
        return record

    async def get_asset(self, asset_id: str) -> SimpleNamespace | None:
        return self.assets.get(asset_id)

    async def list_assets(
        self,
        *,
        workspace_id: str,
        asset_kind: str | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.assets.values() if record.workspace_id == workspace_id]
        if asset_kind is not None:
            records = [record for record in records if record.asset_kind == asset_kind]
        if source_kind is not None:
            records = [record for record in records if record.source_kind == source_kind]
        if source_id is not None:
            records = [record for record in records if record.source_id == source_id]
        if not include_deleted:
            records = [record for record in records if record.deleted_at is None]
        return records[:limit]

    def create_legacy_artifact(self, values: dict[str, Any]) -> SimpleNamespace:
        artifact_id = f"artifact-{len(self.artifacts) + 1}"
        record = _legacy_artifact({"id": artifact_id, **values})
        self.artifacts[artifact_id] = record
        return record

    async def get_legacy_artifact(self, artifact_id: str) -> SimpleNamespace | None:
        return self.artifacts.get(artifact_id)

    async def find_latest_legacy_artifact(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> SimpleNamespace | None:
        matches = [
            record
            for record in self.artifacts.values()
            if record.workspace_id == workspace_id
            and record.type == artifact_type
            and record.title == title
        ]
        return max(matches, key=lambda record: record.version, default=None)

    async def list_legacy_artifacts(
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
    ) -> list[SimpleNamespace]:
        records = [record for record in self.artifacts.values() if record.workspace_id == workspace_id]
        if artifact_type:
            records = [record for record in records if record.type == artifact_type]
        if artifact_types:
            records = [record for record in records if record.type in artifact_types]
        if status:
            records = [record for record in records if record.status == status]
        if created_by_skills:
            records = [record for record in records if record.created_by_skill in created_by_skills]
        elif created_by_skill:
            records = [record for record in records if record.created_by_skill == created_by_skill]
        return records[offset : offset + limit]

    async def count_legacy_artifacts(
        self,
        *,
        workspace_id: str | None = None,
        artifact_type: str | None = None,
        created_by_skill: str | None = None,
        created_by_skills: list[str] | None = None,
    ) -> int:
        records = list(self.artifacts.values())
        if workspace_id is not None:
            records = [record for record in records if record.workspace_id == workspace_id]
        if artifact_type is not None:
            records = [record for record in records if record.type == artifact_type]
        if created_by_skills:
            records = [record for record in records if record.created_by_skill in created_by_skills]
        elif created_by_skill:
            records = [record for record in records if record.created_by_skill == created_by_skill]
        return len(records)

    async def list_legacy_artifact_versions(
        self,
        *,
        workspace_id: str,
        artifact_type: str,
        title: str,
    ) -> list[SimpleNamespace]:
        records = [
            record
            for record in self.artifacts.values()
            if record.workspace_id == workspace_id
            and record.type == artifact_type
            and record.title == title
        ]
        return sorted(records, key=lambda record: record.version, reverse=True)

    async def delete_legacy_artifact(self, artifact: SimpleNamespace) -> None:
        self.artifacts.pop(str(artifact.id), None)


def _service() -> tuple[WorkspaceAssetService, FakeAssetRepository, FakeSession]:
    session = FakeSession()
    service = WorkspaceAssetService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeAssetRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def _command(**overrides: Any) -> WorkspaceAssetCreateCommand:
    values = {
        "workspace_id": "ws-1",
        "asset_kind": "upload",
        "name": "paper.pdf",
        "title": "Paper",
        "mime_type": "application/pdf",
        "storage_backend": "local",
        "storage_path": "uploads/ws-1/paper.pdf",
        "size_bytes": 1024,
        "content_hash": "sha256:abc",
        "created_by": "user-1",
        "source_kind": "upload",
        "source_id": "upload-1",
        "metadata_json": {"page_count": 12},
    }
    values.update(overrides)
    return WorkspaceAssetCreateCommand(**values)


def test_workspace_asset_model_is_registered_on_shared_metadata() -> None:
    assert WorkspaceAssetRecord.__tablename__ in Base.metadata.tables


def test_asset_create_command_requires_storage_pointer() -> None:
    with pytest.raises(ValidationError):
        _command(storage_path="")


@pytest.mark.asyncio
async def test_register_list_update_download_and_delete_asset() -> None:
    service, repository, session = _service()

    created = await service.register_asset(_command())
    listed = await service.list_assets(workspace_id="ws-1", asset_kind="upload")
    updated = await service.update_asset(
        created.id,
        WorkspaceAssetUpdateCommand(title="Updated Paper", metadata_json={"page_count": 13}),
    )
    download = await service.resolve_download(created.id)
    deleted = await service.mark_deleted(created.id)
    active_after_delete = await service.list_assets(workspace_id="ws-1")
    all_after_delete = await service.list_assets(workspace_id="ws-1", include_deleted=True)

    assert created.storage_path == "uploads/ws-1/paper.pdf"
    assert listed[0].id == created.id
    assert updated is not None
    assert updated.title == "Updated Paper"
    assert updated.metadata_json == {"page_count": 13}
    assert download is not None
    assert download.filename == "paper.pdf"
    assert deleted is not None
    assert deleted.deleted_at is not None
    assert active_after_delete == []
    assert all_after_delete[0].id == created.id
    assert repository.assets[created.id].deleted_at is not None
    assert session.commit_count == 3


@pytest.mark.asyncio
async def test_workspace_asset_review_handler_registers_asset_from_review_payload() -> None:
    service, _, _ = _service()
    handler = build_workspace_asset_review_handler(service)
    item = ReviewItemProjection(
        id="review-item-1",
        batch_id="batch-1",
        workspace_id="ws-1",
        item_kind="workspace_asset",
        target_domain="asset",
        target_kind="workspace_asset",
        status="accepted",
        title="Register figure",
        payload_json={
            "asset_kind": "figure",
            "name": "figure-1.png",
            "storage_backend": "local",
            "storage_path": "figures/figure-1.png",
            "mime_type": "image/png",
            "created_by": "agent",
        },
    )

    result = await handler(item)

    assert result == {"asset_id": "asset-1", "storage_path": "figures/figure-1.png"}


@pytest.mark.asyncio
async def test_legacy_artifact_create_increments_version_inside_dataservice() -> None:
    service, repository, session = _service()
    service.autocommit = False
    repository.artifacts["artifact-existing"] = _legacy_artifact(
        {"id": "artifact-existing", "version": 3}
    )

    with patch(
        "src.dataservice.domains.asset.service.DataServiceWorkspaceService"
    ) as workspace_service_cls:
        workspace_service_cls.return_value.lock_workspace_for_update = AsyncMock()
        created = await service.create_legacy_artifact(
            LegacyArtifactCreateCommand(
                workspace_id="ws-1",
                artifact_type="research_idea",
                title="Idea",
                content={"body": "next"},
            )
        )

    assert created.version == 4
    assert created.parent_artifact_id == "artifact-existing"
    assert repository.artifacts[created.id].content == {"body": "next"}
    assert session.flush_count == 1
    workspace_service_cls.return_value.lock_workspace_for_update.assert_awaited_once_with(
        "ws-1"
    )


@pytest.mark.asyncio
async def test_legacy_artifact_list_count_update_delete_and_lineage() -> None:
    service, repository, _ = _service()
    service.autocommit = False
    repository.artifacts["root"] = _legacy_artifact({"id": "root", "title": "Root"})
    repository.artifacts["child"] = _legacy_artifact(
        {"id": "child", "title": "Child", "parent_artifact_id": "root", "version": 2}
    )

    listed = await service.list_legacy_artifacts(workspace_id="ws-1")
    count = await service.count_legacy_artifacts(workspace_id="ws-1")
    versions = await service.list_legacy_artifact_versions(
        workspace_id="ws-1",
        artifact_type="research_idea",
        title="Child",
    )
    lineage = await service.get_legacy_artifact_lineage("child")
    updated = await service.update_legacy_artifact(
        "child",
        command=LegacyArtifactUpdateCommand(title="Updated"),
    )
    deleted = await service.delete_legacy_artifact("child")

    assert [artifact.id for artifact in listed] == ["root", "child"]
    assert count == 2
    assert [artifact.id for artifact in versions] == ["child"]
    assert [artifact.id for artifact in lineage] == ["root", "child"]
    assert updated is not None
    assert updated.title == "Updated"
    assert deleted is True
    assert "child" not in repository.artifacts

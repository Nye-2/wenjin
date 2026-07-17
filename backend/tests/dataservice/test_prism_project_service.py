"""DataService Prism project domain tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.contracts.mission_write_authority import MissionWriteAuthority
from src.contracts.prism_context import prism_selection_hash
from src.contracts.prism_visual_insertion import insert_after_prism_selection
from src.database.base import Base
from src.dataservice.domains.asset.service import WorkspaceAssetService
from src.dataservice.domains.prism.contracts import (
    PrismFileContentUpdateCommand,
    PrismFileRestoreCommand,
    PrismFileVersionCreateCommand,
    PrismPrimaryProjectCommand,
    PrismProtectedScopeUpsertCommand,
    PrismVisualInsertionCommand,
    PrismWorkspaceFileUpsertCommand,
)
from src.dataservice.domains.prism.models import (
    PrismDocumentRecord,
    PrismFileRecord,
    PrismFileVersionRecord,
    PrismProjectRecord,
    PrismProtectedScopeRecord,
    PrismRenderRecord,
)
from src.dataservice.domains.prism.service import PrismDataDomainService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


def _record(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = {"created_at": now, "updated_at": now}
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakePrismRepository:
    def __init__(self) -> None:
        self.projects: dict[str, SimpleNamespace] = {}
        self.documents: dict[str, SimpleNamespace] = {}
        self.files: dict[str, SimpleNamespace] = {}
        self.versions: dict[str, SimpleNamespace] = {}
        self.protected_scopes: dict[str, SimpleNamespace] = {}
        self.locked_files: list[tuple[str, str]] = []

    def create_project(self, values: dict[str, Any]) -> SimpleNamespace:
        project_id = f"project-{len(self.projects) + 1}"
        record = _record({"id": project_id, "trashed_at": None, **values})
        self.projects[project_id] = record
        return record

    def create_document(self, values: dict[str, Any]) -> SimpleNamespace:
        document_id = f"document-{len(self.documents) + 1}"
        record = _record({"id": document_id, "root_file_id": None, **values})
        self.documents[document_id] = record
        return record

    def create_file(self, values: dict[str, Any]) -> SimpleNamespace:
        file_id = f"file-{len(self.files) + 1}"
        record = _record(
            {
                "id": file_id,
                "current_version_id": None,
                "content_hash": None,
                "deleted_at": None,
                **values,
            }
        )
        self.files[file_id] = record
        return record

    def create_file_version(self, values: dict[str, Any]) -> SimpleNamespace:
        version_id = f"version-{len(self.versions) + 1}"
        record = _record({"id": version_id, **values})
        self.versions[version_id] = record
        return record

    def create_protected_scope(self, values: dict[str, Any]) -> SimpleNamespace:
        scope_id = f"protected-{len(self.protected_scopes) + 1}"
        record = _record({"id": scope_id, **values})
        self.protected_scopes[scope_id] = record
        return record

    async def get_primary_project(
        self,
        workspace_id: str,
        *,
        role: str = "primary_manuscript",
    ) -> SimpleNamespace | None:
        for record in self.projects.values():
            if (
                record.workspace_id == workspace_id
                and record.role == role
                and record.status == "active"
                and record.trashed_at is None
            ):
                return record
        return None

    async def get_primary_document(self, project_id: str) -> SimpleNamespace | None:
        for record in self.documents.values():
            if record.project_id == project_id and record.document_kind == "manuscript":
                return record
        return None

    async def lock_document(self, document_id: str) -> None:
        assert document_id in self.documents

    async def get_file_by_path(self, document_id: str, path: str) -> SimpleNamespace | None:
        for record in self.files.values():
            if record.document_id == document_id and record.path == path and record.deleted_at is None:
                return record
        return None

    async def get_file(self, file_id: str) -> SimpleNamespace | None:
        return self.files.get(file_id)

    async def get_file_for_workspace(
        self,
        *,
        workspace_id: str,
        file_id: str,
        project_id: str | None = None,
        for_update: bool = False,
    ) -> SimpleNamespace | None:
        if for_update:
            self.locked_files.append((workspace_id, file_id))
        record = self.files.get(file_id)
        if record is None or record.workspace_id != workspace_id or record.deleted_at is not None:
            return None
        document = self.documents.get(record.document_id)
        project = self.projects.get(document.project_id) if document is not None else None
        if (
            document is None
            or document.workspace_id != workspace_id
            or getattr(document, "status", "active") != "active"
            or project is None
            or project.workspace_id != workspace_id
            or project.role != "primary_manuscript"
            or project.status != "active"
            or project.trashed_at is not None
            or (project_id is not None and project.id != project_id)
        ):
            return None
        return record

    async def get_file_version(self, version_id: str) -> SimpleNamespace | None:
        return self.versions.get(version_id)

    async def get_file_version_by_mission_commit(
        self,
        mission_commit_id: str,
    ) -> SimpleNamespace | None:
        return next(
            (
                record
                for record in self.versions.values()
                if record.mission_commit_id == mission_commit_id
            ),
            None,
        )

    async def get_current_file_version(self, file_record: SimpleNamespace) -> SimpleNamespace | None:
        if not file_record.current_version_id:
            return None
        return self.versions.get(file_record.current_version_id)

    async def get_previous_file_version(
        self,
        *,
        file_id: str,
        before_version_no: int,
    ) -> SimpleNamespace | None:
        candidates = [
            record
            for record in self.versions.values()
            if record.file_id == file_id and record.version_no < before_version_no
        ]
        candidates.sort(key=lambda record: record.version_no, reverse=True)
        return candidates[0] if candidates else None

    def soft_delete_file(self, file_record: SimpleNamespace) -> None:
        file_record.deleted_at = datetime.now(UTC)
        file_record.updated_at = datetime.now(UTC)

    async def get_protected_scope(
        self,
        *,
        project_id: str,
        file_path: str,
        section_key: str,
        scope: str,
    ) -> SimpleNamespace | None:
        for record in self.protected_scopes.values():
            if (
                record.project_id == project_id
                and record.file_path == file_path
                and record.section_key == section_key
                and record.scope == scope
            ):
                return record
        return None

    async def list_documents(self, project_id: str) -> list[SimpleNamespace]:
        return [record for record in self.documents.values() if record.project_id == project_id]

    async def list_files(self, document_id: str) -> list[SimpleNamespace]:
        return [
            record
            for record in self.files.values()
            if record.document_id == document_id and record.deleted_at is None
        ]

    async def list_protected_scopes(
        self,
        project_id: str,
        *,
        limit: int = 200,
    ) -> list[SimpleNamespace]:
        return [
            record
            for record in self.protected_scopes.values()
            if record.project_id == project_id
        ][:limit]

    async def next_file_version_no(self, file_id: str) -> int:
        versions = [record.version_no for record in self.versions.values() if record.file_id == file_id]
        return max(versions, default=0) + 1


def _service() -> tuple[PrismDataDomainService, FakePrismRepository, FakeSession]:
    session = FakeSession()
    service = PrismDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakePrismRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def test_prism_models_are_registered_on_shared_metadata() -> None:
    assert PrismProjectRecord.__tablename__ in Base.metadata.tables
    assert PrismDocumentRecord.__tablename__ in Base.metadata.tables
    assert PrismFileRecord.__tablename__ in Base.metadata.tables
    assert PrismFileVersionRecord.__tablename__ in Base.metadata.tables
    assert PrismRenderRecord.__tablename__ in Base.metadata.tables
    assert PrismProtectedScopeRecord.__tablename__ in Base.metadata.tables


def test_file_version_requires_exactly_one_content_pointer() -> None:
    with pytest.raises(ValidationError):
        PrismFileVersionCreateCommand(
            file_id="file-1",
            content_hash="hash",
            content_inline="content",
            content_asset_id="asset-1",
        )


def test_file_version_allows_empty_inline_content() -> None:
    command = PrismFileVersionCreateCommand(
        file_id="file-1",
        content_hash="sha256:empty",
        content_inline="",
    )

    assert command.content_inline == ""
    assert command.content_asset_id is None


def test_visual_insertion_requires_mission_write_authority() -> None:
    with pytest.raises(ValidationError, match="mission_write_authority"):
        PrismVisualInsertionCommand(
            target_file_id="file-1",
            prism_project_id="project-1",
            expected_current_version_id="version-1",
            expected_current_hash="a" * 64,
            selection_byte_range=(0, 1),
            selection_hash=prism_selection_hash("x"),
            insertion="![Figure](/figure.png)",
            expected_content_hash=f"sha256:{'b' * 64}",
            asset_id="asset-1",
            created_by="user-1",
            source_mission_commit_id="source-commit-1",
        )


@pytest.mark.asyncio
async def test_ensure_primary_project_creates_project_document_and_root_file() -> None:
    service, repository, session = _service()

    surface = await service.ensure_primary_project(
        PrismPrimaryProjectCommand(
            workspace_id="ws-1",
            title="Workspace Manuscript",
            adapter_kind="latex",
            adapter_ref_id="latex-1",
            main_file="main.tex",
            adapter_metadata_json={"latex_project_id": "latex-1"},
        )
    )

    assert surface.project.workspace_id == "ws-1"
    assert surface.project.adapter_ref_id == "latex-1"
    assert surface.project.adapter_metadata_json["main_file"] == "main.tex"
    assert surface.documents[0].root_file_id == "file-1"
    assert surface.files[0].path == "main.tex"
    assert repository.documents["document-1"].root_file_id == "file-1"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_append_file_version_updates_current_file_pointer() -> None:
    service, repository, session = _service()
    surface = await service.ensure_primary_project(
        PrismPrimaryProjectCommand(
            workspace_id="ws-1",
            title="Workspace Manuscript",
            adapter_ref_id="latex-1",
        )
    )
    file_id = surface.files[0].id

    version = await service.append_file_version(
        PrismFileVersionCreateCommand(
            file_id=file_id,
            content_inline="Hello",
            content_hash="hash-1",
            created_by="user-1",
        )
    )

    assert version is not None
    assert version.version_no == 1
    assert repository.files[file_id].current_version_id == version.id
    assert repository.files[file_id].content_hash == "hash-1"
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_upsert_workspace_file_appends_initial_content_and_reads_current_version() -> None:
    service, repository, session = _service()

    write = await service.upsert_workspace_file(
        workspace_id="ws-1",
        command=PrismWorkspaceFileUpsertCommand(
            path="docs/software-copyright/application.md",
            content_inline="# Application",
            content_hash="hash-1",
            created_by="execution:run-1",
        ),
    )

    assert write.changed is True
    assert write.file.path == "docs/software-copyright/application.md"
    assert write.version is not None
    assert write.version.version_no == 1
    content = await service.get_workspace_file_content(
        workspace_id="ws-1",
        file_id=write.file.id,
    )
    assert content is not None
    assert content.current_version is not None
    assert content.current_version.content_inline == "# Application"
    assert repository.files[write.file.id].current_version_id == write.version.id
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_workspace_file_lookup_rejects_cross_project_identity() -> None:
    service, repository, _session = _service()
    surface = await service.ensure_primary_project(
        PrismPrimaryProjectCommand(
            workspace_id="ws-1",
            title="Primary manuscript",
            main_file="paper.md",
        )
    )
    primary_file_id = surface.files[0].id
    secondary_project = repository.create_project(
        {
            "workspace_id": "ws-1",
            "role": "supplementary",
            "title": "Other project",
            "adapter_kind": "workspace_files",
            "adapter_ref_id": None,
            "status": "active",
            "settings_json": {},
            "adapter_metadata_json": {},
        }
    )
    secondary_document = repository.create_document(
        {
            "workspace_id": "ws-1",
            "project_id": secondary_project.id,
            "document_kind": "manuscript",
            "title": "Other document",
            "adapter_kind": "workspace_files",
            "status": "active",
            "metadata_json": {},
        }
    )
    secondary_file = repository.create_file(
        {
            "workspace_id": "ws-1",
            "document_id": secondary_document.id,
            "path": "other.md",
            "file_role": "main",
            "mime_type": "text/markdown",
            "sort_order": 0,
            "metadata_json": {},
        }
    )

    assert (
        await service.get_workspace_file_content(
            workspace_id="ws-1",
            file_id=secondary_file.id,
        )
        is None
    )
    assert (
        await service.get_workspace_file_content(
            workspace_id="ws-1",
            file_id=primary_file_id,
            prism_project_id=secondary_project.id,
        )
        is None
    )
    assert (
        await service.get_workspace_file_content(
            workspace_id="ws-1",
            file_id=primary_file_id,
            prism_project_id=surface.project.id,
        )
        is not None
    )


@pytest.mark.asyncio
async def test_create_only_workspace_file_rejects_existing_path_without_mutation() -> None:
    service, repository, _session = _service()
    initial = await service.upsert_workspace_file(
        workspace_id="ws-1",
        command=PrismWorkspaceFileUpsertCommand(
            path="paper/main.tex",
            file_role="manuscript",
            content_inline="original",
            content_hash="hash-original",
        ),
    )
    conflict = await service.upsert_workspace_file(
        workspace_id="ws-1",
        command=PrismWorkspaceFileUpsertCommand(
            path="paper/main.tex",
            create_only=True,
            file_role="generated",
            metadata_json={"replacement": True},
            content_inline="replacement",
            content_hash="hash-replacement",
        ),
    )

    assert conflict.changed is False
    assert conflict.skipped_reason == "already_exists"
    assert conflict.file.id == initial.file.id
    stored = repository.files[initial.file.id]
    assert stored.file_role == "manuscript"
    assert stored.metadata_json == {}
    assert stored.content_hash == "hash-original"
    assert len(repository.versions) == 1


@pytest.mark.asyncio
async def test_append_file_content_skips_unchanged_hash() -> None:
    service, repository, _session = _service()
    initial = await service.upsert_workspace_file(
        workspace_id="ws-1",
        command=PrismWorkspaceFileUpsertCommand(
            path="paper/main.tex",
            content_inline="hello",
            content_hash="hash-1",
        ),
    )
    repository.locked_files.clear()

    second = await service.append_file_content(
        workspace_id="ws-1",
        file_id=initial.file.id,
        command=PrismFileContentUpdateCommand(
            content_inline="hello",
            content_hash="hash-1",
            created_by="user",
        ),
    )

    assert second.changed is False
    assert second.skipped_reason == "unchanged"
    assert len(repository.versions) == 1
    assert repository.locked_files == [("ws-1", initial.file.id)]


@pytest.mark.asyncio
async def test_visual_insertion_binds_asset_and_manuscript_in_one_commit(monkeypatch) -> None:
    service, repository, session = _service()
    authority_guard = AsyncMock()
    monkeypatch.setattr(
        "src.dataservice.domains.prism.service.assert_active_mission_write",
        authority_guard,
    )
    surface = await service.ensure_primary_project(
        PrismPrimaryProjectCommand(
            workspace_id="ws-1",
            title="Manuscript",
            main_file="paper.md",
        )
    )
    file_id = surface.files[0].id
    original = "# Method\n\nSelected paragraph.\n"
    original_hash = f"sha256:{hashlib.sha256(original.encode()).hexdigest()}"
    original_version = await service.append_file_version(
        PrismFileVersionCreateCommand(
            file_id=file_id,
            content_inline=original,
            content_hash=original_hash,
            created_by="user-1",
        )
    )
    assert original_version is not None
    asset = SimpleNamespace(
        id="asset-1",
        workspace_id="ws-1",
        deleted_at=None,
        source_kind="mission_review_item",
        content_hash="a" * 64,
        mime_type="image/png",
        storage_path="generated_visuals/aa/figure.png",
        metadata_json={"mission_commit_id": "source-commit-1"},
    )
    monkeypatch.setattr(
        WorkspaceAssetService,
        "get_asset",
        AsyncMock(return_value=asset),
    )
    selection = "Selected paragraph."
    start = len(original[: original.index(selection)].encode("utf-8"))
    end = start + len(selection.encode("utf-8"))
    insertion = f"![Figure](/api/workspaces/ws-1/files/{asset.storage_path})"
    next_content = insert_after_prism_selection(
        content=original,
        selection_byte_range=(start, end),
        selection_hash=prism_selection_hash(selection),
        insertion=insertion,
    )
    next_hash = f"sha256:{hashlib.sha256(next_content.encode()).hexdigest()}"
    command = PrismVisualInsertionCommand(
        target_file_id=file_id,
        prism_project_id=surface.project.id,
        expected_current_version_id=original_version.id,
        expected_current_hash=original_hash,
        selection_byte_range=(start, end),
        selection_hash=prism_selection_hash(selection),
        insertion=insertion,
        expected_content_hash=next_hash,
        asset_id=asset.id,
        created_by="user-1",
        mission_write_authority=MissionWriteAuthority(
            mission_id="mission-1",
            mission_review_item_id="review-insertion-1",
            mission_commit_id="insertion-commit-1",
            attempt_token="attempt-token-insertion-1",
        ),
        source_mission_commit_id="source-commit-1",
    )

    result = await service.insert_visual_asset(workspace_id="ws-1", command=command)

    assert result.manuscript.changed is True
    assert result.manuscript.version is not None
    assert result.manuscript.version.mission_commit_id == "insertion-commit-1"
    assert result.asset_file.file.path == f"figures/{'a' * 64}.png"
    assert result.asset_file.version is not None
    assert result.asset_file.version.content_asset_id == "asset-1"
    assert repository.files[file_id].content_hash == next_hash
    authority_guard.assert_awaited()
    assert session.commit_count == 3

    later_content = f"{next_content}\nLater user edit.\n"
    later_hash = f"sha256:{hashlib.sha256(later_content.encode()).hexdigest()}"
    await service.append_file_version(
        PrismFileVersionCreateCommand(
            file_id=file_id,
            content_inline=later_content,
            content_hash=later_hash,
            created_by="user-1",
        )
    )

    replay = await service.insert_visual_asset(workspace_id="ws-1", command=command)
    assert replay.manuscript.changed is False
    assert replay.manuscript.skipped_reason == "already_applied"
    assert replay.manuscript.version is not None
    assert replay.manuscript.version.id == result.manuscript.version.id
    assert replay.manuscript.file.content_hash == later_hash
    assert len(repository.versions) == 4
    assert session.commit_count == 4


@pytest.mark.asyncio
async def test_visual_insertion_rejects_lost_mission_write_authority(monkeypatch) -> None:
    service, _repository, _session = _service()
    monkeypatch.setattr(
        "src.dataservice.domains.prism.service.assert_active_mission_write",
        AsyncMock(side_effect=ValueError("mission_write_authority_lost")),
    )
    command = PrismVisualInsertionCommand(
        target_file_id="file-1",
        prism_project_id="project-1",
        expected_current_version_id="version-1",
        expected_current_hash="sha256:old",
        selection_byte_range=(0, 1),
        selection_hash=prism_selection_hash("x"),
        insertion="![Figure](/figure.png)",
        expected_content_hash=f"sha256:{'a' * 64}",
        asset_id="asset-1",
        created_by="user-1",
        mission_write_authority=MissionWriteAuthority(
            mission_id="mission-1",
            mission_review_item_id="review-1",
            mission_commit_id="commit-1",
            attempt_token="attempt-token-12345",
        ),
        source_mission_commit_id="source-commit-1",
    )

    with pytest.raises(ValueError, match="mission_write_authority_lost"):
        await service.insert_visual_asset(workspace_id="ws-1", command=command)


@pytest.mark.asyncio
async def test_restore_file_version_requires_matching_current_hash() -> None:
    service, _repository, _session = _service()
    initial = await service.upsert_workspace_file(
        workspace_id="ws-1",
        command=PrismWorkspaceFileUpsertCommand(
            path="paper/main.tex",
            content_inline="old",
            content_hash="hash-old",
        ),
    )
    updated = await service.append_file_content(
        workspace_id="ws-1",
        file_id=initial.file.id,
        command=PrismFileContentUpdateCommand(
            content_inline="new",
            content_hash="hash-new",
            created_by="user",
        ),
    )

    skipped = await service.restore_file_version(
        workspace_id="ws-1",
        file_id=initial.file.id,
        command=PrismFileRestoreCommand(
            version_id=initial.version.id if initial.version else "",
            expected_current_hash="other-hash",
        ),
    )
    restored = await service.restore_file_version(
        workspace_id="ws-1",
        file_id=initial.file.id,
        command=PrismFileRestoreCommand(
            version_id=initial.version.id if initial.version else "",
            expected_current_hash=updated.file.content_hash,
        ),
    )

    assert skipped.changed is False
    assert skipped.skipped_reason == "hash_mismatch"
    assert restored.changed is True
    assert restored.file.content_hash == "hash-old"


@pytest.mark.asyncio
async def test_soft_delete_workspace_file_rejects_unsafe_path_and_hash_mismatch() -> None:
    service, repository, _session = _service()
    with pytest.raises(ValueError):
        await service.upsert_workspace_file(
            workspace_id="ws-1",
            command=PrismWorkspaceFileUpsertCommand(path="../memory/workspace.md"),
        )
    write = await service.upsert_workspace_file(
        workspace_id="ws-1",
        command=PrismWorkspaceFileUpsertCommand(
            path="docs/math-modeling/paper-draft.md",
            content_inline="draft",
            content_hash="hash-1",
        ),
    )

    skipped = await service.soft_delete_workspace_file(
        workspace_id="ws-1",
        file_id=write.file.id,
        expected_current_hash="other",
    )
    deleted = await service.soft_delete_workspace_file(
        workspace_id="ws-1",
        file_id=write.file.id,
        expected_current_hash="hash-1",
    )

    assert skipped.changed is False
    assert skipped.skipped_reason == "hash_mismatch"
    assert deleted.changed is True
    assert repository.files[write.file.id].deleted_at is not None


@pytest.mark.asyncio
async def test_upsert_and_list_protected_scope() -> None:
    service, repository, session = _service()
    surface = await service.ensure_primary_project(
        PrismPrimaryProjectCommand(
            workspace_id="ws-1",
            title="Workspace Manuscript",
            adapter_ref_id="latex-1",
        )
    )

    created = await service.upsert_protected_scope(
        PrismProtectedScopeUpsertCommand(
            workspace_id="ws-1",
            project_id=surface.project.id,
            file_path="sections/intro.tex",
            section_key="section:intro",
            scope="section",
            reason="user_protected",
            source="review_reject",
        )
    )
    updated = await service.upsert_protected_scope(
        PrismProtectedScopeUpsertCommand(
            workspace_id="ws-1",
            project_id=surface.project.id,
            file_path="sections/intro.tex",
            section_key="section:intro",
            scope="section",
            reason="manual_override",
            source="manual_edit",
        )
    )
    listed = await service.list_protected_scopes(surface.project.id)

    assert created.id == updated.id
    assert updated.reason == "manual_override"
    assert listed == [updated]
    assert len(repository.protected_scopes) == 1
    assert session.commit_count == 3

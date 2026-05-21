"""DataService Prism project domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from src.database.base import Base
from src.dataservice.domains.prism.contracts import (
    PrismFileVersionCreateCommand,
    PrismPrimaryProjectCommand,
    PrismProtectedScopeUpsertCommand,
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

    async def get_file_by_path(self, document_id: str, path: str) -> SimpleNamespace | None:
        for record in self.files.values():
            if record.document_id == document_id and record.path == path and record.deleted_at is None:
                return record
        return None

    async def get_file(self, file_id: str) -> SimpleNamespace | None:
        return self.files.get(file_id)

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

"""Workspace memory domain tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from src.contracts.mission_write_authority import MissionWriteAuthority
from src.database.base import Base
from src.dataservice.domains.workspace_memory.contracts import (
    WorkspaceMemoryItemCommand,
    WorkspaceMemoryMergeCommand,
    WorkspaceMemoryRewriteCommand,
)
from src.dataservice.domains.workspace_memory.models import (
    WorkspaceMemoryDocumentRecord,
    WorkspaceMemoryRevisionRecord,
)
from src.dataservice.domains.workspace_memory.repository import WorkspaceMemoryRepository
from src.dataservice.domains.workspace_memory.service import (
    WorkspaceMemoryDataDomainService,
    format_workspace_memory_for_prompt,
)


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0
        self._workspace_lock: asyncio.Lock | None = None

    def hold_workspace_lock(self, lock: asyncio.Lock) -> None:
        self._workspace_lock = lock

    async def commit(self) -> None:
        self.commit_count += 1
        if self._workspace_lock is not None:
            self._workspace_lock.release()
            self._workspace_lock = None

    async def flush(self) -> None:
        self.flush_count += 1


def _record(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(created_at=now, updated_at=now, **values)


class FakeWorkspaceMemoryRepository:
    def __init__(self) -> None:
        self.documents: dict[str, SimpleNamespace] = {}
        self.revisions: dict[str, SimpleNamespace] = {}
        self.locked_workspaces: list[str] = []

    async def lock_workspace_for_update(self, workspace_id: str) -> None:
        self.locked_workspaces.append(workspace_id)

    def create_document(self, values: dict[str, Any]) -> SimpleNamespace:
        record_id = f"memory-doc-{len(self.documents) + 1}"
        record = _record(
            {
                "id": record_id,
                "source_mission_id": None,
                "source_mission_commit_id": None,
                "source_thread_id": None,
                **values,
            }
        )
        self.documents[record.workspace_id] = record
        return record

    def create_revision(self, values: dict[str, Any]) -> SimpleNamespace:
        record_id = f"memory-rev-{len(self.revisions) + 1}"
        record = _record({"id": record_id, "source_mission_commit_id": None, **values})
        self.revisions[record_id] = record
        return record

    async def get_document(self, workspace_id: str) -> SimpleNamespace | None:
        return self.documents.get(workspace_id)

    async def get_revision_by_mission_commit(
        self,
        *,
        workspace_id: str,
        mission_commit_id: str,
    ) -> SimpleNamespace | None:
        return next(
            (record for record in self.revisions.values() if record.workspace_id == workspace_id and record.source_mission_commit_id == mission_commit_id),
            None,
        )

    async def list_revisions(self, *, workspace_id: str, limit: int = 20) -> list[SimpleNamespace]:
        records = [record for record in self.revisions.values() if record.workspace_id == workspace_id]
        records.sort(key=lambda record: record.revision, reverse=True)
        return records[:limit]


def _service() -> tuple[WorkspaceMemoryDataDomainService, FakeWorkspaceMemoryRepository, FakeSession]:
    session = FakeSession()
    service = WorkspaceMemoryDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeWorkspaceMemoryRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def test_workspace_memory_models_are_registered_on_shared_metadata() -> None:
    assert WorkspaceMemoryDocumentRecord.__tablename__ in Base.metadata.tables
    assert WorkspaceMemoryRevisionRecord.__tablename__ in Base.metadata.tables


@pytest.mark.asyncio
async def test_workspace_memory_repository_fence_uses_for_update() -> None:
    statements: list[Any] = []

    class CapturingSession:
        async def execute(self, statement: Any) -> None:
            statements.append(statement)

    repository = WorkspaceMemoryRepository(CapturingSession())  # type: ignore[arg-type]
    await repository.lock_workspace_for_update("ws-1")

    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "FROM workspaces" in sql
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_merge_items_creates_one_hidden_markdown_document() -> None:
    service, repository, session = _service()

    command = WorkspaceMemoryMergeCommand(
        workspace_id="ws-1",
        items=[
            WorkspaceMemoryItemCommand(
                category="preference",
                content="用户希望软著材料使用 Java Web 后端设定。",
                confidence=0.9,
            )
        ],
        updated_by="mission:run-1",
        source_mission_id="run-1",
        source_mission_commit_id="commit-1",
        mission_write_authority=MissionWriteAuthority(
            mission_id="run-1",
            mission_review_item_id="review-1",
            mission_commit_id="commit-1",
            attempt_token="attempt-token-memory-1",
        ),
    )
    with patch(
        "src.dataservice.domains.workspace_memory.service.assert_active_mission_write",
        new_callable=AsyncMock,
    ) as authority_guard:
        result = await service.merge_items(command)

    assert result.changed is True
    assert result.document.workspace_id == "ws-1"
    assert "## User Preferences" in result.document.content_markdown
    assert "- 用户希望软著材料使用 Java Web 后端设定。" in result.document.content_markdown
    assert result.document.revision == 2
    assert len(repository.documents) == 1
    assert len(repository.revisions) == 2
    assert session.commit_count == 1
    assert repository.locked_workspaces == ["ws-1"]
    authority_guard.assert_awaited_once()


@pytest.mark.asyncio
async def test_merge_items_skips_duplicate_content() -> None:
    service, repository, _session = _service()
    command = WorkspaceMemoryMergeCommand(
        workspace_id="ws-1",
        items=[
            WorkspaceMemoryItemCommand(
                category="context",
                content="本工作区正在完成数学建模论文。",
                confidence=0.9,
            )
        ],
        updated_by="mission:run-1",
    )

    first = await service.merge_items(command)
    second = await service.merge_items(command)

    assert first.changed is True
    assert second.changed is False
    assert second.skipped_reason == "unchanged"
    assert second.document.revision == 2
    assert len(repository.revisions) == 2


@pytest.mark.asyncio
async def test_rewrite_document_updates_revision_and_prompt_format() -> None:
    service, _repository, _session = _service()
    first = await service.rewrite_document(
        WorkspaceMemoryRewriteCommand(
            workspace_id="ws-1",
            content_markdown="# Workspace Memory\n\n## Project Context\n- 初版",
            updated_by="user",
            update_reason="explicit_correction",
        )
    )
    second = await service.rewrite_document(
        WorkspaceMemoryRewriteCommand(
            workspace_id="ws-1",
            content_markdown="# Workspace Memory\n\n## Project Context\n- 二版",
            updated_by="user",
            update_reason="explicit_correction",
        )
    )

    assert first.changed is True
    assert first.document.revision == 1
    assert second.changed is True
    assert second.document.revision == 2
    prompt = format_workspace_memory_for_prompt(second.document)
    assert prompt.startswith("<workspace_memory>")
    assert "- 二版" in prompt
    assert prompt.endswith("</workspace_memory>")


@pytest.mark.asyncio
async def test_concurrent_memory_merges_preserve_both_updates_and_revision_order() -> None:
    documents: dict[str, SimpleNamespace] = {}
    revisions: dict[str, SimpleNamespace] = {}
    workspace_locks: dict[str, asyncio.Lock] = {}

    class ConcurrentWorkspaceMemoryRepository(FakeWorkspaceMemoryRepository):
        def __init__(self, session: FakeSession) -> None:
            super().__init__()
            self.documents = documents
            self.revisions = revisions
            self.session = session

        async def lock_workspace_for_update(self, workspace_id: str) -> None:
            lock = workspace_locks.setdefault(workspace_id, asyncio.Lock())
            await lock.acquire()
            self.session.hold_workspace_lock(lock)

        async def get_document(self, workspace_id: str) -> SimpleNamespace | None:
            await asyncio.sleep(0)
            return await super().get_document(workspace_id)

    services: list[WorkspaceMemoryDataDomainService] = []
    for _index in range(2):
        session = FakeSession()
        service = WorkspaceMemoryDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
        service.repository = ConcurrentWorkspaceMemoryRepository(session)  # type: ignore[assignment]
        services.append(service)

    await asyncio.gather(
        services[0].merge_items(
            WorkspaceMemoryMergeCommand(
                workspace_id="ws-1",
                items=[
                    WorkspaceMemoryItemCommand(
                        category="context",
                        content="使用公开数据集。",
                    )
                ],
                updated_by="worker-a",
            )
        ),
        services[1].merge_items(
            WorkspaceMemoryMergeCommand(
                workspace_id="ws-1",
                items=[
                    WorkspaceMemoryItemCommand(
                        category="constraint",
                        content="结果必须可复现。",
                    )
                ],
                updated_by="worker-b",
            )
        ),
    )

    document = documents["ws-1"]
    assert "- 使用公开数据集。" in document.content_markdown
    assert "- 结果必须可复现。" in document.content_markdown
    assert document.revision == 3
    assert sorted(revision.revision for revision in revisions.values()) == [1, 2, 3]

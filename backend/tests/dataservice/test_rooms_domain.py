"""DataService rooms aggregate tests."""

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
from src.dataservice.domains.rooms.contracts import (
    DecisionSetCommand,
    WorkspaceTaskCreateCommand,
)
from src.dataservice.domains.rooms.models import DecisionRecord, WorkspaceTaskRecord
from src.dataservice.domains.rooms.repository import RoomsRepository
from src.dataservice.domains.rooms.service import RoomsDataDomainService


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
    defaults = {"created_at": now, "updated_at": now, "deleted_at": None}
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeRoomsRepository:
    def __init__(self) -> None:
        self.decisions: dict[str, SimpleNamespace] = {}
        self.tasks: dict[str, SimpleNamespace] = {}
        self.locked_workspaces: list[str] = []

    async def lock_workspace_for_update(self, workspace_id: str) -> None:
        self.locked_workspaces.append(workspace_id)

    async def get_active_decision(self, *, workspace_id: str, key: str) -> SimpleNamespace | None:
        for record in self.decisions.values():
            if record.workspace_id == workspace_id and record.key == key and record.deleted_at is None and record.superseded_by is None:
                return record
        return None

    async def get_decision_by_mission_commit(
        self,
        *,
        workspace_id: str,
        source_mission_commit_id: str,
    ) -> SimpleNamespace | None:
        for record in self.decisions.values():
            if record.workspace_id == workspace_id and record.source_mission_commit_id == source_mission_commit_id and record.deleted_at is None:
                return record
        return None

    def create_decision(self, values: dict[str, Any]) -> SimpleNamespace:
        decision_id = f"decision-{len(self.decisions) + 1}"
        record = _record(
            {
                "id": decision_id,
                "source_message_id": None,
                "superseded_by": None,
                "source_mission_id": None,
                "source_mission_item_seq": None,
                "source_mission_commit_id": None,
                **values,
            }
        )
        self.decisions[decision_id] = record
        return record

    async def list_active_decisions(self, workspace_id: str) -> list[SimpleNamespace]:
        return [record for record in self.decisions.values() if record.workspace_id == workspace_id and record.deleted_at is None and record.superseded_by is None]

    async def get_decision_by_id(self, decision_id: str) -> SimpleNamespace | None:
        return self.decisions.get(decision_id)

    async def get_decision(self, *, workspace_id: str, decision_id: str) -> SimpleNamespace | None:
        record = self.decisions.get(decision_id)
        return record if record and record.workspace_id == workspace_id else None

    def create_workspace_task(self, values: dict[str, Any]) -> SimpleNamespace:
        task_id = f"task-{len(self.tasks) + 1}"
        record = _record(
            {
                "id": task_id,
                "completed_at": None,
                "source_mission_id": None,
                "source_mission_item_seq": None,
                "source_mission_commit_id": None,
                **values,
            }
        )
        self.tasks[task_id] = record
        return record

    async def get_workspace_task_by_mission_commit(
        self,
        *,
        workspace_id: str,
        source_mission_commit_id: str,
    ) -> SimpleNamespace | None:
        for record in self.tasks.values():
            if record.workspace_id == workspace_id and record.source_mission_commit_id == source_mission_commit_id and record.deleted_at is None:
                return record
        return None

    async def list_workspace_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.tasks.values() if record.workspace_id == workspace_id]
        if status is not None:
            records = [record for record in records if record.status == status]
        return records

    async def get_workspace_task(self, *, workspace_id: str, task_id: str) -> SimpleNamespace | None:
        record = self.tasks.get(task_id)
        return record if record and record.workspace_id == workspace_id else None


def _service() -> tuple[RoomsDataDomainService, FakeRoomsRepository, FakeSession]:
    session = FakeSession()
    service = RoomsDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeRoomsRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def test_room_models_are_registered_on_shared_metadata() -> None:
    assert DecisionRecord.__tablename__ in Base.metadata.tables
    assert WorkspaceTaskRecord.__tablename__ in Base.metadata.tables


def test_decision_model_has_one_active_value_constraint() -> None:
    index = next(index for index in DecisionRecord.__table__.indexes if index.name == "uq_decisions_active_workspace_key")

    assert index.unique is True
    assert tuple(column.name for column in index.columns) == ("workspace_id", "key")
    assert str(index.dialect_options["postgresql"]["where"]) == ("deleted_at IS NULL AND superseded_by IS NULL")
    assert str(index.dialect_options["sqlite"]["where"]) == ("deleted_at IS NULL AND superseded_by IS NULL")


@pytest.mark.asyncio
async def test_rooms_repository_workspace_fence_uses_for_update() -> None:
    statements: list[Any] = []

    class CapturingSession:
        async def execute(self, statement: Any) -> None:
            statements.append(statement)

    repository = RoomsRepository(CapturingSession())  # type: ignore[arg-type]
    await repository.lock_workspace_for_update("ws-1")

    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "FROM workspaces" in sql
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_decision_set_supersedes_previous_active_value() -> None:
    service, repository, session = _service()

    old = await service.set_decision(DecisionSetCommand(workspace_id="ws-1", key="citation_style", value="MLA", extracted_by="user"))
    new = await service.set_decision(DecisionSetCommand(workspace_id="ws-1", key="citation_style", value="APA", extracted_by="user"))
    active = await service.list_active_decisions("ws-1")

    assert repository.decisions[old.id].superseded_by == new.id
    assert len(active) == 1
    assert active[0].id == new.id
    assert active[0].workspace_id == "ws-1"
    assert active[0].key == "citation_style"
    assert active[0].value == "APA"
    assert active[0].confidence == 1.0
    assert active[0].extracted_by == "user"
    assert active[0].created_at == new.created_at
    assert session.commit_count == 2
    assert session.flush_count == 2
    assert repository.locked_workspaces == ["ws-1", "ws-1"]


@pytest.mark.asyncio
async def test_concurrent_decision_sets_leave_exactly_one_active_value() -> None:
    decisions: dict[str, SimpleNamespace] = {}
    workspace_locks: dict[str, asyncio.Lock] = {}

    class ConcurrentRoomsRepository(FakeRoomsRepository):
        def __init__(self, session: FakeSession) -> None:
            super().__init__()
            self.decisions = decisions
            self.session = session

        async def lock_workspace_for_update(self, workspace_id: str) -> None:
            lock = workspace_locks.setdefault(workspace_id, asyncio.Lock())
            await lock.acquire()
            self.session.hold_workspace_lock(lock)

        async def get_active_decision(
            self,
            *,
            workspace_id: str,
            key: str,
        ) -> SimpleNamespace | None:
            await asyncio.sleep(0)
            return await super().get_active_decision(workspace_id=workspace_id, key=key)

    services: list[RoomsDataDomainService] = []
    for _index in range(2):
        session = FakeSession()
        service = RoomsDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
        service.repository = ConcurrentRoomsRepository(session)  # type: ignore[assignment]
        services.append(service)

    results = await asyncio.gather(
        services[0].set_decision(
            DecisionSetCommand(
                workspace_id="ws-1",
                key="citation_style",
                value="APA",
                extracted_by="user-a",
            )
        ),
        services[1].set_decision(
            DecisionSetCommand(
                workspace_id="ws-1",
                key="citation_style",
                value="Chicago",
                extracted_by="user-b",
            )
        ),
    )

    active = [record for record in decisions.values() if record.deleted_at is None and record.superseded_by is None]
    assert len(decisions) == 2
    assert len(active) == 1
    assert active[0].id in {result.id for result in results}
    assert sum(record.superseded_by is not None for record in decisions.values()) == 1


@pytest.mark.asyncio
async def test_task_create_with_mission_commit_trace() -> None:
    service, _, _ = _service()

    command = WorkspaceTaskCreateCommand(
        workspace_id="ws-1",
        title="Check appendix",
        created_by="user",
        source_mission_id="mission-1",
        source_mission_item_seq=7,
        source_mission_commit_id="commit-1",
        mission_write_authority=MissionWriteAuthority(
            mission_id="mission-1",
            mission_review_item_id="review-1",
            mission_commit_id="commit-1",
            attempt_token="attempt-token-task-1",
        ),
    )
    with patch(
        "src.dataservice.domains.rooms.service.assert_active_mission_write",
        new_callable=AsyncMock,
    ) as authority_guard:
        task = await service.create_workspace_task(command)

    assert task.source_mission_commit_id == "commit-1"
    authority_guard.assert_awaited_once()


@pytest.mark.asyncio
async def test_decision_set_replays_mission_commit_provenance_key() -> None:
    service, repository, session = _service()
    authority = MissionWriteAuthority(
        mission_id="mission-1",
        mission_review_item_id="review-1",
        mission_commit_id="commit-1",
        attempt_token="attempt-token-decision-1",
    )
    command = DecisionSetCommand(
        workspace_id="ws-1",
        key="method",
        value="DID",
        extracted_by="mission:mission-1:commit:commit-1",
        source_mission_id="mission-1",
        source_mission_commit_id="commit-1",
        mission_write_authority=authority,
    )
    with patch(
        "src.dataservice.domains.rooms.service.assert_active_mission_write",
        new_callable=AsyncMock,
    ):
        first = await service.set_decision(command)
        replay = await service.set_decision(command)

    assert replay.id == first.id
    assert len(repository.decisions) == 1
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_workspace_task_create_replays_mission_commit_provenance_key() -> None:
    service, repository, session = _service()
    authority = MissionWriteAuthority(
        mission_id="mission-1",
        mission_review_item_id="review-1",
        mission_commit_id="commit-1",
        attempt_token="attempt-token-task-replay-1",
    )
    command = WorkspaceTaskCreateCommand(
        workspace_id="ws-1",
        title="Verify dataset",
        created_by="mission:mission-1:commit:commit-1",
        source_mission_id="mission-1",
        source_mission_commit_id="commit-1",
        mission_write_authority=authority,
    )
    with patch(
        "src.dataservice.domains.rooms.service.assert_active_mission_write",
        new_callable=AsyncMock,
    ):
        first = await service.create_workspace_task(command)
        replay = await service.create_workspace_task(command)

    assert replay.id == first.id
    assert len(repository.tasks) == 1
    assert session.commit_count == 1

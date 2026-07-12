"""DataService rooms aggregate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.base import Base
from src.dataservice.domains.rooms.contracts import (
    DecisionSetCommand,
    WorkspaceTaskCreateCommand,
)
from src.dataservice.domains.rooms.models import DecisionRecord, WorkspaceTaskRecord
from src.dataservice.domains.rooms.service import RoomsDataDomainService


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
    defaults = {"created_at": now, "updated_at": now, "deleted_at": None}
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeRoomsRepository:
    def __init__(self) -> None:
        self.decisions: dict[str, SimpleNamespace] = {}
        self.tasks: dict[str, SimpleNamespace] = {}

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

    async def get_decision_by_extracted_by(
        self,
        *,
        workspace_id: str,
        key: str,
        extracted_by: str,
    ) -> SimpleNamespace | None:
        for record in self.decisions.values():
            if record.workspace_id == workspace_id and record.key == key and record.extracted_by == extracted_by and record.deleted_at is None:
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

    async def get_workspace_task_by_created_by(
        self,
        *,
        workspace_id: str,
        title: str,
        created_by: str,
    ) -> SimpleNamespace | None:
        for record in self.tasks.values():
            if record.workspace_id == workspace_id and record.title == title and record.created_by == created_by and record.deleted_at is None:
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


@pytest.mark.asyncio
async def test_task_create_with_mission_commit_trace() -> None:
    service, _, _ = _service()

    task = await service.create_workspace_task(
        WorkspaceTaskCreateCommand(
            workspace_id="ws-1",
            title="Check appendix",
            created_by="user",
            source_mission_id="mission-1",
            source_mission_item_seq=7,
            source_mission_commit_id="commit-1",
        )
    )

    assert task.source_mission_commit_id == "commit-1"


@pytest.mark.asyncio
async def test_decision_set_replays_mission_commit_provenance_key() -> None:
    service, repository, session = _service()

    first = await service.set_decision(
        DecisionSetCommand(
            workspace_id="ws-1",
            key="method",
            value="DID",
            extracted_by="mission:mission-1:commit:commit-1",
        )
    )
    replay = await service.set_decision(
        DecisionSetCommand(
            workspace_id="ws-1",
            key="method",
            value="DID",
            extracted_by="mission:mission-1:commit:commit-1",
        )
    )

    assert replay.id == first.id
    assert len(repository.decisions) == 1
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_workspace_task_create_replays_mission_commit_provenance_key() -> None:
    service, repository, session = _service()

    first = await service.create_workspace_task(
        WorkspaceTaskCreateCommand(
            workspace_id="ws-1",
            title="Verify dataset",
            created_by="mission:mission-1:commit:commit-1",
        )
    )
    replay = await service.create_workspace_task(
        WorkspaceTaskCreateCommand(
            workspace_id="ws-1",
            title="Verify dataset",
            created_by="mission:mission-1:commit:commit-1",
        )
    )

    assert replay.id == first.id
    assert len(repository.tasks) == 1
    assert session.commit_count == 1

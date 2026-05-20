"""DataService rooms aggregate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.base import Base
from src.dataservice.domains.review.contracts import ReviewItemProjection
from src.dataservice.domains.rooms.contracts import (
    DecisionSetCommand,
    MemoryFactCreateCommand,
    WorkspaceTaskCreateCommand,
)
from src.dataservice.domains.rooms.models import DecisionRecord, MemoryFactRecord, WorkspaceTaskRecord
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
        self.memory: dict[str, SimpleNamespace] = {}
        self.tasks: dict[str, SimpleNamespace] = {}

    async def get_active_decision(self, *, workspace_id: str, key: str) -> SimpleNamespace | None:
        for record in self.decisions.values():
            if (
                record.workspace_id == workspace_id
                and record.key == key
                and record.deleted_at is None
                and record.superseded_by is None
            ):
                return record
        return None

    def create_decision(self, values: dict[str, Any]) -> SimpleNamespace:
        decision_id = f"decision-{len(self.decisions) + 1}"
        record = _record(
            {
                "id": decision_id,
                "source_message_id": None,
                "superseded_by": None,
                "source_review_batch_id": None,
                "source_review_item_id": None,
                **values,
            }
        )
        self.decisions[decision_id] = record
        return record

    async def list_active_decisions(self, workspace_id: str) -> list[SimpleNamespace]:
        return [
            record
            for record in self.decisions.values()
            if record.workspace_id == workspace_id and record.deleted_at is None and record.superseded_by is None
        ]

    async def get_decision_by_id(self, decision_id: str) -> SimpleNamespace | None:
        return self.decisions.get(decision_id)

    async def get_decision(self, *, workspace_id: str, decision_id: str) -> SimpleNamespace | None:
        record = self.decisions.get(decision_id)
        return record if record and record.workspace_id == workspace_id else None

    def create_memory_fact(self, values: dict[str, Any]) -> SimpleNamespace:
        fact_id = f"memory-{len(self.memory) + 1}"
        record = _record(
            {
                "id": fact_id,
                "last_referenced_at": None,
                "reference_count": 0,
                "source_review_batch_id": None,
                "source_review_item_id": None,
                **values,
            }
        )
        self.memory[fact_id] = record
        return record

    async def list_memory_facts(
        self,
        *,
        workspace_id: str,
        limit: int = 15,
        category: str | None = None,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.memory.values() if record.workspace_id == workspace_id]
        if category is not None:
            records = [record for record in records if record.category == category]
        return records[:limit]

    async def get_memory_fact(self, fact_id: str) -> SimpleNamespace | None:
        return self.memory.get(fact_id)

    def create_workspace_task(self, values: dict[str, Any]) -> SimpleNamespace:
        task_id = f"task-{len(self.tasks) + 1}"
        record = _record(
            {
                "id": task_id,
                "completed_at": None,
                "source_review_batch_id": None,
                "source_review_item_id": None,
                **values,
            }
        )
        self.tasks[task_id] = record
        return record

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
    assert MemoryFactRecord.__tablename__ in Base.metadata.tables
    assert WorkspaceTaskRecord.__tablename__ in Base.metadata.tables


@pytest.mark.asyncio
async def test_decision_set_supersedes_previous_active_value() -> None:
    service, repository, session = _service()

    old = await service.set_decision(
        DecisionSetCommand(workspace_id="ws-1", key="citation_style", value="MLA", extracted_by="user")
    )
    new = await service.set_decision(
        DecisionSetCommand(workspace_id="ws-1", key="citation_style", value="APA", extracted_by="user")
    )
    active = await service.list_active_decisions("ws-1")

    assert repository.decisions[old.id].superseded_by == new.id
    assert active == {"citation_style": "APA"}
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_memory_and_task_create_with_review_trace() -> None:
    service, _, _ = _service()

    facts = await service.add_memory_facts(
        [
            MemoryFactCreateCommand(
                workspace_id="ws-1",
                category="research",
                content="Use fixed effects.",
                source_review_batch_id="batch-1",
                source_review_item_id="item-1",
            )
        ]
    )
    task = await service.create_workspace_task(
        WorkspaceTaskCreateCommand(
            workspace_id="ws-1",
            title="Check appendix",
            created_by="user",
            source_review_batch_id="batch-1",
            source_review_item_id="item-2",
        )
    )

    assert facts[0].source_review_item_id == "item-1"
    assert task.source_review_item_id == "item-2"


@pytest.mark.asyncio
async def test_apply_review_item_materializes_room_payload() -> None:
    service, repository, _ = _service()

    result = await service.apply_review_item(
        ReviewItemProjection(
            id="review-item-1",
            batch_id="review-batch-1",
            workspace_id="ws-1",
            item_kind="room_write",
            target_domain="rooms",
            target_kind="decision",
            status="accepted",
            title="Decision",
            payload_json={"key": "method", "value": "DID", "confidence": 0.8},
        )
    )

    assert result["room"] == "decisions"
    assert repository.decisions[result["record_id"]].source_review_batch_id == "review-batch-1"
    assert repository.decisions[result["record_id"]].source_review_item_id == "review-item-1"

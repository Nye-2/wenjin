"""DataService execution domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.execution.contracts import (
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionUpdateCommand,
)
from src.dataservice.domains.execution.service import DataServiceExecutionService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


def _execution(values: dict[str, Any]) -> SimpleNamespace:
    now = values.get("created_at") or datetime.now(UTC)
    defaults = {
        "id": "exec-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "thread_id": None,
        "execution_type": "feature",
        "feature_id": None,
        "entry_skill_id": None,
        "workspace_type": None,
        "display_name": None,
        "status": "pending",
        "params": {},
        "result": None,
        "error": None,
        "result_summary": None,
        "graph_structure": None,
        "node_states": {},
        "runtime_state": None,
        "progress": 0,
        "message": None,
        "artifact_ids": [],
        "next_actions": [],
        "advisory_code": None,
        "last_error": None,
        "parent_execution_id": None,
        "child_execution_ids": [],
        "dispatch_mode": None,
        "worker_task_id": None,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "updated_at": now,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeExecutionRepository:
    def __init__(self) -> None:
        self.record: SimpleNamespace | None = None
        self.events: list[SimpleNamespace] = []

    def create_execution(self, values: dict[str, Any]) -> SimpleNamespace:
        self.record = _execution({"id": "exec-created", **values})
        return self.record

    async def get_execution(self, execution_id: str) -> SimpleNamespace | None:
        if self.record is not None and self.record.id == execution_id:
            return self.record
        return None

    async def list_executions(self, **kwargs: Any) -> list[SimpleNamespace]:
        _ = kwargs
        return [self.record] if self.record is not None else []

    async def append_event(
        self,
        *,
        execution_id: str,
        workspace_id: str | None,
        node_id: str | None,
        event_type: str,
        payload_json: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> SimpleNamespace:
        event = SimpleNamespace(
            id=f"event-{len(self.events) + 1}",
            execution_id=execution_id,
            workspace_id=workspace_id,
            node_id=node_id,
            event_type=event_type,
            sequence_index=len(self.events) + 1,
            payload_json=payload_json,
            occurred_at=occurred_at or datetime.now(UTC),
            created_at=None,
            updated_at=None,
        )
        self.events.append(event)
        return event

    async def list_nodes(self, execution_id: str) -> list:
        _ = execution_id
        return []

    async def list_events(self, execution_id: str) -> list[SimpleNamespace]:
        return [event for event in self.events if event.execution_id == execution_id]


def _service() -> tuple[DataServiceExecutionService, FakeExecutionRepository, FakeSession]:
    session = FakeSession()
    service = DataServiceExecutionService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeExecutionRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


@pytest.mark.asyncio
async def test_create_execution_projects_v2_field_names() -> None:
    service, repository, session = _service()

    record = await service.create_execution(
        ExecutionCreateCommand(
            execution_type="feature",
            user_id="user-1",
            workspace_id="ws-1",
            capability_id="idea_to_thesis_manuscript",
            task_brief_json={"brief": {"topic": "agents"}},
            display_name="从想法到全文",
        )
    )

    assert record.id == "exec-created"
    assert record.capability_id == "idea_to_thesis_manuscript"
    assert record.task_brief_json == {"brief": {"topic": "agents"}}
    assert repository.record is not None
    assert repository.record.feature_id == "idea_to_thesis_manuscript"
    assert repository.record.params == {"brief": {"topic": "agents"}}
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_update_execution_maps_v2_fields_to_storage_fields() -> None:
    service, repository, session = _service()
    repository.record = _execution({"id": "exec-1", "feature_id": "old", "params": {}})

    updated = await service.update_execution(
        "exec-1",
        ExecutionUpdateCommand(
            status="running",
            task_brief_json={"brief": {"topic": "new"}},
            graph_json={"nodes": []},
            runtime_state_json={"phase": "draft"},
        ),
    )

    assert updated is not None
    assert updated.status == "running"
    assert updated.task_brief_json == {"brief": {"topic": "new"}}
    assert repository.record.params == {"brief": {"topic": "new"}}
    assert repository.record.graph_structure == {"nodes": []}
    assert repository.record.runtime_state == {"phase": "draft"}
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_append_execution_events_are_ordered() -> None:
    service, _, session = _service()

    first = await service.append_event(
        "exec-1",
        ExecutionEventCreateCommand(
            event_type="execution.status",
            workspace_id="ws-1",
            payload_json={"status": "running"},
        ),
    )
    second = await service.append_event(
        "exec-1",
        ExecutionEventCreateCommand(
            event_type="node.completed",
            workspace_id="ws-1",
            node_id="node-1",
            payload_json={"status": "completed"},
        ),
    )

    assert first.sequence_index == 1
    assert second.sequence_index == 2
    assert second.node_id == "node-1"
    assert session.commit_count == 2

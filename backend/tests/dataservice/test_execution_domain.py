"""DataService execution domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.execution.contracts import (
    ComputeSessionEnsureCommand,
    ComputeSessionUpdateCommand,
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionNodePatchCommand,
    ExecutionNodeUpsertCommand,
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


def _compute_session(values: dict[str, Any]) -> SimpleNamespace:
    now = values.get("created_at") or datetime.now(UTC)
    defaults = {
        "id": "compute-1",
        "execution_id": "exec-1",
        "workspace_id": "ws-1",
        "user_id": "user-1",
        "sandbox_session_id": None,
        "active_view": "overview",
        "ui_state": {},
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _node(values: dict[str, Any]) -> SimpleNamespace:
    now = values.get("created_at") or datetime.now(UTC)
    defaults = {
        "id": "node-row-1",
        "execution_id": "exec-1",
        "parent_node_id": None,
        "node_id": "node-1",
        "node_type": "agent",
        "label": None,
        "status": "pending",
        "input_data": None,
        "output_data": None,
        "thinking": None,
        "tool_calls": None,
        "token_usage": None,
        "node_metadata": None,
        "started_at": None,
        "completed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeExecutionRepository:
    def __init__(self) -> None:
        self.record: SimpleNamespace | None = None
        self.events: list[SimpleNamespace] = []
        self.compute_session: SimpleNamespace | None = None
        self.nodes: list[SimpleNamespace] = []

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

    async def list_executions_by_status(self, statuses: list[str]) -> list[SimpleNamespace]:
        if self.record is None or self.record.status not in statuses:
            return []
        return [self.record]

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

    async def list_nodes(self, execution_id: str) -> list[SimpleNamespace]:
        return [node for node in self.nodes if node.execution_id == execution_id]

    async def list_nodes_by_execution_ids(self, execution_ids: list[str]) -> list[SimpleNamespace]:
        return [node for node in self.nodes if node.execution_id in execution_ids]

    async def get_node_by_node_id(
        self,
        *,
        execution_id: str,
        node_id: str,
    ) -> SimpleNamespace | None:
        for node in self.nodes:
            if node.execution_id == execution_id and node.node_id == node_id:
                return node
        return None

    async def get_node_by_record_id(self, node_record_id: str) -> SimpleNamespace | None:
        for node in self.nodes:
            if node.id == node_record_id:
                return node
        return None

    def create_node(self, values: dict[str, Any]) -> SimpleNamespace:
        node = _node({"id": f"node-row-{len(self.nodes) + 1}", **values})
        self.nodes.append(node)
        return node

    async def list_events(self, execution_id: str) -> list[SimpleNamespace]:
        return [event for event in self.events if event.execution_id == execution_id]

    def create_compute_session(self, values: dict[str, Any]) -> SimpleNamespace:
        self.compute_session = _compute_session({"id": "compute-created", **values})
        return self.compute_session

    async def get_compute_session(self, compute_session_id: str) -> SimpleNamespace | None:
        if self.compute_session is not None and self.compute_session.id == compute_session_id:
            return self.compute_session
        return None

    async def get_compute_session_by_execution(self, execution_id: str) -> SimpleNamespace | None:
        if self.compute_session is not None and self.compute_session.execution_id == execution_id:
            return self.compute_session
        return None

    async def list_compute_sessions(self, **kwargs: Any) -> list[SimpleNamespace]:
        _ = kwargs
        return [self.compute_session] if self.compute_session is not None else []


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
async def test_reconcile_interrupted_executions_marks_in_flight_terminal() -> None:
    service, repository, session = _service()
    repository.record = _execution({"id": "exec-1", "status": "running"})

    reconciled = await service.reconcile_interrupted_executions()

    assert reconciled == 1
    assert repository.record.status == "failed"
    assert repository.record.error == "Execution interrupted by process restart"
    assert repository.record.completed_at is not None
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_upsert_and_patch_node_project_lifecycle_snapshot() -> None:
    service, repository, session = _service()

    created = await service.upsert_node(
        "exec-1",
        ExecutionNodeUpsertCommand(
            node_id="node-1",
            node_type="agent",
            label="Draft",
            status="running",
            input_data={"topic": "agents"},
        ),
    )
    patched = await service.update_node(
        created.id,
        ExecutionNodePatchCommand(
            status="completed",
            output_data={"summary": "done"},
            token_usage={"total": 42},
        ),
    )

    assert created.id == "node-row-1"
    assert patched is not None
    assert patched.status == "completed"
    assert patched.output_data == {"summary": "done"}
    assert repository.nodes[0].token_usage == {"total": 42}
    assert session.commit_count == 2


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


@pytest.mark.asyncio
async def test_ensure_compute_session_creates_projection() -> None:
    service, repository, session = _service()

    projection, changed = await service.ensure_compute_session(
        ComputeSessionEnsureCommand(
            execution_id="exec-1",
            workspace_id="ws-1",
            user_id="user-1",
            sandbox_session_id="sandbox-1",
        )
    )

    assert changed is True
    assert projection.id == "compute-created"
    assert projection.sandbox_session_id == "sandbox-1"
    assert repository.compute_session is not None
    assert repository.compute_session.active_view == "overview"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_update_compute_session_merges_ui_state_delta() -> None:
    service, repository, session = _service()
    repository.compute_session = _compute_session(
        {"id": "compute-1", "ui_state": {"selected": "overview"}}
    )

    projection = await service.update_compute_session(
        "compute-1",
        ComputeSessionUpdateCommand(
            active_view="files",
            ui_state_delta={"panel": "artifacts"},
        ),
    )

    assert projection is not None
    assert projection.active_view == "files"
    assert projection.ui_state == {"selected": "overview", "panel": "artifacts"}
    assert session.commit_count == 1

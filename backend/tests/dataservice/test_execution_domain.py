"""DataService execution domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.execution.contracts import (
    ComputeSessionEnsureCommand,
    ComputeSessionUpdateCommand,
    ExecutionCommitClaimCommand,
    ExecutionCommitFailCommand,
    ExecutionCommitFinalizeCommand,
    ExecutionCommitResetCommand,
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionNodePatchCommand,
    ExecutionNodeUpsertCommand,
    ExecutionUpdateCommand,
    GenerationRecordCreateCommand,
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


def _generation(values: dict[str, Any]) -> SimpleNamespace:
    now = values.get("created_at") or datetime.now(UTC)
    defaults = {
        "id": "generation-1",
        "workspace_id": "ws-1",
        "thread_id": None,
        "skill_name": "idea_to_manuscript",
        "model_name": None,
        "input_summary": None,
        "output_summary": None,
        "duration_ms": None,
        "token_usage": None,
        "status": "success",
        "error_message": None,
        "extra_data": {},
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
        self.generation_records: list[SimpleNamespace] = []
        self.locked_execution_ids: list[str] = []

    def create_execution(self, values: dict[str, Any]) -> SimpleNamespace:
        self.record = _execution({"id": "exec-created", **values})
        return self.record

    async def get_execution(self, execution_id: str) -> SimpleNamespace | None:
        if self.record is not None and self.record.id == execution_id:
            return self.record
        return None

    async def lock_execution(self, execution_id: str) -> None:
        self.locked_execution_ids.append(execution_id)

    async def list_executions(self, **kwargs: Any) -> list[SimpleNamespace]:
        _ = kwargs
        return [self.record] if self.record is not None else []

    async def list_executions_by_status(self, statuses: list[str]) -> list[SimpleNamespace]:
        if self.record is None or self.record.status not in statuses:
            return []
        return [self.record]

    async def find_execution_by_launch_idempotency_key(self, **kwargs: Any) -> SimpleNamespace | None:
        if self.record is None:
            return None
        if self.record.workspace_id != kwargs["workspace_id"]:
            return None
        if self.record.thread_id != kwargs["thread_id"]:
            return None
        if self.record.user_id != kwargs["user_id"]:
            return None
        if self.record.feature_id != kwargs["capability_id"]:
            return None
        params = self.record.params or {}
        if params.get("launch_idempotency_key") != kwargs["launch_idempotency_key"]:
            return None
        return self.record

    async def count_executions(self, **kwargs: Any) -> int:
        status = kwargs.get("status")
        if status is None:
            return 5
        if "completed" in status:
            return 3
        if "failed" in status:
            return 1
        return 0

    async def count_distinct_execution_users(self, **kwargs: Any) -> int:
        _ = kwargs
        return 4

    async def list_execution_stat_buckets(self, **kwargs: Any) -> list[SimpleNamespace]:
        _ = kwargs
        return [
            SimpleNamespace(
                bucket=datetime(2026, 5, 21, tzinfo=UTC),
                workspace_type="thesis",
                status="completed",
                count=2,
            ),
            SimpleNamespace(
                bucket=datetime(2026, 5, 21, tzinfo=UTC),
                workspace_type="sci",
                status="failed",
                count=1,
            ),
        ]

    async def count_executions_by_workspace_type(self, **kwargs: Any) -> dict[str, int]:
        _ = kwargs
        return {"thesis": 3, "sci": 2}

    async def count_running_feature_executions(self, **kwargs: Any) -> int:
        _ = kwargs
        return 2

    async def get_latest_feature_execution_status(self, **kwargs: Any) -> str | None:
        _ = kwargs
        return "running"

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

    def create_generation_record(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _generation({"id": f"generation-{len(self.generation_records) + 1}", **values})
        self.generation_records.append(record)
        return record

    async def get_generation_record(self, record_id: str) -> SimpleNamespace | None:
        for record in self.generation_records:
            if record.id == record_id:
                return record
        return None

    async def list_generation_records(self, **kwargs: Any) -> list[SimpleNamespace]:
        workspace_id = kwargs.get("workspace_id")
        skill_name = kwargs.get("skill_name")
        status = kwargs.get("status")
        since = kwargs.get("since")
        limit = kwargs.get("limit", 100)
        records = [
            record
            for record in self.generation_records
            if record.workspace_id == workspace_id
            and (skill_name is None or record.skill_name == skill_name)
            and (status is None or record.status == status)
            and (since is None or record.created_at >= since)
        ]
        return records[:limit]

    async def list_generation_records_by_thread(
        self,
        thread_id: str,
    ) -> list[SimpleNamespace]:
        return [
            record
            for record in self.generation_records
            if record.thread_id == thread_id
        ]

    async def delete_generation_records_before(
        self,
        *,
        cutoff: datetime,
        workspace_id: str | None = None,
    ) -> int:
        before = len(self.generation_records)
        self.generation_records = [
            record
            for record in self.generation_records
            if not (
                record.created_at < cutoff
                and (workspace_id is None or record.workspace_id == workspace_id)
            )
        ]
        return before - len(self.generation_records)


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
async def test_reconcile_interrupted_executions_releases_credit_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released: list[tuple[str, str | None]] = []

    class FakeCreditService:
        def __init__(self, session: FakeSession, *, autocommit: bool = True) -> None:
            self.session = session
            self.autocommit = autocommit

        async def release_reservation(self, reservation_id: str, *, reason: str | None = None):
            released.append((reservation_id, reason))
            return SimpleNamespace(id=reservation_id, status="released")

    monkeypatch.setattr(
        "src.dataservice.domains.execution.service.DataServiceCreditService",
        FakeCreditService,
    )
    service, repository, session = _service()
    repository.record = _execution(
        {
            "id": "exec-1",
            "status": "running",
            "params": {"billing": {"credit_reservation_id": "reservation-1"}},
        }
    )

    reconciled = await service.reconcile_interrupted_executions()

    assert reconciled == 1
    assert repository.record.status == "failed"
    assert released == [("reservation-1", "Execution interrupted by process restart")]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_execution_analytics_are_aggregated_inside_domain() -> None:
    service, _, _ = _service()

    active_users = await service.count_active_execution_users(
        created_since=datetime(2026, 5, 20, tzinfo=UTC)
    )
    stats = await service.aggregate_execution_stats(
        created_since=datetime(2026, 5, 20, tzinfo=UTC),
        granularity="day",
    )

    assert active_users == 4
    assert stats["kpis"] == {
        "total": 5,
        "success": 3,
        "failed": 1,
        "success_rate": 0.6,
    }
    assert stats["time_series"][0]["by_type"] == {"thesis": 2, "sci": 1}
    assert stats["by_workspace_type"] == [
        {"type": "thesis", "count": 3},
        {"type": "sci", "count": 2},
    ]


@pytest.mark.asyncio
async def test_feature_status_helpers_read_execution_domain() -> None:
    service, _, _ = _service()

    running_count = await service.count_running_feature_executions(
        workspace_id="ws-1",
        capability_id="idea_to_manuscript",
    )
    latest_status = await service.get_latest_feature_execution_status(
        workspace_id="ws-1",
        capability_id="idea_to_manuscript",
    )

    assert running_count == 2
    assert latest_status == "running"


@pytest.mark.asyncio
async def test_find_execution_by_launch_idempotency_key_reads_execution_domain() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-idem",
            "thread_id": "thread-1",
            "feature_id": "idea_to_manuscript",
            "params": {"launch_idempotency_key": "launch_feature:thread-1:msg-1"},
        }
    )

    found = await service.find_execution_by_launch_idempotency_key(
        workspace_id="ws-1",
        thread_id="thread-1",
        user_id="user-1",
        capability_id="idea_to_manuscript",
        launch_idempotency_key="launch_feature:thread-1:msg-1",
    )

    assert found is not None
    assert found.id == "exec-idem"


@pytest.mark.asyncio
async def test_claim_execution_commit_marks_execution_committing_under_lock() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {"task_report": {"status": "completed"}},
        }
    )

    claim = await service.claim_execution_commit(
        "exec-claim",
        ExecutionCommitClaimCommand(commit_token="token-1"),
    )

    assert claim["status"] == "claimed"
    assert repository.locked_execution_ids == ["exec-claim"]
    assert repository.record.result["commit_state"]["status"] == "committing"
    assert repository.record.result["commit_state"]["commit_token"] == "token-1"
    assert repository.record.result["commit_state"]["lease_expires_at"]
    assert claim["execution"].result_json["commit_state"]["status"] == "committing"


@pytest.mark.asyncio
async def test_claim_execution_commit_rejects_existing_in_progress_claim() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {
                "task_report": {"status": "completed"},
                "commit_state": {
                    "status": "committing",
                    "commit_token": "token-1",
                    "started_at": "2026-06-25T00:00:00+00:00",
                },
            },
        }
    )

    claim = await service.claim_execution_commit(
        "exec-claim",
        ExecutionCommitClaimCommand(commit_token="token-2"),
    )

    assert claim["status"] == "in_progress"
    assert repository.record.result["commit_state"]["commit_token"] == "token-1"


@pytest.mark.asyncio
async def test_claim_execution_commit_reports_stale_expired_claim() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {
                "task_report": {"status": "completed"},
                "commit_state": {
                    "status": "committing",
                    "commit_token": "token-1",
                    "started_at": "2026-06-25T00:00:00+00:00",
                    "lease_expires_at": "2000-01-01T00:00:00+00:00",
                },
            },
        }
    )

    claim = await service.claim_execution_commit(
        "exec-claim",
        ExecutionCommitClaimCommand(commit_token="token-2"),
    )

    assert claim["status"] == "stale"
    assert repository.record.result["commit_state"]["commit_token"] == "token-1"


@pytest.mark.asyncio
async def test_finalize_execution_commit_requires_matching_claim_token_under_lock() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {
                "task_report": {"status": "completed"},
                "commit_state": {
                    "status": "committing",
                    "commit_token": "token-1",
                    "started_at": "2026-06-25T00:00:00+00:00",
                },
            },
        }
    )
    final_result = {
        "task_report": {"status": "completed"},
        "commit_state": {
            "status": "committed",
            "accepted_ids": ["out-1"],
            "rejected_ids": [],
            "counts": {
                "library": 0,
                "documents": 1,
                "memory": 0,
                "decisions": 0,
                "tasks": 0,
            },
            "room_targets": {
                "library": [],
                "documents": [{"output_id": "out-1", "item_id": "doc-1"}],
                "memory": [],
                "decisions": [],
                "tasks": [],
            },
            "committed_at": "2026-06-25T00:01:00+00:00",
        },
    }

    rejected = await service.finalize_execution_commit(
        "exec-claim",
        ExecutionCommitFinalizeCommand(
            commit_token="token-2",
            result_json=final_result,
        ),
    )

    assert rejected is None
    assert repository.locked_execution_ids == ["exec-claim"]
    assert repository.record.result["commit_state"]["status"] == "committing"
    assert repository.record.result["commit_state"]["commit_token"] == "token-1"

    finalized = await service.finalize_execution_commit(
        "exec-claim",
        ExecutionCommitFinalizeCommand(
            commit_token="token-1",
            result_json=final_result,
        ),
    )

    assert finalized is not None
    assert repository.locked_execution_ids == ["exec-claim", "exec-claim"]
    assert repository.record.result["commit_state"]["status"] == "committed"
    assert finalized.result_json["commit_state"]["status"] == "committed"


@pytest.mark.asyncio
async def test_finalize_execution_commit_rejects_malformed_terminal_commit_state() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {
                "task_report": {"status": "completed"},
                "commit_state": {
                    "status": "committing",
                    "commit_token": "token-1",
                    "started_at": "2026-06-25T00:00:00+00:00",
                },
            },
        }
    )

    finalized = await service.finalize_execution_commit(
        "exec-claim",
        ExecutionCommitFinalizeCommand(
            commit_token="token-1",
            result_json={
                "task_report": {"status": "completed"},
                "commit_state": {"status": "committed"},
            },
        ),
    )

    assert finalized is None
    assert repository.record.result["commit_state"]["status"] == "committing"


@pytest.mark.asyncio
async def test_fail_execution_commit_requires_matching_claim_token_and_blocks_reclaim() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {
                "task_report": {"status": "completed"},
                "commit_state": {
                    "status": "committing",
                    "commit_token": "token-1",
                    "started_at": "2026-06-25T00:00:00+00:00",
                },
            },
        }
    )

    rejected = await service.fail_execution_commit(
        "exec-claim",
        ExecutionCommitFailCommand(
            commit_token="token-2",
            error_text="wrong token",
        ),
    )

    assert rejected is None
    assert repository.record.result["commit_state"]["status"] == "committing"

    failed = await service.fail_execution_commit(
        "exec-claim",
        ExecutionCommitFailCommand(
            commit_token="token-1",
            error_text="asset write failed",
            accepted_ids=["out-doc"],
            rejected_ids=["out-lib"],
            partial_counts={"documents": 0},
            partial_room_targets={"documents": []},
        ),
    )

    assert failed is not None
    assert repository.record.result["commit_state"]["status"] == "failed"
    assert repository.record.result["commit_state"]["commit_token"] == "token-1"
    assert repository.record.result["commit_state"]["error_text"] == "asset write failed"
    assert repository.record.result["commit_state"]["accepted_ids"] == ["out-doc"]
    assert repository.record.result["commit_state"]["rejected_ids"] == ["out-lib"]
    assert repository.record.result["commit_state"]["partial_counts"] == {"documents": 0}

    claim = await service.claim_execution_commit(
        "exec-claim",
        ExecutionCommitClaimCommand(commit_token="token-3"),
    )

    assert claim["status"] == "failed"
    assert repository.record.result["commit_state"]["commit_token"] == "token-1"


@pytest.mark.asyncio
async def test_reset_execution_commit_claim_keeps_recovery_log_and_allows_reclaim() -> None:
    service, repository, _ = _service()
    repository.record = _execution(
        {
            "id": "exec-claim",
            "result": {
                "task_report": {"status": "completed"},
                "commit_state": {
                    "status": "failed",
                    "commit_token": "token-1",
                    "error_text": "asset write failed",
                    "manual_recovery_required": True,
                },
            },
        }
    )

    reset = await service.reset_execution_commit(
        "exec-claim",
        ExecutionCommitResetCommand(
            reason="operator verified no room side effects",
            current_commit_token="wrong-token",
        ),
    )

    assert reset is None
    assert repository.record.result["commit_state"]["status"] == "failed"

    reset = await service.reset_execution_commit(
        "exec-claim",
        ExecutionCommitResetCommand(
            reason="operator verified no room side effects",
            current_commit_token="token-1",
        ),
    )

    assert reset is not None
    assert "commit_state" not in repository.record.result
    assert repository.record.result["commit_recovery_log"][0]["reason"] == (
        "operator verified no room side effects"
    )
    assert repository.record.result["commit_recovery_log"][0]["previous_commit_state"]["status"] == "failed"

    claim = await service.claim_execution_commit(
        "exec-claim",
        ExecutionCommitClaimCommand(commit_token="token-2"),
    )

    assert claim["status"] == "claimed"
    assert repository.record.result["commit_state"]["commit_token"] == "token-2"


@pytest.mark.asyncio
async def test_generation_usage_records_are_owned_by_execution_domain() -> None:
    service, repository, session = _service()

    created = await service.create_generation_record(
        GenerationRecordCreateCommand(
            workspace_id="ws-1",
            thread_id="thread-1",
            skill_name="idea_to_manuscript",
            model_name="gpt-x",
            duration_ms=1200,
            token_usage={"input": 10, "output": 20, "total": 30},
            metadata={"source": "legacy"},
        )
    )
    listed = await service.list_generation_records_by_thread("thread-1")
    stats = await service.get_generation_usage_stats(workspace_id="ws-1")

    assert created.id == "generation-1"
    assert created.metadata == {"source": "legacy"}
    assert [record.id for record in listed] == [created.id]
    assert stats["total_executions"] == 1
    assert stats["total_tokens"] == 30
    assert repository.generation_records[0].skill_name == "idea_to_manuscript"
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

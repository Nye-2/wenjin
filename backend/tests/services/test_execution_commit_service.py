"""Tests for ExecutionCommitService (Task 2.9)."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.contracts.task_report import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    MemoryFactData,
    MemoryFactOutput,
    TaskData,
    TaskOutput,
    TaskReport,
)
from src.services.execution_commit_service import (
    ExecutionCommitConcurrencyError,
    ExecutionCommitNotFoundError,
    ExecutionCommitPersistenceError,
    ExecutionCommitService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXECUTION_ID = "exec-commit-1"
WORKSPACE_ID = "ws-commit-1"


def _make_report(
    outputs: list | None = None,
    *,
    status: str = "completed",
) -> TaskReport:
    return TaskReport(
        execution_id=EXECUTION_ID,
        capability_id="cap-1",
        status=status,
        duration_seconds=10,
        narrative="Test narrative for commit",
        outputs=outputs or [],
    )


def _make_execution(report: TaskReport, workspace_id: str = WORKSPACE_ID) -> SimpleNamespace:
    return SimpleNamespace(
        id=EXECUTION_ID,
        workspace_id=workspace_id,
        user_id="user-1",
        feature_id="feat-1",
        result={"task_report": report.model_dump(mode="json")},
        status="completed",
    )


def _make_service(
    execution: SimpleNamespace | None = None,
    *,
    audit=None,
    redis=None,
) -> tuple[ExecutionCommitService, dict[str, AsyncMock]]:
    """Build a service with DataService-backed commit dependencies mocked."""
    execution_svc = MagicMock()
    execution_svc.get_by_id = AsyncMock(return_value=execution)
    execution_svc.claim_execution_commit = AsyncMock(
        return_value={"status": "claimed", "execution": execution}
    )

    async def _update_execution(_execution_id: str | None = None, **kwargs):
        if execution is None:
            return None
        updated = SimpleNamespace(**vars(execution))
        if "result" in kwargs:
            updated.result = kwargs["result"]
        return updated

    execution_svc.update_execution = AsyncMock(side_effect=_update_execution)
    execution_svc.finalize_execution_commit = AsyncMock(side_effect=_update_execution)
    execution_svc.fail_execution_commit = AsyncMock(side_effect=_update_execution)

    dataservice = MagicMock()
    dataservice.create_source = AsyncMock(return_value=SimpleNamespace(id="lib-1"))
    dataservice.import_source = AsyncMock(
        return_value=SimpleNamespace(
            source=SimpleNamespace(id="lib-1"),
            created=True,
            external_ids=[],
        )
    )
    dataservice.register_asset = AsyncMock(return_value=SimpleNamespace(id="prism-file-1"))
    dataservice.delete_asset = AsyncMock(return_value=SimpleNamespace(id="prism-file-1"))
    dataservice.get_prism_surface = AsyncMock(return_value=None)
    dataservice.upsert_prism_workspace_file = AsyncMock(
        side_effect=lambda _workspace_id, command: SimpleNamespace(
            file=SimpleNamespace(
                id="prism-file-1",
                path=command.path,
                current_version_id="prism-version-1",
                content_hash=command.content_hash,
            ),
            version=SimpleNamespace(
                id="prism-version-1",
                content_hash=command.content_hash,
            ),
            changed=True,
            skipped_reason=None,
        )
    )
    dataservice.delete_prism_workspace_file = AsyncMock(
        return_value=SimpleNamespace(changed=True, skipped_reason=None)
    )
    dataservice.restore_prism_workspace_file = AsyncMock(
        return_value=SimpleNamespace(changed=True, skipped_reason=None)
    )
    dataservice.delete_source = AsyncMock(return_value=True)
    dataservice.delete_room_decision = AsyncMock(return_value=True)
    dataservice.delete_room_task = AsyncMock(return_value=True)
    dataservice.stage_and_apply_room_candidates = AsyncMock(
        return_value=SimpleNamespace(
            review_batch_id="review-batch-1",
            counts={"decisions": 1, "tasks": 1},
            item_results=[
                {"room": "decisions", "record_id": "dec-1", "source_item_id": "out-dec"},
                {"room": "tasks", "record_id": "task-1", "source_item_id": "out-task"},
            ],
        )
    )
    dataservice.merge_workspace_memory = AsyncMock(
        return_value=SimpleNamespace(
            changed=True,
            document=SimpleNamespace(
                id="memory-doc-1",
                revision=2,
                content_hash="memory-hash-2",
            ),
        )
    )
    dataservice.append_execution_event = AsyncMock(return_value=SimpleNamespace(id="run-event-1"))

    svc = ExecutionCommitService(
        execution_service=execution_svc,
        dataservice=dataservice,
        audit_service=audit,
        redis=redis,
        referral_first_task_callback=AsyncMock(),
    )

    mocks = {
        "execution": execution_svc,
        "dataservice": dataservice,
    }
    return svc, mocks


def _commit_state_for_all_outputs() -> dict:
    return {
        "status": "committed",
        "accepted_ids": ["out-lib", "out-doc", "out-mem", "out-dec", "out-task"],
        "rejected_ids": [],
        "counts": {
            "library": 1,
            "prism": 1,
            "memory": 1,
            "decisions": 1,
            "tasks": 1,
        },
        "room_targets": {
            "library": [{"output_id": "out-lib", "item_id": "lib-1"}],
            "prism": [
                {
                    "output_id": "out-doc",
                    "item_id": "prism-file-1",
                    "file_id": "prism-file-1",
                    "path": "docs/generated/thesis.md",
                    "version_id": "prism-version-1",
                    "content_hash": "hash-doc",
                    "created_file": True,
                }
            ],
            "memory": [{"output_id": "out-mem", "item_id": "memory-doc-1"}],
            "decisions": [{"output_id": "out-dec", "item_id": "dec-1"}],
            "tasks": [{"output_id": "out-task", "item_id": "task-1"}],
        },
        "committed_at": "2026-06-29T00:00:00+00:00",
        "review_batch_id": "review-batch-1",
    }


def _all_kinds_outputs() -> list:
    return [
        LibraryItemOutput(
            id="out-lib",
            preview="A paper",
            kind="library_item",
            data=LibraryItemData(title="Paper A", authors=["Author 1"], year=2024),
        ),
        DocumentOutput(
            id="out-doc",
            preview="A doc",
            kind="document",
            data=DocumentData(
                name="thesis.pdf",
                mime_type="application/pdf",
                storage_path="/storage/thesis.pdf",
                size_bytes=1024,
            ),
        ),
        MemoryFactOutput(
            id="out-mem",
            preview="A fact",
            kind="memory_fact",
            data=MemoryFactData(content="Key finding", category="research"),
        ),
        DecisionOutput(
            id="out-dec",
            preview="A decision",
            kind="decision",
            data=DecisionData(key="approach", value="qualitative"),
        ),
        TaskOutput(
            id="out-task",
            preview="A task",
            kind="task",
            data=TaskData(title="Write chapter 2"),
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_all_writes_all_kinds():
    """accept_all=True writes all rooms through DataService-backed commit paths."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        actor_user_id="user-1",
    )

    assert result["committed"]["library"] == 1
    assert result["committed"]["prism"] == 1
    assert result["committed"]["memory"] == 1
    assert result["committed"]["decisions"] == 1
    assert result["committed"]["tasks"] == 1

    mocks["dataservice"].import_source.assert_called_once()
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()
    mocks["dataservice"].merge_workspace_memory.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_called_once()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_persists_commit_state_and_preserves_task_report():
    """Successful commits persist commit_state without replacing task_report."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        actor_user_id="user-1",
    )

    mocks["execution"].claim_execution_commit.assert_awaited_once()
    claim_kwargs = mocks["execution"].claim_execution_commit.await_args.kwargs
    assert claim_kwargs["execution_id"] == EXECUTION_ID
    assert isinstance(claim_kwargs["commit_token"], str)
    assert claim_kwargs["commit_token"]
    mocks["execution"].finalize_execution_commit.assert_awaited_once()
    update_args = mocks["execution"].finalize_execution_commit.call_args
    assert update_args.args == (EXECUTION_ID,)
    assert update_args.kwargs["commit"] is True
    assert update_args.kwargs["commit_token"] == claim_kwargs["commit_token"]
    mocks["execution"].update_execution.assert_not_called()

    persisted_result = update_args.kwargs["result"]
    assert persisted_result["task_report"] == report.model_dump(mode="json")

    commit_state = persisted_result["commit_state"]
    assert result["commit_state"] == commit_state
    assert commit_state["status"] == "committed"
    assert commit_state["accepted_ids"] == [output.id for output in outputs]
    assert commit_state["rejected_ids"] == []
    assert commit_state["counts"] == result["committed"]
    assert commit_state["room_targets"] == result["room_targets"]
    assert commit_state["review_batch_id"] == "review-batch-1"
    assert datetime.fromisoformat(commit_state["committed_at"])


@pytest.mark.asyncio
async def test_undo_commit_deletes_room_targets_and_marks_reverted():
    """Undo removes the room records created by the committed execution batch."""
    report = _make_report(_all_kinds_outputs())
    execution = _make_execution(report)
    execution.result["commit_state"] = _commit_state_for_all_outputs()
    svc, mocks = _make_service(execution)

    result = await svc.undo_commit(
        EXECUTION_ID,
        actor_user_id="user-1",
    )

    mocks["dataservice"].delete_source.assert_awaited_once_with(
        source_id="lib-1",
        workspace_id=WORKSPACE_ID,
    )
    mocks["dataservice"].delete_prism_workspace_file.assert_awaited_once_with(
        WORKSPACE_ID,
        "prism-file-1",
        expected_current_hash="hash-doc",
    )
    mocks["dataservice"].delete_asset.assert_not_called()
    mocks["dataservice"].delete_room_decision.assert_awaited_once_with("dec-1")
    mocks["dataservice"].delete_room_task.assert_awaited_once_with(
        workspace_id=WORKSPACE_ID,
        task_id="task-1",
    )

    reverted_state = result["commit_state"]
    assert reverted_state["status"] == "reverted"
    assert reverted_state["accepted_ids"] == ["out-lib", "out-doc", "out-mem", "out-dec", "out-task"]
    assert reverted_state["room_targets"] == _commit_state_for_all_outputs()["room_targets"]
    assert reverted_state["revert_counts"] == {
        "library": 1,
        "prism": 1,
        "memory": 0,
        "decisions": 1,
        "tasks": 1,
    }
    assert datetime.fromisoformat(reverted_state["reverted_at"])

    mocks["execution"].update_execution.assert_awaited_once()
    persisted_result = mocks["execution"].update_execution.await_args.kwargs["result"]
    assert persisted_result["task_report"] == report.model_dump(mode="json")
    assert persisted_result["commit_state"] == reverted_state


@pytest.mark.asyncio
async def test_undo_commit_rejects_non_owner_before_deletes():
    """Undo must enforce execution ownership before touching room records."""
    report = _make_report(_all_kinds_outputs())
    execution = _make_execution(report)
    execution.result["commit_state"] = _commit_state_for_all_outputs()
    svc, mocks = _make_service(execution)

    with pytest.raises(ExecutionCommitNotFoundError):
        await svc.undo_commit(
            EXECUTION_ID,
            actor_user_id="other-user",
        )

    mocks["dataservice"].delete_source.assert_not_called()
    mocks["dataservice"].delete_asset.assert_not_called()
    mocks["dataservice"].delete_room_decision.assert_not_called()
    mocks["dataservice"].delete_room_task.assert_not_called()
    mocks["execution"].update_execution.assert_not_called()


@pytest.mark.asyncio
async def test_commit_rejects_duplicate_claim_before_room_writes_without_redis():
    """The DB-backed commit claim must be the production concurrency guard."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution, redis=None)
    mocks["execution"].claim_execution_commit = AsyncMock(
        return_value={"status": "in_progress", "execution": execution}
    )

    with pytest.raises(ExecutionCommitConcurrencyError):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()
    mocks["execution"].update_execution.assert_not_called()
    mocks["execution"].finalize_execution_commit.assert_not_called()
    mocks["execution"].fail_execution_commit.assert_not_called()


@pytest.mark.asyncio
async def test_commit_fails_when_claim_token_cannot_finalize():
    """Final commit persistence must be bound to the DB claim token holder."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution, redis=None)
    mocks["execution"].finalize_execution_commit = AsyncMock(return_value=None)

    with pytest.raises(ExecutionCommitPersistenceError):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_awaited_once()
    mocks["execution"].finalize_execution_commit.assert_awaited_once()
    mocks["execution"].update_execution.assert_not_called()
    mocks["execution"].fail_execution_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_marks_claim_failed_when_room_write_fails():
    """Claimed commits leave recovery state instead of permanent in_progress."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="Draft.md", doc_kind="draft", content="hello"),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution, redis=None)
    mocks["dataservice"].upsert_prism_workspace_file.side_effect = RuntimeError("asset write failed")

    with pytest.raises(RuntimeError, match="asset write failed"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    claim_token = mocks["execution"].claim_execution_commit.await_args.kwargs["commit_token"]
    mocks["execution"].fail_execution_commit.assert_awaited_once()
    fail_kwargs = mocks["execution"].fail_execution_commit.await_args.kwargs
    assert fail_kwargs["execution_id"] == EXECUTION_ID
    assert fail_kwargs["commit_token"] == claim_token
    assert "asset write failed" in fail_kwargs["error_text"]
    assert fail_kwargs["accepted_ids"] == ["out-doc"]
    assert fail_kwargs["rejected_ids"] == []
    assert fail_kwargs["partial_counts"] == {
        "library": 0,
        "prism": 0,
        "memory": 0,
        "decisions": 0,
        "tasks": 0,
    }
    mocks["execution"].finalize_execution_commit.assert_not_called()
    mocks["execution"].update_execution.assert_not_called()


@pytest.mark.asyncio
async def test_commit_rejects_previous_failed_claim_before_room_writes():
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution, redis=None)
    mocks["execution"].claim_execution_commit = AsyncMock(
        return_value={"status": "failed", "execution": execution}
    )

    with pytest.raises(ExecutionCommitPersistenceError, match="previous execution commit failed"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()
    mocks["execution"].finalize_execution_commit.assert_not_called()
    mocks["execution"].fail_execution_commit.assert_not_called()


@pytest.mark.asyncio
async def test_commit_rejects_stale_claim_before_room_writes():
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution, redis=None)
    mocks["execution"].claim_execution_commit = AsyncMock(
        return_value={"status": "stale", "execution": execution}
    )

    with pytest.raises(ExecutionCommitPersistenceError, match="stale execution commit claim"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()
    mocks["execution"].finalize_execution_commit.assert_not_called()
    mocks["execution"].fail_execution_commit.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_rejects_partial_runs():
    """Partial runs require explicit user-selected output IDs."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs, status="failed_partial")
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="only allowed for completed executions"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_partial_runs_with_explicit_selection():
    """Partial candidates can still be committed after explicit selection."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs, status="failed_partial")
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-doc"],
        actor_user_id="user-1",
    )

    assert result["committed"]["prism"] == 1
    assert result["committed"]["library"] == 0
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_some_only():
    """accepted_ids=[out-lib, out-doc] → only those 2 written."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-lib", "out-doc"],
        actor_user_id="user-1",
    )

    assert result["committed"]["library"] == 1
    assert result["committed"]["prism"] == 1
    assert result["committed"]["memory"] == 0
    assert result["committed"]["decisions"] == 0
    assert result["committed"]["tasks"] == 0

    mocks["dataservice"].import_source.assert_called_once()
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    # run_history must still be called
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_returns_room_targets_for_committed_items():
    """Committed document/library outputs return room focus metadata."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-lib", "out-doc"],
        actor_user_id="user-1",
    )

    prism_target = result["room_targets"]["prism"][0]
    assert prism_target["output_id"] == "out-doc"
    assert prism_target["item_id"] == "prism-file-1"
    assert prism_target["file_id"] == "prism-file-1"
    assert prism_target["version_id"] == "prism-version-1"
    assert prism_target["path"].endswith("thesis.md")
    assert result["room_targets"]["library"] == [{"output_id": "out-lib", "item_id": "lib-1"}]


@pytest.mark.asyncio
async def test_commit_document_writes_to_prism_file():
    """Execution-backed documents are saved as Prism file versions."""
    outputs = [
        DocumentOutput(
            id="out-doc",
            preview="A doc",
            kind="document",
            data=DocumentData(
                name="文献定位与创新点.md",
                doc_kind="draft",
                content="# Literature positioning",
            ),
        )
    ]
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        actor_user_id="user-1",
    )

    prism_payload = mocks["dataservice"].upsert_prism_workspace_file.call_args.args[1]
    assert prism_payload.path == "docs/generated/文献定位与创新点.md"
    assert prism_payload.content_inline == "# Literature positioning"
    assert prism_payload.metadata_json["source"] == "execution_commit"
    mocks["dataservice"].register_asset.assert_not_called()


@pytest.mark.asyncio
async def test_commit_returns_room_targets_for_room_candidates():
    """Memory/decision/task candidates return workspace room focus metadata."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-mem", "out-dec", "out-task"],
        actor_user_id="user-1",
    )

    memory_target = result["room_targets"]["memory"][0]
    assert memory_target["output_id"] == "out-mem"
    assert memory_target["item_id"] == "memory-doc-1"
    assert memory_target["document_id"] == "memory-doc-1"
    assert memory_target["revision"] == "2"
    assert result["room_targets"]["decisions"] == [{"output_id": "out-dec", "item_id": "dec-1"}]
    assert result["room_targets"]["tasks"] == [{"output_id": "out-task", "item_id": "task-1"}]


@pytest.mark.asyncio
async def test_commit_empty_still_writes_run_history():
    """accept_all=False, accepted_ids=[] → no room writes, run_history.record called once."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=False,
        accepted_ids=[],
        actor_user_id="user-1",
    )

    assert all(v == 0 for v in result["committed"].values())
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_empty_selection_persists_discard_without_room_writes():
    """accepted_ids=[] records a durable discard and skips room materialization."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=[],
        actor_user_id="user-1",
    )

    commit_state = result["commit_state"]
    assert commit_state["status"] == "discarded"
    assert commit_state["accepted_ids"] == []
    assert commit_state["rejected_ids"] == [output.id for output in outputs]
    assert all(value == 0 for value in commit_state["counts"].values())

    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()

    persisted_result = mocks["execution"].finalize_execution_commit.call_args.kwargs["result"]
    assert persisted_result["task_report"] == report.model_dump(mode="json")
    assert persisted_result["commit_state"] == commit_state


@pytest.mark.asyncio
async def test_commit_without_selection_returns_noop_without_durable_discard():
    """Omitted accepted_ids is a no-op, not an irreversible discard decision."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        actor_user_id="user-1",
    )

    assert result == {
        "committed": {
            "library": 0,
            "prism": 0,
            "memory": 0,
            "decisions": 0,
            "tasks": 0,
        },
        "room_targets": {
            "prism": [],
            "library": [],
            "memory": [],
            "decisions": [],
            "tasks": [],
        },
    }
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()
    mocks["execution"].update_execution.assert_not_called()
    mocks["execution"].finalize_execution_commit.assert_not_called()


@pytest.mark.asyncio
async def test_commit_library_item_imports_verified_external_source():
    """Execution-backed Library writes preserve external search provenance."""
    outputs = [
        LibraryItemOutput(
            id="out-lib",
            preview="A verified paper",
            kind="library_item",
            data=LibraryItemData(
                title="Federated Fine-Tuning of Large Language Models",
                authors=["Ada Lovelace", "Grace Hopper"],
                year=2025,
                doi="10.1145/example",
                url="https://www.semanticscholar.org/paper/ss-paper-1",
                abstract="Verified external metadata.",
                venue="ICML",
                citation_count=42,
                source="semantic_scholar",
                external_id="ss-paper-1",
                metadata={"paperId": "ss-paper-1", "source": "semantic_scholar"},
            ),
        )
    ]
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        actor_user_id="user-1",
    )

    payload = mocks["dataservice"].import_source.call_args.args[0]
    assert payload.ingest_kind == "semantic_scholar"
    assert payload.evidence_level == "external_verified"
    assert payload.verified_at is not None
    assert payload.venue == "ICML"
    assert payload.citation_count == 42
    assert payload.external_ids[0].provider == "semantic_scholar"
    assert payload.external_ids[0].external_id == "ss-paper-1"
    mocks["dataservice"].create_source.assert_not_called()


@pytest.mark.asyncio
async def test_commit_library_item_syncs_prism_bibliography_without_db_session():
    """Library commits sync refs.bib through DataService, not an execution DB session."""
    outputs = [
        LibraryItemOutput(
            id="out-lib",
            preview="A paper",
            kind="library_item",
            data=LibraryItemData(title="Paper A", authors=["Author 1"], year=2024),
        )
    ]
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)
    sync_calls: list[dict[str, object]] = []

    class _FakeSourceBibliographyService:
        def __init__(self, dataservice=None, **kwargs):
            sync_calls.append({"dataservice": dataservice, "kwargs": kwargs})

        async def sync_prism(self, *, workspace_id: str):
            sync_calls[-1]["workspace_id"] = workspace_id
            return {"synced_file": "refs.bib"}

    with patch(
        "src.services.execution_commit_service.SourceBibliographyService",
        _FakeSourceBibliographyService,
    ):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    assert sync_calls == [
        {
            "dataservice": mocks["dataservice"],
            "kwargs": {},
            "workspace_id": WORKSPACE_ID,
        }
    ]


@pytest.mark.asyncio
async def test_commit_rejects_unknown_accepted_id():
    """accepted_ids must refer to real staged outputs."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, _mocks = _make_service(execution)

    with pytest.raises(ValueError, match="accepted_ids contains unknown"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accepted_ids=["missing"],
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_commit_idempotent_with_key():
    """Same idempotency_key → second call returns cached result, services called only once."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)

    # Set up a simple in-memory Redis mock
    store: dict[str, str] = {}

    redis_mock = MagicMock()

    async def mock_get(key: str) -> str | None:
        return store.get(key)

    async def mock_set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    redis_mock.get = mock_get
    redis_mock.set = mock_set

    svc, mocks = _make_service(execution, redis=redis_mock)

    # First call — should write everything
    result1 = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        idempotency_key="key-abc",
        actor_user_id="user-1",
    )
    assert mocks["dataservice"].append_execution_event.call_count == 1
    assert result1["commit_state"]["status"] == "committed"
    assert result1["commit_state"]["accepted_ids"] == [output.id for output in outputs]

    # Second call with same key — should return cached, no additional writes
    result2 = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        idempotency_key="key-abc",
        actor_user_id="user-1",
    )
    # Run-history event should still only have been called once (second call short-circuits)
    assert mocks["dataservice"].append_execution_event.call_count == 1
    assert mocks["execution"].finalize_execution_commit.call_count == 1
    assert result1 == result2


@pytest.mark.asyncio
async def test_commit_ignores_stale_idempotency_cache_without_commit_state():
    """Old cached responses without commit_state cannot be treated as durable truth."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    stale_result = {
        "committed": {
            "library": 0,
            "prism": 0,
            "memory": 0,
            "decisions": 0,
            "tasks": 0,
        },
        "room_targets": {
            "prism": [],
            "library": [],
            "memory": [],
            "decisions": [],
            "tasks": [],
        },
    }

    redis_mock = SimpleNamespace()
    redis_mock.get = AsyncMock(return_value=json.dumps(stale_result))
    redis_mock.set = AsyncMock()

    svc, mocks = _make_service(execution, redis=redis_mock)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-doc"],
        idempotency_key="key-abc",
        actor_user_id="user-1",
    )

    assert result["commit_state"]["status"] == "committed"
    assert result["commit_state"]["accepted_ids"] == ["out-doc"]
    assert result["committed"]["prism"] == 1
    mocks["execution"].finalize_execution_commit.assert_awaited_once()
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()
    redis_mock.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_ignores_unavailable_redis_cache_read():
    """Redis cache is an optimization; DB claim remains the source of truth."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="Draft.md", doc_kind="draft", content="hello"),
    )
    report = _make_report([output])
    execution = _make_execution(report)

    redis_mock = SimpleNamespace()
    redis_mock.get = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    redis_mock.set = AsyncMock()

    svc, mocks = _make_service(execution, redis=redis_mock)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-doc"],
        idempotency_key="key-abc",
        actor_user_id="user-1",
    )

    assert result["commit_state"]["status"] == "committed"
    mocks["execution"].claim_execution_commit.assert_awaited_once()
    mocks["execution"].finalize_execution_commit.assert_awaited_once()
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()


@pytest.mark.asyncio
async def test_commit_ignores_unavailable_redis_cache_write_after_durable_persistence():
    """A Redis set failure must not turn a persisted commit into an API failure."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="Draft.md", doc_kind="draft", content="hello"),
    )
    report = _make_report([output])
    execution = _make_execution(report)

    redis_mock = SimpleNamespace()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(side_effect=RuntimeError("redis unavailable"))

    svc, mocks = _make_service(execution, redis=redis_mock)

    with patch(
        "src.services.execution_commit_service.publish_workspace_event",
        new=AsyncMock(),
    ) as publish_refresh:
        result = await svc.commit_outputs(
            EXECUTION_ID,
            accepted_ids=["out-doc"],
            idempotency_key="key-abc",
            actor_user_id="user-1",
        )

    assert result["commit_state"]["status"] == "committed"
    mocks["execution"].finalize_execution_commit.assert_awaited_once()
    redis_mock.set.assert_awaited_once()
    publish_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_raises_when_commit_state_persistence_not_confirmed():
    """Do not report success or cache when execution result persistence fails."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    audit = MagicMock()
    audit.log = AsyncMock()

    redis_mock = SimpleNamespace()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock()

    svc, mocks = _make_service(execution, audit=audit, redis=redis_mock)
    mocks["execution"].finalize_execution_commit.side_effect = None
    mocks["execution"].finalize_execution_commit.return_value = None

    with patch(
        "src.services.execution_commit_service.publish_workspace_event",
        new=AsyncMock(),
    ) as publish_refresh:
        with pytest.raises(RuntimeError, match="commit_state persistence failed"):
            await svc.commit_outputs(
                EXECUTION_ID,
                accept_all=True,
                idempotency_key="key-abc",
                actor_user_id="user-1",
            )

    redis_mock.set.assert_not_called()
    publish_refresh.assert_not_called()
    audit.log.assert_not_called()


@pytest.mark.asyncio
async def test_commit_uses_redis_lock_when_supported():
    """When Redis lock primitives exist, commits are guarded through a short lock."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)

    svc, _mocks = _make_service(execution, redis=redis_mock)

    await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-doc"],
        actor_user_id="user-1",
    )

    lock_call = redis_mock.set.await_args_list[0]
    assert lock_call.args[0] == f"commit:lock:{EXECUTION_ID}"
    assert lock_call.kwargs == {"nx": True, "ex": 60}
    redis_mock.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_commit_state_short_circuits_duplicate_writes_with_new_key():
    """A durable commit_state wins over a new idempotency key and avoids rewrites."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    existing_commit_state = {
        "status": "committed",
        "accepted_ids": ["out-lib"],
        "rejected_ids": ["out-doc", "out-mem", "out-dec", "out-task"],
        "counts": {
            "library": 1,
            "prism": 0,
            "memory": 0,
            "decisions": 0,
            "tasks": 0,
        },
        "room_targets": {
            "prism": [],
            "library": [{"output_id": "out-lib", "item_id": "lib-1"}],
            "memory": [],
            "decisions": [],
            "tasks": [],
        },
        "committed_at": "2026-06-24T12:00:00+00:00",
        "review_batch_id": "review-batch-1",
    }
    execution = _make_execution(report)
    execution.result["commit_state"] = existing_commit_state

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock()

    svc, mocks = _make_service(execution, redis=redis_mock)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-doc"],
        idempotency_key="new-key",
        actor_user_id="user-1",
    )

    assert result == {
        "committed": existing_commit_state["counts"],
        "room_targets": existing_commit_state["room_targets"],
        "review_batch_id": "review-batch-1",
        "commit_state": existing_commit_state,
    }
    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()
    mocks["execution"].update_execution.assert_not_called()
    mocks["execution"].finalize_execution_commit.assert_not_called()
    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_existing_commit_state_wins_before_request_body_validation():
    """Once durable, duplicate calls return the prior result despite stale request args."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="Draft.md", doc_kind="draft", content="hello"),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    existing_commit_state = {
        "status": "committed",
        "accepted_ids": ["out-doc"],
        "rejected_ids": [],
        "counts": {
            "library": 0,
            "prism": 1,
            "memory": 0,
            "decisions": 0,
            "tasks": 0,
        },
        "room_targets": {
            "library": [],
            "prism": [{"output_id": "out-doc", "item_id": "prism-file-1"}],
            "memory": [],
            "decisions": [],
            "tasks": [],
        },
        "committed_at": "2026-06-25T00:00:00+00:00",
    }
    execution.result["commit_state"] = existing_commit_state
    svc, mocks = _make_service(execution, redis=None)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["missing-output"],
        actor_user_id="user-1",
    )

    assert result["commit_state"] == existing_commit_state
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["execution"].finalize_execution_commit.assert_not_called()


@pytest.mark.asyncio
async def test_commit_raises_not_found_on_missing_execution():
    """Missing executions use the explicit hidden/not-found contract."""
    svc, mocks = _make_service(execution=None)

    with pytest.raises(ExecutionCommitNotFoundError, match="not found"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_commit_rejects_non_owner_before_room_writes():
    """Commit writeback must be scoped to the execution owner."""
    report = _make_report(_all_kinds_outputs())
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ExecutionCommitNotFoundError, match="not found"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="other-user",
        )

    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_raises_on_no_task_report():
    """Execution exists but has no task_report in result → ValueError."""
    execution = SimpleNamespace(
        id=EXECUTION_ID,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        feature_id=None,
        result={"something_else": {}},
        status="completed",
    )
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="no task_report"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_commit_publishes_refresh_event():
    """After successful commit, canonical workspace.refresh is published."""
    report = _make_report([])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with patch("src.services.execution_commit_service.publish_workspace_event", new=AsyncMock()) as publish_refresh:
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    publish_refresh.assert_awaited_once_with(
        WORKSPACE_ID,
        "workspace.refresh",
        {
            "refresh_targets": [
                "activity",
                "artifacts",
                "dashboard",
                "library",
                "decisions",
                "tasks",
                "runs",
                "references",
                "prism",
            ]
        },
    )

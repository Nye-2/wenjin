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
    ReviewPacket,
    ReviewPacketItem,
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


def _attach_change_set(
    execution: SimpleNamespace,
    *,
    output_id: str,
    output_kind: str,
    room: str,
    risk: str = "medium",
    default_apply_state: str = "staged",
    accepted: bool = False,
    rejected: bool = False,
    undone: bool = False,
) -> SimpleNamespace:
    unit_id = f"output-{output_id}"
    execution.result["change_set"] = {
        "execution_id": EXECUTION_ID,
        "workspace_id": execution.workspace_id,
        "write_mode": "ask_workspace_write",
        "summary": "Reviewable output changes.",
        "created_at": "2026-06-20T00:00:00Z",
        "units": [
            {
                "id": unit_id,
                "target": {
                    "room": room,
                    "object_type": output_kind,
                    "object_id": output_id,
                },
                "action": f"commit_{output_kind}",
                "risk": risk,
                "risk_reasons": ["requires review"] if risk in {"high", "critical"} else [],
                "default_apply_state": default_apply_state,
                "requires_confirmation": True,
                "diff": {"title": output_id},
                "provenance": {"output_id": output_id, "output_kind": output_kind},
                "rollback": {},
            }
        ],
    }
    execution.result["change_set_review_state"] = {
        "schema_version": "wenjin.change_set.review_state.v1",
        "accepted_unit_ids": [unit_id] if accepted else [],
        "rejected_unit_ids": [unit_id] if rejected else [],
        "undone_unit_ids": [unit_id] if undone else [],
        "updated_at": "2026-06-20T00:00:01Z",
    }
    return execution


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
    execution_svc.patch_execution_result = AsyncMock(side_effect=_update_execution)
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
    dataservice.set_room_decision = AsyncMock(
        return_value=SimpleNamespace(id="dec-1")
    )
    dataservice.delete_room_decision = AsyncMock(return_value=True)
    dataservice.create_room_task = AsyncMock(return_value=SimpleNamespace(id="task-1"))
    dataservice.delete_room_task = AsyncMock(return_value=True)
    dataservice.mark_sandbox_artifact_materialized = AsyncMock(
        return_value=SimpleNamespace(id="artifact-1", materialization_status="applied")
    )
    dataservice.update_workspace_settings = AsyncMock(
        return_value=SimpleNamespace(workspace_id=WORKSPACE_ID, write_mode="ask_workspace_write")
    )
    async def _stage_and_apply_room_candidates(*, candidates, **_kwargs):
        item_results = []
        counts = {"decisions": 0, "tasks": 0}
        for candidate in candidates:
            if candidate.target_kind == "decision":
                counts["decisions"] += 1
                item_results.append(
                    {
                        "room": "decisions",
                        "record_id": "dec-1",
                        "source_item_id": candidate.source_item_id,
                    }
                )
            elif candidate.target_kind == "workspace_task":
                counts["tasks"] += 1
                item_results.append(
                    {
                        "room": "tasks",
                        "record_id": "task-1",
                        "source_item_id": candidate.source_item_id,
                    }
                )
        return SimpleNamespace(
            review_batch_id="review-batch-1",
            counts=counts,
            item_results=item_results,
        )

    dataservice.stage_and_apply_room_candidates = AsyncMock(
        side_effect=_stage_and_apply_room_candidates
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
    dataservice.workspace_has_active_membership = AsyncMock(return_value=True)

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
            "sandbox": 0,
            "settings": 0,
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
            "sandbox": [],
            "settings": [],
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


def _bulk_safe_outputs() -> list:
    return [
        DocumentOutput(
            id="out-doc",
            preview="A doc",
            kind="document",
            data=DocumentData(name="Draft.md", doc_kind="draft", content="hello"),
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
async def test_commit_all_writes_bulk_safe_outputs():
    """accept_all=True writes low-risk rooms through DataService-backed commit paths."""
    outputs = _bulk_safe_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        actor_user_id="user-1",
    )

    assert result["committed"]["library"] == 0
    assert result["committed"]["prism"] == 1
    assert result["committed"]["memory"] == 0
    assert result["committed"]["decisions"] == 0
    assert result["committed"]["tasks"] == 1

    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()
    mocks["dataservice"].merge_workspace_memory.assert_not_called()
    mocks["dataservice"].create_room_task.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_explicit_selection_writes_all_kinds():
    """accepted_ids can still write all rooms through DataService-backed commit paths."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=[output.id for output in outputs],
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
    mocks["dataservice"].set_room_decision.assert_called_once()
    mocks["dataservice"].create_room_task.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_persists_commit_state_and_preserves_task_report():
    """Successful commits persist commit_state without replacing task_report."""
    outputs = _bulk_safe_outputs()
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
    assert "review_batch_id" not in commit_state
    assert datetime.fromisoformat(commit_state["committed_at"])


@pytest.mark.asyncio
async def test_commit_all_rejects_default_unchecked_output():
    """accept_all=True rejects outputs that were not default-selected for review."""
    output = DocumentOutput(
        id="out-doc",
        preview="Needs review",
        kind="document",
        default_checked=False,
        data=DocumentData(name="Claim audit.md", doc_kind="draft", content="needs review"),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="explicit review/selection"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_rejects_manual_review_output():
    """accept_all=True rejects outputs whose kind requires explicit review."""
    output = DecisionOutput(
        id="out-dec",
        preview="A decision",
        kind="decision",
        data=DecisionData(key="approach", value="qualitative"),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="explicit review/selection"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_rejects_memory_fact_with_claim_content():
    """accept_all=True rejects data text that signals claim/evidence review risk."""
    output = MemoryFactOutput(
        id="out-mem",
        preview="A fact",
        kind="memory_fact",
        data=MemoryFactData(
            category="general",
            content="Manual review required: this claim lacks evidence.",
        ),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="explicit review/selection"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].merge_workspace_memory.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_allows_safe_document_with_academic_body_terms():
    """Normal academic body text should not make a safe document bulk-unsafe."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(
            name="draft.md",
            doc_kind="draft",
            content=(
                "This literature review compares citation practices and evidence "
                "standards before introducing the main claim."
            ),
        ),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        actor_user_id="user-1",
    )

    assert result["committed"]["prism"] == 1
    assert result["commit_state"]["accepted_ids"] == ["out-doc"]
    mocks["dataservice"].upsert_prism_workspace_file.assert_called_once()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_explicit_selection_allows_data_derived_bulk_unsafe_output():
    """accepted_ids still commits outputs rejected from accept_all by data text."""
    output = MemoryFactOutput(
        id="out-mem",
        preview="A fact",
        kind="memory_fact",
        data=MemoryFactData(
            category="general",
            content="Manual review required: this claim lacks evidence.",
        ),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-mem"],
        actor_user_id="user-1",
    )

    assert result["committed"]["memory"] == 1
    assert result["commit_state"]["accepted_ids"] == ["out-mem"]
    mocks["dataservice"].merge_workspace_memory.assert_called_once()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_explicit_selection_requires_changeset_acceptance_when_present():
    """Accepted ChangeUnit ids still require prior Review & Changes acceptance."""
    output = MemoryFactOutput(
        id="out-mem",
        preview="A fact",
        kind="memory_fact",
        data=MemoryFactData(category="general", content="Needs review."),
    )
    report = _make_report([output])
    execution = _attach_change_set(
        _make_execution(report),
        output_id="out-mem",
        output_kind="memory_fact",
        room="memory",
    )
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="must be accepted"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accepted_unit_ids=["output-out-mem"],
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].merge_workspace_memory.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_changeset_rejects_historical_output_id_selection():
    """ChangeSet executions must use unit ids instead of the historical output-id bridge."""
    output = MemoryFactOutput(
        id="out-mem",
        preview="A fact",
        kind="memory_fact",
        data=MemoryFactData(category="general", content="Accepted fact."),
    )
    report = _make_report([output])
    execution = _attach_change_set(
        _make_execution(report),
        output_id="out-mem",
        output_kind="memory_fact",
        room="memory",
        accepted=True,
    )
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="accepted_unit_ids"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accepted_ids=["out-mem"],
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].merge_workspace_memory.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_changeset_units_materialize_direct_room_writes():
    """Accepted ChangeUnit ids are the commit primitive for ChangeSet executions."""
    output = DecisionOutput(
        id="out-dec",
        preview="A decision",
        kind="decision",
        data=DecisionData(key="approach", value="qualitative"),
    )
    report = _make_report([output])
    execution = _attach_change_set(
        _make_execution(report),
        output_id="out-dec",
        output_kind="decision",
        room="decisions",
        accepted=True,
    )
    execution.result["change_set"]["units"][0]["materialization"] = {
        "operation": "decisions.set",
        "payload": {
            "key": "approach",
            "value": "quantitative",
            "confidence": 0.7,
        },
    }
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_unit_ids=["output-out-dec"],
        actor_user_id="user-1",
    )

    assert result["committed"]["decisions"] == 1
    assert result["commit_state"]["accepted_ids"] == ["out-dec"]
    assert result["commit_state"]["accepted_unit_ids"] == ["output-out-dec"]
    assert result["room_targets"]["decisions"] == [
        {
            "output_id": "out-dec",
            "item_id": "dec-1",
            "unit_id": "output-out-dec",
            "provenance_key": "execution:exec-commit-1:unit:output-out-dec",
        }
    ]
    mocks["dataservice"].set_room_decision.assert_called_once()
    command = mocks["dataservice"].set_room_decision.call_args.args[0]
    assert command.value == "quantitative"
    assert command.confidence == 0.7
    assert command.extracted_by == "execution:exec-commit-1:unit:output-out-dec"
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_changeset_failure_records_only_completed_unit_materializations():
    """A partial ChangeUnit commit records the units that actually reached rooms."""
    decision_output = DecisionOutput(
        id="out-dec",
        preview="A decision",
        kind="decision",
        data=DecisionData(key="approach", value="qualitative"),
    )
    task_output = TaskOutput(
        id="out-task",
        preview="A task",
        kind="task",
        data=TaskData(title="Verify dataset", priority=2),
    )
    report = _make_report([decision_output, task_output])
    execution = _make_execution(report)
    execution.result["change_set"] = {
        "execution_id": EXECUTION_ID,
        "workspace_id": execution.workspace_id,
        "write_mode": "ask_workspace_write",
        "summary": "Reviewable output changes.",
        "created_at": "2026-06-20T00:00:00Z",
        "units": [
            {
                "id": "output-out-dec",
                "target": {"room": "decisions", "object_type": "decision", "object_id": "out-dec"},
                "action": "commit_decision",
                "risk": "medium",
                "risk_reasons": [],
                "default_apply_state": "staged",
                "requires_confirmation": True,
                "diff": {"title": "out-dec"},
                "provenance": {"output_id": "out-dec", "output_kind": "decision"},
                "rollback": {},
            },
            {
                "id": "output-out-task",
                "target": {"room": "tasks", "object_type": "task", "object_id": "out-task"},
                "action": "commit_task",
                "risk": "medium",
                "risk_reasons": [],
                "default_apply_state": "staged",
                "requires_confirmation": True,
                "diff": {"title": "out-task"},
                "provenance": {"output_id": "out-task", "output_kind": "task"},
                "rollback": {},
            },
        ],
    }
    execution.result["change_set_review_state"] = {
        "schema_version": "wenjin.change_set.review_state.v1",
        "accepted_unit_ids": ["output-out-dec", "output-out-task"],
        "rejected_unit_ids": [],
        "undone_unit_ids": [],
        "updated_at": "2026-06-20T00:00:01Z",
    }
    svc, mocks = _make_service(execution)
    mocks["dataservice"].create_room_task.side_effect = RuntimeError("task write failed")

    with pytest.raises(RuntimeError, match="task write failed"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accepted_unit_ids=["output-out-dec", "output-out-task"],
            actor_user_id="user-1",
        )

    progress_patch = mocks["execution"].patch_execution_result.await_args.kwargs[
        "result_patch"
    ]["change_unit_materialization"]
    assert progress_patch["completed_unit_ids"] == ["output-out-dec"]
    assert progress_patch["room_targets"]["decisions"] == [
        {
            "output_id": "out-dec",
            "item_id": "dec-1",
            "unit_id": "output-out-dec",
            "provenance_key": progress_patch["room_targets"]["decisions"][0][
                "provenance_key"
            ],
        }
    ]
    fail_kwargs = mocks["execution"].fail_execution_commit.await_args.kwargs
    assert fail_kwargs["partial_counts"]["decisions"] == 1
    assert fail_kwargs["partial_counts"]["tasks"] == 0
    assert fail_kwargs["partial_room_targets"]["decisions"] == progress_patch[
        "room_targets"
    ]["decisions"]
    mocks["dataservice"].set_room_decision.assert_awaited_once()
    mocks["dataservice"].create_room_task.assert_awaited_once()
    mocks["execution"].finalize_execution_commit.assert_not_called()


@pytest.mark.asyncio
async def test_commit_changeset_retry_skips_completed_unit_materializations():
    """Retrying after recovery resumes at remaining ChangeUnits and drops temp progress."""
    decision_output = DecisionOutput(
        id="out-dec",
        preview="A decision",
        kind="decision",
        data=DecisionData(key="approach", value="qualitative"),
    )
    task_output = TaskOutput(
        id="out-task",
        preview="A task",
        kind="task",
        data=TaskData(title="Verify dataset", priority=2),
    )
    report = _make_report([decision_output, task_output])
    execution = _make_execution(report)
    decision_target = {
        "output_id": "out-dec",
        "item_id": "dec-1",
        "unit_id": "output-out-dec",
        "provenance_key": "execution:exec-commit-1:unit:output-out-dec",
    }
    execution.result.update(
        {
            "change_set": {
                "execution_id": EXECUTION_ID,
                "workspace_id": execution.workspace_id,
                "write_mode": "ask_workspace_write",
                "summary": "Reviewable output changes.",
                "created_at": "2026-06-20T00:00:00Z",
                "units": [
                    {
                        "id": "output-out-dec",
                        "target": {
                            "room": "decisions",
                            "object_type": "decision",
                            "object_id": "out-dec",
                        },
                        "action": "commit_decision",
                        "risk": "medium",
                        "risk_reasons": [],
                        "default_apply_state": "staged",
                        "requires_confirmation": True,
                        "diff": {"title": "out-dec"},
                        "provenance": {"output_id": "out-dec", "output_kind": "decision"},
                        "rollback": {},
                    },
                    {
                        "id": "output-out-task",
                        "target": {
                            "room": "tasks",
                            "object_type": "task",
                            "object_id": "out-task",
                        },
                        "action": "commit_task",
                        "risk": "medium",
                        "risk_reasons": [],
                        "default_apply_state": "staged",
                        "requires_confirmation": True,
                        "diff": {"title": "out-task"},
                        "provenance": {"output_id": "out-task", "output_kind": "task"},
                        "rollback": {},
                    },
                ],
            },
            "change_set_review_state": {
                "schema_version": "wenjin.change_set.review_state.v1",
                "accepted_unit_ids": ["output-out-dec", "output-out-task"],
                "rejected_unit_ids": [],
                "undone_unit_ids": [],
                "updated_at": "2026-06-20T00:00:01Z",
            },
            "change_unit_materialization": {
                "schema_version": "wenjin.change_unit_materialization.v1",
                "execution_id": EXECUTION_ID,
                "accepted_unit_ids": ["output-out-dec", "output-out-task"],
                "completed_unit_ids": ["output-out-dec"],
                "counts": {
                    "library": 0,
                    "prism": 0,
                    "memory": 0,
                    "decisions": 1,
                    "tasks": 0,
                    "sandbox": 0,
                    "settings": 0,
                },
                "room_targets": {
                    "library": [],
                    "prism": [],
                    "memory": [],
                    "decisions": [decision_target],
                    "tasks": [],
                    "sandbox": [],
                    "settings": [],
                },
            },
        }
    )
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_unit_ids=["output-out-dec", "output-out-task"],
        actor_user_id="user-1",
    )

    assert result["committed"]["decisions"] == 1
    assert result["committed"]["tasks"] == 1
    assert result["room_targets"]["decisions"] == [decision_target]
    assert result["room_targets"]["tasks"] == [
        {
            "output_id": "out-task",
            "item_id": "task-1",
            "unit_id": "output-out-task",
            "provenance_key": result["room_targets"]["tasks"][0]["provenance_key"],
        }
    ]
    mocks["dataservice"].set_room_decision.assert_not_called()
    mocks["dataservice"].create_room_task.assert_awaited_once()
    finalize_kwargs = mocks["execution"].finalize_execution_commit.call_args.kwargs
    assert "change_unit_materialization" in finalize_kwargs["delete_result_keys"]


@pytest.mark.asyncio
async def test_commit_changeset_sandbox_unit_materializes_artifact_without_output_bridge():
    """Sandbox ChangeUnits are materialized by unit id, not by historical output ids."""
    report = _make_report([])
    execution = _make_execution(report)
    execution.result["change_set"] = {
        "execution_id": EXECUTION_ID,
        "workspace_id": execution.workspace_id,
        "write_mode": "auto_draft",
        "summary": "Sandbox artifact ready.",
        "created_at": "2026-06-20T00:00:00Z",
        "units": [
            {
                "id": "review-review-1",
                "target": {
                    "room": "sandbox",
                    "object_type": "sandbox_artifact",
                    "object_id": "artifact-1",
                    "path": "/workspace/reports/analysis.md",
                },
                "action": "accept_sandbox_artifact",
                "risk": "low",
                "risk_reasons": [],
                "default_apply_state": "staged",
                "requires_confirmation": True,
                "diff": {"title": "Accept sandbox artifact"},
                "provenance": {
                    "source": "task_report.review_items",
                    "source_review_item_id": "review-1",
                },
                "rollback": {"strategy": "manual_review"},
                "materialization": {
                    "operation": "sandbox.materialize_artifact",
                    "payload": {
                        "artifact_id": "artifact-1",
                        "review_item_id": "review-1",
                        "path": "/workspace/reports/analysis.md",
                    },
                },
            }
        ],
    }
    execution.result["change_set_review_state"] = {
        "schema_version": "wenjin.change_set.review_state.v1",
        "accepted_unit_ids": ["review-review-1"],
        "rejected_unit_ids": [],
        "undone_unit_ids": [],
        "updated_at": "2026-06-20T00:00:01Z",
    }
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_unit_ids=["review-review-1"],
        actor_user_id="user-1",
    )

    assert result["committed"]["sandbox"] == 1
    assert result["commit_state"]["status"] == "committed"
    assert result["commit_state"]["accepted_ids"] == []
    assert result["commit_state"]["accepted_unit_ids"] == ["review-review-1"]
    assert result["room_targets"]["sandbox"] == [
        {
            "output_id": "review-review-1",
            "item_id": "artifact-1",
            "unit_id": "review-review-1",
            "artifact_id": "artifact-1",
            "provenance_key": "execution:exec-commit-1:unit:review-review-1",
            "path": "/workspace/reports/analysis.md",
        }
    ]
    mocks["dataservice"].mark_sandbox_artifact_materialized.assert_awaited_once_with(
        "artifact-1",
        review_item_id="review-1",
    )
    event_payload = mocks["dataservice"].append_execution_event.await_args.args[1].payload_json
    assert event_payload["artifact_count"] == 1
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_commit_changeset_settings_unit_updates_workspace_settings_without_output_bridge():
    """Settings ChangeUnits are materialized directly, not through historical outputs."""
    report = _make_report([])
    execution = _make_execution(report)
    execution.result["change_set"] = {
        "execution_id": EXECUTION_ID,
        "workspace_id": execution.workspace_id,
        "write_mode": "ask_workspace_write",
        "summary": "Workspace setting update.",
        "created_at": "2026-06-20T00:00:00Z",
        "units": [
            {
                "id": "review-settings-write-mode",
                "target": {
                    "room": "settings",
                    "object_type": "workspace_settings",
                    "object_id": "write_mode",
                },
                "action": "update_workspace_settings",
                "risk": "medium",
                "risk_reasons": [],
                "default_apply_state": "staged",
                "requires_confirmation": True,
                "diff": {"write_mode": "ask_workspace_write"},
                "provenance": {
                    "source": "task_report.review_items",
                    "source_review_item_id": "settings-write-mode",
                },
                "rollback": {"strategy": "manual_restore_settings"},
                "materialization": {
                    "operation": "settings.update",
                    "payload": {
                        "write_mode": "ask_workspace_write",
                        "thinking_enabled": False,
                    },
                },
            }
        ],
    }
    execution.result["change_set_review_state"] = {
        "schema_version": "wenjin.change_set.review_state.v1",
        "accepted_unit_ids": ["review-settings-write-mode"],
        "rejected_unit_ids": [],
        "undone_unit_ids": [],
        "updated_at": "2026-06-20T00:00:01Z",
    }
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_unit_ids=["review-settings-write-mode"],
        actor_user_id="user-1",
    )

    assert result["committed"]["settings"] == 1
    assert result["commit_state"]["status"] == "committed"
    assert result["commit_state"]["accepted_ids"] == []
    assert result["commit_state"]["accepted_unit_ids"] == ["review-settings-write-mode"]
    assert result["room_targets"]["settings"] == [
        {
            "output_id": "review-settings-write-mode",
            "item_id": WORKSPACE_ID,
            "unit_id": "review-settings-write-mode",
            "settings_keys": "thinking_enabled,write_mode",
            "provenance_key": "execution:exec-commit-1:unit:review-settings-write-mode",
        }
    ]
    command = mocks["dataservice"].update_workspace_settings.await_args.args[1]
    assert command.write_mode == "ask_workspace_write"
    assert command.thinking_enabled is False
    event_payload = mocks["dataservice"].append_execution_event.await_args.args[1].payload_json
    assert event_payload["artifact_count"] == 1
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_commit_compacts_changeset_details_after_successful_writeback():
    """Accepted writeback keeps a small receipt, not the full review diff payload."""
    output = MemoryFactOutput(
        id="out-mem",
        preview="A fact",
        kind="memory_fact",
        data=MemoryFactData(category="general", content="Accepted fact."),
    )
    report = _make_report([output])
    execution = _attach_change_set(
        _make_execution(report),
        output_id="out-mem",
        output_kind="memory_fact",
        room="memory",
        accepted=True,
    )
    execution.result["change_set"]["units"][0]["diff"] = {
        "title": "out-mem",
        "full_text": "x" * 10_000,
    }
    execution.result["change_set"]["units"][0]["rollback"] = {
        "previous_version": "y" * 10_000,
    }
    execution.result["unit_states"] = [
        {
            "unit_id": "output-out-mem",
            "default_apply_state": "staged",
            "state": "accepted",
        }
    ]
    svc, mocks = _make_service(execution)

    await svc.commit_outputs(
        EXECUTION_ID,
        accepted_unit_ids=["output-out-mem"],
        actor_user_id="user-1",
    )

    finalize_kwargs = mocks["execution"].finalize_execution_commit.call_args.kwargs
    persisted_result = finalize_kwargs["result"]
    assert finalize_kwargs["delete_result_keys"] == [
        "change_set",
        "change_set_review_state",
        "unit_states",
    ]
    assert "change_set" not in persisted_result
    assert "change_set_review_state" not in persisted_result
    assert "unit_states" not in persisted_result
    receipt = persisted_result["change_set_receipt"]
    assert receipt["schema_version"] == "wenjin.change_set.receipt.v1"
    assert receipt["retention"] == "compacted_after_commit"
    assert receipt["accepted_unit_ids"] == ["output-out-mem"]
    assert receipt["accepted_output_ids"] == ["out-mem"]
    assert receipt["targets"]["memory"][0]["output_id"] == "out-mem"
    assert "full_text" not in json.dumps(receipt)
    assert "previous_version" not in json.dumps(receipt)


@pytest.mark.asyncio
async def test_commit_explicit_selection_rejects_changeset_blocked_output_even_if_accepted():
    """Blocked units require native materialization or remediation, not output-id commit."""
    output = DecisionOutput(
        id="out-dec",
        preview="A decision",
        kind="decision",
        data=DecisionData(key="approach", value="qualitative"),
    )
    report = _make_report([output])
    execution = _attach_change_set(
        _make_execution(report),
        output_id="out-dec",
        output_kind="decision",
        room="decisions",
        risk="high",
        default_apply_state="blocked",
        accepted=True,
    )
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="blocked"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accepted_unit_ids=["output-out-dec"],
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_rejects_review_items_metadata_risk():
    """accept_all=True rejects review_items carrying manual-review metadata."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="draft.md", doc_kind="draft", content="ready"),
    )
    report = _make_report([output])
    report.review_items = [
        {
            "item_id": "review-1",
            "kind": "document",
            "title": "Reviewer note",
            "summary": "Needs approval",
            "source": {"requires_manual_review": True},
            "default_checked": True,
            "can_commit": True,
        }
    ]
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="explicit review/selection"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_rejects_review_items_root_risk_string():
    """Legacy review_items risk strings are also bulk-unsafe."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="draft.md", doc_kind="draft", content="ready"),
    )
    report = _make_report([output])
    report.review_items = [
        {
            "item_id": "review-1",
            "kind": "document",
            "title": "Reviewer note",
            "summary": "Needs approval",
            "risk": "high",
            "default_checked": True,
            "can_commit": True,
        }
    ]
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="explicit review/selection"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_all_rejects_review_packet_unchecked_risk():
    """accept_all=True rejects review_packet items that require explicit review."""
    output = DocumentOutput(
        id="out-doc",
        preview="A doc",
        kind="document",
        data=DocumentData(name="draft.md", doc_kind="draft", content="ready"),
    )
    report = _make_report([output])
    report.review_packet = ReviewPacket(
        packet_id="packet-1",
        execution_id=EXECUTION_ID,
        capability_id="cap-1",
        title="Review packet",
        summary="Contains review-required item",
        completion_status="complete",
        items=[
            ReviewPacketItem(
                item_id="packet-item-1",
                kind="document",
                title="Claim audit",
                summary="Unsupported claim needs explicit review.",
                risk={"level": "high", "reasons": ["unsupported claim"]},
                default_checked=False,
                can_commit=True,
            )
        ],
    )
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="explicit review/selection"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].upsert_prism_workspace_file.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_not_called()


@pytest.mark.asyncio
async def test_commit_explicit_selection_allows_bulk_unsafe_output():
    """accepted_ids preserves manual commit semantics for outputs unsafe for accept_all."""
    output = DecisionOutput(
        id="out-dec",
        preview="A decision",
        kind="decision",
        data=DecisionData(key="approach", value="qualitative"),
    )
    report = _make_report([output])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-dec"],
        actor_user_id="user-1",
    )

    assert result["committed"]["decisions"] == 1
    assert result["commit_state"]["accepted_ids"] == ["out-dec"]
    mocks["dataservice"].set_room_decision.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()


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
        "sandbox": 0,
        "settings": 0,
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
async def test_undo_commit_marks_sandbox_and_settings_targets_as_manual_revert():
    """Rooms without automatic reverse APIs are explicit skipped targets."""
    report = _make_report([])
    execution = _make_execution(report)
    execution.result["commit_state"] = {
        "status": "committed",
        "accepted_ids": [],
        "rejected_ids": [],
        "accepted_unit_ids": ["review-artifact-1", "review-settings-1"],
        "counts": {
            "library": 0,
            "prism": 0,
            "memory": 0,
            "decisions": 0,
            "tasks": 0,
            "sandbox": 1,
            "settings": 1,
        },
        "room_targets": {
            "library": [],
            "prism": [],
            "memory": [],
            "decisions": [],
            "tasks": [],
            "sandbox": [
                {
                    "output_id": "review-artifact-1",
                    "item_id": "artifact-1",
                    "unit_id": "review-artifact-1",
                }
            ],
            "settings": [
                {
                    "output_id": "review-settings-1",
                    "item_id": WORKSPACE_ID,
                    "unit_id": "review-settings-1",
                    "settings_keys": "write_mode",
                }
            ],
        },
        "committed_at": "2026-06-29T00:00:00+00:00",
    }
    svc, mocks = _make_service(execution)

    result = await svc.undo_commit(
        EXECUTION_ID,
        actor_user_id="user-1",
    )

    reverted_state = result["commit_state"]
    assert reverted_state["status"] == "reverted"
    assert reverted_state["revert_counts"]["sandbox"] == 0
    assert reverted_state["revert_counts"]["settings"] == 0
    assert reverted_state["revert_skipped"] == {
        "sandbox": [
            {
                "output_id": "review-artifact-1",
                "item_id": "artifact-1",
                "unit_id": "review-artifact-1",
                "reason": "manual_revert_required",
            }
        ],
        "settings": [
            {
                "output_id": "review-settings-1",
                "item_id": WORKSPACE_ID,
                "unit_id": "review-settings-1",
                "settings_keys": "write_mode",
                "reason": "manual_revert_required",
            }
        ],
    }
    mocks["dataservice"].delete_source.assert_not_called()
    mocks["dataservice"].delete_room_decision.assert_not_called()
    mocks["dataservice"].delete_room_task.assert_not_called()


@pytest.mark.asyncio
async def test_commit_rejects_duplicate_claim_before_room_writes_without_redis():
    """The DB-backed commit claim must be the production concurrency guard."""
    outputs = _bulk_safe_outputs()
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
    outputs = _bulk_safe_outputs()
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
        "sandbox": 0,
        "settings": 0,
    }
    mocks["execution"].finalize_execution_commit.assert_not_called()
    mocks["execution"].update_execution.assert_not_called()


@pytest.mark.asyncio
async def test_commit_rejects_previous_failed_claim_before_room_writes():
    outputs = _bulk_safe_outputs()
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
    outputs = _bulk_safe_outputs()
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
            "sandbox": 0,
            "settings": 0,
        },
        "room_targets": {
            "prism": [],
            "library": [],
            "memory": [],
            "decisions": [],
            "tasks": [],
            "sandbox": [],
            "settings": [],
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
        accepted_ids=["out-lib"],
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
            accepted_ids=["out-lib"],
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
    outputs = _bulk_safe_outputs()
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
    outputs = _bulk_safe_outputs()
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
            "sandbox": 0,
            "settings": 0,
        },
        "room_targets": {
            "prism": [],
            "library": [{"output_id": "out-lib", "item_id": "lib-1"}],
            "memory": [],
            "decisions": [],
            "tasks": [],
            "sandbox": [],
            "settings": [],
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
            "sandbox": 0,
            "settings": 0,
        },
        "room_targets": {
            "library": [],
            "prism": [{"output_id": "out-doc", "item_id": "prism-file-1"}],
            "memory": [],
            "decisions": [],
            "tasks": [],
            "sandbox": [],
            "settings": [],
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
async def test_commit_rejects_workspace_non_member_before_room_writes():
    """Execution owners removed from the workspace cannot write room data."""
    report = _make_report(_all_kinds_outputs())
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)
    mocks["dataservice"].workspace_has_active_membership.return_value = False

    with pytest.raises(ExecutionCommitNotFoundError, match="not found"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            actor_user_id="user-1",
        )

    mocks["execution"].claim_execution_commit.assert_not_called()
    mocks["dataservice"].import_source.assert_not_called()
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

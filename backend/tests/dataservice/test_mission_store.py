"""High-value transaction tests for the canonical MissionStore."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.contracts.mission_write_authority import MissionWriteAuthority
from src.contracts.stage_acceptance import StageAcceptanceContract
from src.contracts.subagent_progress import subagent_progress_sha256
from src.database.models.credit_reservation import CreditReservation
from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.dataservice.common.errors import (
    DataServiceConflictError,
    DataServiceValidationError,
)
from src.dataservice.domains.mission._store_core import (
    _project_stage_instance_ids,
    _stage_projection_title,
)
from src.dataservice.domains.mission.service import (
    MissionProjectionStaleError,
    MissionStore,
)
from src.dataservice.domains.mission.write_authority import assert_active_mission_write
from src.dataservice_client.contracts.mission import (
    MAX_MISSION_SNAPSHOT_BYTES,
    MissionAppendPayload,
    MissionApplyCommandsPayload,
    MissionCheckpointPayload,
    MissionCommitCreatePayload,
    MissionCommitFinishPayload,
    MissionCommitStartPayload,
    MissionCreatePayload,
    MissionItemDraftPayload,
    MissionLeaseClaimPayload,
    MissionLeaseReleasePayload,
    MissionOperationClaimPayload,
    MissionOperationFinishPayload,
    MissionPausePayload,
    MissionPreviewCleanupPayload,
    MissionResumePayload,
    MissionReviewDecisionPayload,
    MissionReviewDecisionsPayload,
    MissionReviewItemDraftPayload,
    MissionReviewItemsCreatePayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPatchPayload,
    MissionSemanticReferencePayload,
    MissionStatus,
    MissionUserCommandPayload,
)

MISSION_TABLES = [
    MissionRunRecord.__table__,
    CreditReservation.__table__,
    MissionItemRecord.__table__,
    MissionReviewItemRecord.__table__,
    MissionCommitRecord.__table__,
]

_MISSION_POLICY_SNAPSHOT = {
    "execution_budget": {
        "max_model_calls": 1_000,
        "max_tool_operations": 1_000,
        "max_subagent_jobs": 100,
        "stop_after_total_tokens": 10_000_000,
    }
}
_ZERO_RESOURCE_USAGE = {
    "model_calls": 0,
    "tool_operations": 0,
    "subagent_jobs": 0,
    "input_tokens": 0,
    "cached_input_tokens": 0,
    "output_tokens": 0,
    "reasoning_tokens": 0,
    "total_tokens": 0,
}


def _model_call_started(
    model_call_id: str,
    *,
    producer: str = "workspace_agent",
    stage_id: str | None = None,
    turn: int = 1,
    attempt: int = 1,
    parent_operation_id: str | None = None,
    job_id: str | None = None,
) -> MissionItemDraftPayload:
    payload = {
        "model_call_id": model_call_id,
        "model_id": "gpt-5.6-sol",
        "turn": turn,
        "attempt": attempt,
    }
    if parent_operation_id is not None or job_id is not None:
        payload.update(
            {
                "parent_operation_id": parent_operation_id,
                "job_id": job_id,
            }
        )
    return MissionItemDraftPayload(
        item_type="model_call_started",
        operation_id=model_call_id,
        phase="started",
        stage_id=stage_id,
        producer=producer,
        summary=(
            "Workspace Agent model call started"
            if producer == "workspace_agent"
            else "Subagent model call started"
        ),
        payload_json=payload,
    )


def _model_usage_receipt(
    model_call_id: str,
    *,
    usage: dict[str, int],
    producer: str = "workspace_agent",
    stage_id: str | None = None,
    turn: int = 1,
    attempt: int = 1,
    parent_operation_id: str | None = None,
    job_id: str | None = None,
    provider_response_id: str | None = None,
) -> MissionItemDraftPayload:
    payload = {
        "model_call_id": model_call_id,
        "model_id": "gpt-5.6-sol",
        "turn": turn,
        "attempt": attempt,
        "usage": usage,
        "provider_response_id": provider_response_id,
    }
    if parent_operation_id is not None or job_id is not None:
        payload.update(
            {
                "parent_operation_id": parent_operation_id,
                "job_id": job_id,
            }
        )
    return MissionItemDraftPayload(
        item_type="usage_receipt",
        operation_id=model_call_id,
        phase="completed",
        stage_id=stage_id,
        producer=producer,
        summary=(
            "Workspace Agent model usage recorded"
            if producer == "workspace_agent"
            else "Subagent model usage recorded"
        ),
        payload_json=payload,
    )


def _model_call_terminal(
    model_call_id: str,
    *,
    outcome: str = "unresolved",
    producer: str = "workspace_agent",
    stage_id: str | None = None,
    turn: int = 1,
    attempt: int = 1,
    parent_operation_id: str | None = None,
    job_id: str | None = None,
) -> MissionItemDraftPayload:
    payload = {
        "model_call_id": model_call_id,
        "model_id": "gpt-5.6-sol",
        "turn": turn,
        "attempt": attempt,
        "outcome": outcome,
        "error_type": "ProviderTransportError",
        "detail": "Provider usage could not be confirmed",
    }
    if parent_operation_id is not None or job_id is not None:
        payload.update(
            {
                "parent_operation_id": parent_operation_id,
                "job_id": job_id,
            }
        )
    return MissionItemDraftPayload(
        item_type="model_call_terminal",
        operation_id=model_call_id,
        phase="cancelled" if outcome == "cancelled" else "failed",
        stage_id=stage_id,
        producer=producer,
        summary=f"Model call {outcome}",
        payload_json=payload,
    )


def _subagent_terminal_progress(
    *,
    operation_id: str,
    job_id: str,
    result_version: int,
    summary: str | None = None,
    display_name: str = "终态核验员",
    role_label: str = "终态核验",
    status: str = "completed",
) -> MissionItemDraftPayload:
    summary = summary or f"Subagent terminal version {result_version}"
    payload = {
        "job_id": job_id,
        "display_name": display_name,
        "role_label": role_label,
        "lifecycle_phase": "terminal",
        "job_fingerprint": "a" * 64,
        "status": status,
        "public_summary": summary,
        "frozen_budget": {
            "max_turns": 1,
            "max_tool_steps": 1,
            "max_context_bytes": 4096,
            "max_result_bytes": 4096,
        },
        "result": {"version": result_version},
    }
    progress_hash = subagent_progress_sha256(
        summary=summary,
        payload_json=payload,
    )
    payload.update(
        {
            "progress_id": f"subagent-terminal:{job_id}",
            "progress_sha256": progress_hash,
        }
    )
    return MissionItemDraftPayload(
        item_type="subagent_progress",
        operation_id=operation_id,
        phase="completed",
        stage_id="literature",
        producer=job_id,
        summary=summary,
        payload_json=payload,
    )


def _subagent_spawned(operation_id: str) -> MissionItemDraftPayload:
    return MissionItemDraftPayload(
        item_type="subagent_spawned",
        operation_id=operation_id,
        phase="started",
        stage_id="literature",
        producer="workspace_agent",
        summary="Subagent batch started",
        payload_json={"input_scope": {"jobs": []}},
    )


def _subagent_live_progress(
    *,
    operation_id: str,
    job_id: str,
    summary: str,
    progress_kind: str = "formula",
) -> MissionItemDraftPayload:
    payload = {
        "job_id": job_id,
        "display_name": "公式核验员",
        "role_label": "建模推导",
        "lifecycle_phase": "progress",
        "job_fingerprint": "b" * 64,
        "status": "milestone",
        "progress_kind": progress_kind,
        "public_summary": summary,
    }
    progress_hash = subagent_progress_sha256(
        summary=summary,
        payload_json=payload,
    )
    payload.update(
        {
            "progress_id": f"subagent-progress:{progress_hash}",
            "progress_sha256": progress_hash,
        }
    )
    return MissionItemDraftPayload(
        item_type="subagent_progress",
        operation_id=operation_id,
        phase="progress",
        stage_id="question_1_model",
        producer=job_id,
        summary=summary,
        payload_json=payload,
    )


def _subagent_internal_progress(
    *,
    operation_id: str,
    job_id: str,
    summary: str,
) -> MissionItemDraftPayload:
    payload = {
        "job_id": job_id,
        "display_name": "公式核验员",
        "role_label": "建模推导",
        "lifecycle_phase": "progress",
        "job_fingerprint": "b" * 64,
        "status": "output_contract_retry",
    }
    progress_hash = subagent_progress_sha256(
        summary=summary,
        payload_json=payload,
    )
    payload.update(
        {
            "progress_id": f"subagent-progress:{progress_hash}",
            "progress_sha256": progress_hash,
        }
    )
    return MissionItemDraftPayload(
        item_type="subagent_progress",
        operation_id=operation_id,
        phase="progress",
        stage_id="question_1_model",
        producer=job_id,
        summary=summary,
        payload_json=payload,
    )


def _per_item_stage_contract(stage_id: str, template: str) -> StageAcceptanceContract:
    return StageAcceptanceContract.model_validate(
        {
            "schema_version": "stage_acceptance_contract.v2",
            "contract_id": f"math.{stage_id}",
            "version": 1,
            "mission_policy_id": "math",
            "workspace_type": "math_modeling",
            "stage_id": stage_id,
            "stage_goal": "Complete one question stage.",
            "minimum_criteria": [{"criterion_id": "complete", "description": "The stage is complete."}],
            "allowed_actions_if_failed": ["revise_existing", "stop_execution"],
            "instantiation": {
                "mode": "per_item",
                "source_context_key": "problem_questions",
                "instance_id_template": template,
            },
            "advance_condition": "The stage passes.",
            "stop_condition": "The stage cannot be repaired.",
        }
    )


def test_stage_projection_replaces_per_item_families_with_observed_instances() -> None:
    contracts = (
        _per_item_stage_contract("question_model", "question_{index}_model"),
        _per_item_stage_contract(
            "question_solution_validation",
            "question_{index}_solution_validation",
        ),
    )

    projected = _project_stage_instance_ids(
        [
            "problem_understanding",
            "question_model",
            "question_solution_validation",
            "paper_integration",
        ],
        observed_ids=[
            "question_1_model",
            "question_1_solution_validation",
            "question_2_model",
            "question_2_solution_validation",
        ],
        contracts=contracts,
    )

    assert projected == [
        "problem_understanding",
        "question_1_model",
        "question_1_solution_validation",
        "question_2_model",
        "question_2_solution_validation",
        "paper_integration",
    ]
    assert (
        _stage_projection_title(
            workspace_type="math_modeling",
            stage_id="question_1_solution_validation",
            contracts=contracts,
        )
        == "第 1 问求解与验证"
    )


def test_stage_projection_expands_every_pinned_item_before_it_is_observed() -> None:
    contracts = (
        _per_item_stage_contract("question_model", "question_{index}_model"),
        _per_item_stage_contract(
            "question_solution_validation",
            "question_{index}_solution_validation",
        ),
    )

    projected = _project_stage_instance_ids(
        [
            "problem_understanding",
            "question_model",
            "question_solution_validation",
            "paper_integration",
        ],
        observed_ids=["question_1_model"],
        contracts=contracts,
        item_counts={"problem_questions": 3},
    )

    assert projected == [
        "problem_understanding",
        "question_1_model",
        "question_1_solution_validation",
        "question_2_model",
        "question_2_solution_validation",
        "question_3_model",
        "question_3_solution_validation",
        "paper_integration",
    ]


@pytest.mark.asyncio
async def test_mission_view_preserves_dynamic_stage_while_waiting_for_review(
    mission_session: AsyncSession,
) -> None:
    contracts = (
        _per_item_stage_contract("question_model", "question_{index}_model"),
        _per_item_stage_contract(
            "question_solution_validation",
            "question_{index}_solution_validation",
        ),
    )
    payload = _create_payload(
        thread_id="thread-dynamic-stage-review",
        idempotency_key="dynamic-stage-review",
    ).model_copy(
        update={
            "workspace_type": "math_modeling",
            "mission_policy_id": "math_modeling_solution",
            "snapshot_json": {
                "stage_item_counts": {"problem_questions": 3},
                "stage_acceptance": {
                    "question_1_model": {"result": "pass"},
                }
            },
                "runtime_context_json": {
                    "mission_policy_snapshot": _MISSION_POLICY_SNAPSHOT,
                    "required_stage_ids": [
                    "problem_understanding",
                    "question_model",
                    "question_solution_validation",
                    "paper_integration",
                ],
                "stage_contracts": {contract.stage_id: contract.model_dump(mode="json") for contract in contracts},
            },
        }
    )
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(payload)
    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=created.mission.state_version,
    )
    appended = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="tool_result",
                    phase="completed",
                    stage_id="question_1_solution_validation",
                    summary="Validated baseline result.",
                )
            ],
        ),
    )
    source_seq = appended.items[0].seq
    staged = await store.create_review_items(
        created.mission.mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=appended.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    source_item_seq=source_seq,
                    output_key="question_1_solution",
                    target_kind="artifact",
                    target_room="documents",
                    title="问题 1 可复现求解包",
                    risk_level="medium",
                    preview_json={"summary": "D=120 基准求解与验证。"},
                )
            ],
        ),
    )

    view = await store.get_view(staged.mission.mission_id)

    assert view is not None
    assert view.required_stage_ids == [
        "problem_understanding",
        "question_1_model",
        "question_1_solution_validation",
        "question_2_model",
        "question_2_solution_validation",
        "question_3_model",
        "question_3_solution_validation",
        "paper_integration",
    ]
    assert [stage.title for stage in view.stage_summaries] == [
        "题目理解",
        "第 1 问建模",
        "第 1 问求解与验证",
        "第 2 问建模",
        "第 2 问求解与验证",
        "第 3 问建模",
        "第 3 问求解与验证",
        "论文整合",
    ]


@pytest_asyncio.fixture
async def mission_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: MissionRunRecord.metadata.create_all(sync_connection, tables=MISSION_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _create_payload(
    *,
    thread_id: str = "thread-1",
    idempotency_key: str = "mission-create-1",
) -> MissionCreatePayload:
    return MissionCreatePayload(
        workspace_id="workspace-1",
        thread_id=thread_id,
        user_id="user-1",
        workspace_type="sci",
        mission_policy_id="sci.research",
        title="Federated LLM research gap",
        objective="Identify a defensible research gap with evidence.",
        model_id="gpt-5.6-sol",
        reasoning_effort="xhigh",
        snapshot_json={"plan_summary": "Scope the literature."},
        runtime_context_json={
            "policy_ref": "policy-v1",
            "mission_policy_snapshot": _MISSION_POLICY_SNAPSHOT,
        },
        mission_idempotency_key=idempotency_key,
    )


async def _created(store: MissionStore, **kwargs: str) -> str:
    result = await store.create_run(_create_payload(**kwargs))
    return result.mission.mission_id


async def _claim(store: MissionStore, mission_id: str, *, version: int, worker: str = "worker-1"):
    return await store.claim_run_lease(
        mission_id,
        MissionLeaseClaimPayload(
            worker_id=worker,
            expected_state_version=version,
            ttl_seconds=120,
        ),
    )


async def _cancel_at_boundary(
    store: MissionStore,
    mission_id: str,
    *,
    request_id: str,
    reason: str,
):
    queued = await store.append_command_once(
        mission_id,
        MissionUserCommandPayload(
            command_id=request_id,
            command_type="cancel",
            summary=reason,
            payload_json={"reason": reason},
        ),
    )
    claimed = await _claim(store, mission_id, version=queued.mission.state_version)
    return await store.apply_commands_and_advance_cursor(
        mission_id,
        MissionApplyCommandsPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            through_command_seq=queued.mission.last_command_seq,
            patch=MissionRunPatchPayload(status="cancelled"),
        ),
    )


@pytest.mark.asyncio
async def test_mission_stats_aggregate_only_mission_runs(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    first = await store.create_run(_create_payload(thread_id="thread-stats-1", idempotency_key="stats-1"))
    second = await store.create_run(_create_payload(thread_id="thread-stats-2", idempotency_key="stats-2"))
    await mission_session.execute(update(MissionRunRecord).where(MissionRunRecord.mission_id == first.mission.mission_id).values(status="completed", next_wakeup_at=None))
    await mission_session.execute(update(MissionRunRecord).where(MissionRunRecord.mission_id == second.mission.mission_id).values(status="failed", next_wakeup_at=None))
    await mission_session.commit()

    result = await store.aggregate_stats(
        created_since=datetime.now(UTC) - timedelta(days=1),
        granularity="day",
    )

    assert result.kpis.model_dump() == {
        "total": 2,
        "success": 1,
        "failed": 1,
        "success_rate": 0.5,
    }
    assert result.by_workspace_type[0].model_dump() == {"type": "sci", "count": 2}
    assert result.time_series[0].by_status == {"completed": 1, "failed": 1}


@pytest.mark.asyncio
async def test_workspace_summary_aggregates_all_runs_without_history_page_limits(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    first = await store.create_run(_create_payload(thread_id="thread-summary-1", idempotency_key="summary-1"))
    await mission_session.execute(
        update(MissionRunRecord)
        .where(MissionRunRecord.mission_id == first.mission.mission_id)
        .values(
            status="completed",
            pending_review_count=2,
            evidence_count=5,
            artifact_count=3,
            next_wakeup_at=None,
        )
    )
    second = await store.create_run(_create_payload(thread_id="thread-summary-2", idempotency_key="summary-2"))
    await mission_session.execute(update(MissionRunRecord).where(MissionRunRecord.mission_id == second.mission.mission_id).values(evidence_count=4, artifact_count=1))
    await mission_session.commit()

    summary = await store.get_workspace_summary(
        workspace_id="workspace-1",
        user_id="user-1",
    )

    assert summary.total == 2
    assert summary.status_counts == {"completed": 1, "created": 1}
    assert summary.pending_review_count == 2
    assert summary.evidence_count == 9
    assert summary.artifact_count == 4
    assert summary.active is not None
    assert summary.active.mission_id == second.mission.mission_id
    assert summary.latest is not None


@pytest.mark.asyncio
async def test_user_summary_aggregates_all_runs_and_bounds_recent_projection(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    first = await store.create_run(_create_payload(thread_id="thread-user-summary-1", idempotency_key="user-summary-1"))
    second = await store.create_run(_create_payload(thread_id="thread-user-summary-2", idempotency_key="user-summary-2"))
    await mission_session.execute(update(MissionRunRecord).where(MissionRunRecord.mission_id == first.mission.mission_id).values(status="completed", next_wakeup_at=None))
    await mission_session.commit()

    summary = await store.get_user_summary(user_id="user-1", recent_limit=1)

    assert summary.total == 2
    assert summary.status_counts == {"completed": 1, "created": 1}
    assert len(summary.recent) == 1
    assert summary.recent[0].mission_id in {
        first.mission.mission_id,
        second.mission.mission_id,
    }


@pytest.mark.asyncio
async def test_review_mode_command_is_ordered_before_runtime_applies_it(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(_create_payload())

    result = await store.append_command_once(
        created.mission.mission_id,
        MissionUserCommandPayload(
            command_id="review-mode-1",
            command_type="set_review_mode",
            payload_json={"review_mode": "review_all"},
        ),
    )

    assert result.mission.review_mode.value == "balanced_default"
    assert result.mission.last_applied_command_seq < result.mission.last_command_seq
    assert result.mission.next_wakeup_at is not None

    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=result.mission.state_version,
    )
    applied = await store.apply_commands_and_advance_cursor(
        created.mission.mission_id,
        MissionApplyCommandsPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            through_command_seq=result.mission.last_command_seq,
            patch=MissionRunPatchPayload(review_mode="review_all"),
        ),
    )
    assert applied.mission.review_mode.value == "review_all"
    assert applied.mission.last_applied_command_seq == applied.mission.last_command_seq


@pytest.mark.asyncio
async def test_prism_command_is_rejected_before_persistence_when_workspace_differs(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(_create_payload())
    command = MissionUserCommandPayload(
        command_id="prism-command-1",
        command_type="instruction",
        payload_json={
            "prism_context_ref": {
                "workspace_id": "another-workspace",
                "prism_project_id": "project-1",
                "file_id": "file-1",
                "base_revision_ref": "revision-1",
                "selection_hash": f"sha256:{'a' * 64}",
                "selection_byte_range": [0, 1],
            }
        },
    )

    with pytest.raises(DataServiceValidationError, match="Mission workspace"):
        await store.append_command_once(created.mission.mission_id, command)

    unchanged = await store.load_run_snapshot(created.mission.mission_id)
    assert unchanged is not None
    assert unchanged.last_command_seq == 0


@pytest.mark.asyncio
async def test_resume_requires_exact_pending_request_id(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(_create_payload())
    claimed = await store.claim_run_lease(
        created.mission.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            expected_state_version=created.mission.state_version,
        ),
    )
    await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    paused = await store.pause_run(
        created.mission.mission_id,
        MissionPausePayload(
            request_id="request-1",
            reason="permission",
            pending_request={"request_id": "request-1"},
        ),
    )

    with pytest.raises(DataServiceConflictError, match="does not match"):
        await store.resume_run(
            created.mission.mission_id,
            MissionResumePayload(request_id="request-2"),
        )

    resumed = await store.resume_run(
        created.mission.mission_id,
        MissionResumePayload(request_id="request-1", input_json={"decision": "allow_once"}),
    )
    assert paused.mission.status.value == "waiting"
    assert resumed.mission.status.value == "planning"


@pytest.mark.asyncio
async def test_mission_view_keeps_execution_and_review_axes_separate_and_cleans_preview(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(_create_payload())
    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=created.mission.state_version,
    )
    planning = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    staged = await store.create_review_items(
        created.mission.mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=planning.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    output_key="draft",
                    target_kind="document",
                    target_room="documents",
                    title="Draft",
                    risk_level="medium",
                    preview_json={"diff": "temporary"},
                    preview_ref="mpv1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    preview_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            ],
        ),
    )
    running = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=staged.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    completed = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=running.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="completed"),
        ),
    )
    assert completed.mission.status.value == "completed"
    view = await store.get_view(created.mission.mission_id)
    assert view is not None
    assert view.review_summary.pending == 1
    assert view.mission.pending_review_count == 1
    assert view.review_items[0].preview_ref is None
    assert view.review_items[0].commit_block_reason == "review_item_not_accepted"

    cleaned = await store.cleanup_expired_previews(MissionPreviewCleanupPayload(now=datetime.now(UTC)))
    assert cleaned.preview_refs == ["mpv1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    remaining = await store.list_review_items(created.mission.mission_id)
    assert remaining[0].preview_json == {}
    assert remaining[0].preview_hash is not None


@pytest.mark.asyncio
async def test_one_foreground_mission_per_thread_and_idempotent_create(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(_create_payload())
    replay = await store.create_run(_create_payload())

    assert created.created is True
    assert replay.created is False
    assert replay.mission.mission_id == created.mission.mission_id

    divergent = _create_payload().model_copy(update={"model_id": "other-model"})
    with pytest.raises(DataServiceConflictError, match="idempotency key"):
        await store.create_run(divergent)

    with pytest.raises(DataServiceConflictError, match="foreground"):
        await store.create_run(_create_payload(idempotency_key="mission-create-2"))

    await _cancel_at_boundary(
        store,
        created.mission.mission_id,
        request_id="cancel-1",
        reason="Replace the task",
    )
    replacement = await store.create_run(_create_payload(idempotency_key="mission-create-2"))
    assert replacement.created is True


@pytest.mark.asyncio
async def test_latest_mission_for_thread_includes_terminal_run(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    created = await store.create_run(_create_payload())
    await _cancel_at_boundary(
        store,
        created.mission.mission_id,
        request_id="cancel-latest",
        reason="Pause here",
    )

    latest = await store.latest_for_thread(
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
    )
    hidden = await store.latest_for_thread(
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="another-user",
    )

    assert latest is not None
    assert latest.mission_id == created.mission.mission_id
    assert latest.status.value == "cancelled"
    assert hidden is None


@pytest.mark.asyncio
async def test_append_allocates_ordered_immutable_items_and_updates_snapshot_once(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)

    result = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(item_type="plan", phase="completed", summary="Plan accepted"),
                MissionItemDraftPayload(
                    item_type="stage_started",
                    phase="started",
                    stage_id="literature",
                ),
            ],
            snapshot_json={"plan_summary": "Literature first."},
            patch=MissionRunPatchPayload(status="planning", active_stage_id="literature"),
        ),
    )

    assert [item.seq for item in result.items] == [1, 2]
    assert result.mission.last_item_seq == 2
    assert result.mission.state_version == claimed.state_version + 1
    assert result.mission.snapshot_json == {
        "plan_summary": "Literature first.",
        "resource_usage": _ZERO_RESOURCE_USAGE,
    }

    checkpoint = await store.checkpoint_run(
        mission_id,
        MissionCheckpointPayload(
            expected_state_version=result.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=result.mission.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="context_checkpoint",
                    phase="completed",
                    payload_ref="trace://checkpoint-1",
                )
            ],
            snapshot_json={"context_checkpoint_summary": "Stage state compacted."},
            patch=MissionRunPatchPayload(context_checkpoint_ref="trace://checkpoint-1"),
        ),
    )
    assert checkpoint.mission.context_checkpoint_ref == "trace://checkpoint-1"
    assert checkpoint.items[0].seq == 3

    result.items[0].payload_json["client_only"] = True
    persisted = await store.list_items_page(mission_id)
    assert "client_only" not in persisted[0].payload_json
    selected = await store.list_items_by_seqs(mission_id, seqs=(1, 3))
    assert [item.seq for item in selected] == [1, 3]
    assert [item.item_type for item in selected] == ["plan", "context_checkpoint"]
    first_page = await store.get_items_page(mission_id, limit=2)
    assert [item.seq for item in first_page.items] == [1, 2]
    assert first_page.page.total == 3
    assert first_page.page.next_cursor == 2
    second_page = await store.get_items_page(
        mission_id,
        after_seq=first_page.page.next_cursor,
        limit=2,
    )
    assert [item.seq for item in second_page.items] == [3]
    assert second_page.page.next_cursor is None


@pytest.mark.asyncio
async def test_append_projects_cumulative_mission_resource_usage(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    payload = _create_payload(
        thread_id="thread-resource-usage",
        idempotency_key="resource-usage",
    ).model_copy(
        update={
            "runtime_context_json": {
                "policy_ref": "policy-v1",
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 3,
                        "max_tool_operations": 1,
                        "max_subagent_jobs": 2,
                        "stop_after_total_tokens": 100,
                    }
                },
            }
        }
    )
    created = await store.create_run(payload)
    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=created.mission.state_version,
    )

    result = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _model_call_started("model-call:workspace:resource-usage"),
                MissionItemDraftPayload(
                    item_type="operation_claim",
                    phase="started",
                ),
                MissionItemDraftPayload(
                    item_type="subagent_spawned",
                    phase="started",
                    payload_json={"input_scope": {"jobs": [{}, {}]}},
                ),
                _model_usage_receipt(
                    "model-call:workspace:resource-usage",
                    usage={
                        "input_tokens": 40,
                        "cached_input_tokens": 10,
                        "output_tokens": 20,
                        "reasoning_tokens": 5,
                        "total_tokens": 60,
                    },
                ),
            ],
        ),
    )

    assert result.mission.snapshot_json["resource_usage"] == {
        "model_calls": 1,
        "tool_operations": 1,
        "subagent_jobs": 2,
        "input_tokens": 40,
        "cached_input_tokens": 10,
        "output_tokens": 20,
        "reasoning_tokens": 5,
        "total_tokens": 60,
    }


@pytest.mark.asyncio
async def test_resource_budget_preflights_the_complete_item_batch(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    payload = _create_payload(
        thread_id="thread-resource-preflight",
        idempotency_key="resource-preflight",
    ).model_copy(
        update={
            "runtime_context_json": {
                "policy_ref": "policy-v1",
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 1,
                        "max_tool_operations": 1,
                        "max_subagent_jobs": 1,
                        "stop_after_total_tokens": 100,
                    }
                },
            }
        }
    )
    created = await store.create_run(payload)
    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=created.mission.state_version,
    )

    with pytest.raises(
        DataServiceValidationError,
        match="execution budget is exhausted",
    ):
        await store.append_items_and_update_snapshot(
            created.mission.mission_id,
            MissionAppendPayload(
                expected_state_version=claimed.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    _model_call_started("model-call:workspace:preflight-1"),
                    _model_call_started("model-call:workspace:preflight-2"),
                ],
            ),
        )

    persisted = await store.load_run_snapshot(created.mission.mission_id)
    assert persisted is not None
    assert persisted.last_item_seq == 0
    assert persisted.snapshot_json["resource_usage"] == _ZERO_RESOURCE_USAGE
    assert await store.list_items_page(created.mission.mission_id) == []


@pytest.mark.asyncio
async def test_token_overage_is_recorded_but_blocks_only_future_dispatch(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    payload = _create_payload(
        thread_id="thread-token-overage",
        idempotency_key="token-overage",
    ).model_copy(
        update={
            "runtime_context_json": {
                "policy_ref": "policy-v1",
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 2,
                        "max_tool_operations": 1,
                        "max_subagent_jobs": 1,
                        "stop_after_total_tokens": 100,
                    }
                },
            }
        }
    )
    created = await store.create_run(payload)
    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=created.mission.state_version,
    )
    recorded = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _model_call_started("model-call:workspace:token-overage"),
                _model_usage_receipt(
                    "model-call:workspace:token-overage",
                    usage={
                        "input_tokens": 80,
                        "output_tokens": 40,
                        "total_tokens": 120,
                    },
                ),
                MissionItemDraftPayload(
                    item_type="error",
                    phase="failed",
                    summary="Token ceiling crossed after provider completion",
                ),
            ],
        ),
    )
    assert recorded.mission.snapshot_json["resource_usage"]["total_tokens"] == 120

    with pytest.raises(DataServiceValidationError) as exc_info:
        await store.append_items_and_update_snapshot(
            created.mission.mission_id,
            MissionAppendPayload(
                expected_state_version=recorded.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    MissionItemDraftPayload(
                        item_type="operation_claim",
                        phase="started",
                    )
                ],
            ),
        )
    assert exc_info.value.detail["dimensions"] == ["total_tokens"]


@pytest.mark.asyncio
async def test_token_threshold_equality_blocks_the_next_model_dispatch(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    payload = _create_payload(
        thread_id="thread-token-threshold",
        idempotency_key="token-threshold",
    ).model_copy(
        update={
            "runtime_context_json": {
                "policy_ref": "policy-v1",
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 2,
                        "max_tool_operations": 1,
                        "max_subagent_jobs": 1,
                        "stop_after_total_tokens": 100,
                    }
                },
            }
        }
    )
    created = await store.create_run(payload)
    claimed = await _claim(
        store,
        created.mission.mission_id,
        version=created.mission.state_version,
    )
    recorded = await store.append_items_and_update_snapshot(
        created.mission.mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _model_call_started("model-call:workspace:threshold-1"),
                _model_usage_receipt(
                    "model-call:workspace:threshold-1",
                    usage={
                        "input_tokens": 60,
                        "output_tokens": 40,
                        "total_tokens": 100,
                    },
                ),
            ],
        ),
    )

    with pytest.raises(DataServiceValidationError) as exc_info:
        await store.append_items_and_update_snapshot(
            created.mission.mission_id,
            MissionAppendPayload(
                expected_state_version=recorded.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    _model_call_started("model-call:workspace:threshold-2")
                ],
            ),
        )

    assert exc_info.value.detail["dimensions"] == ["total_tokens"]
    persisted = await store.load_run_snapshot(created.mission.mission_id)
    assert persisted is not None
    assert persisted.snapshot_json["resource_usage"]["model_calls"] == 1


@pytest.mark.asyncio
async def test_model_ledger_replay_is_adopted_atomically_under_the_run_lock(
    mission_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-model-ledger-replay",
        idempotency_key="model-ledger-replay",
    )
    claimed = await _claim(store, mission_id, version=0)
    real_get_run = store.repository.get_run
    lock_observations: list[bool] = []

    async def tracked_get_run(
        candidate_mission_id: str,
        *,
        for_update: bool = False,
        skip_locked: bool = False,
    ):
        lock_observations.append(for_update)
        return await real_get_run(
            candidate_mission_id,
            for_update=for_update,
            skip_locked=skip_locked,
        )

    monkeypatch.setattr(store.repository, "get_run", tracked_get_run)
    model_call_id = "model-call:workspace:atomic-replay"
    started = _model_call_started(model_call_id)
    started_command = MissionAppendPayload(
        expected_state_version=claimed.state_version,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        items=[started],
    )

    first_started = await store.append_items_and_update_snapshot(
        mission_id,
        started_command,
    )
    replayed_started = await store.append_items_and_update_snapshot(
        mission_id,
        started_command,
    )
    receipt = _model_usage_receipt(
        model_call_id,
        usage={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        provider_response_id="provider-response-atomic",
    )
    receipt_command = MissionAppendPayload(
        expected_state_version=first_started.mission.state_version,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        items=[receipt],
    )
    first_receipt = await store.append_items_and_update_snapshot(
        mission_id,
        receipt_command,
    )
    replayed_receipt = await store.append_items_and_update_snapshot(
        mission_id,
        receipt_command,
    )
    assert lock_observations == [True, True, True, True]

    items = await store.list_items_page(
        mission_id,
        operation_id=model_call_id,
        limit=10,
    )
    assert replayed_started.mission.state_version == first_started.mission.state_version
    assert replayed_started.items[0].id == first_started.items[0].id
    assert replayed_receipt.mission.state_version == first_receipt.mission.state_version
    assert replayed_receipt.items[0].id == first_receipt.items[0].id
    assert [item.item_type for item in items] == [
        "model_call_started",
        "usage_receipt",
    ]
    assert first_receipt.mission.snapshot_json["resource_usage"] == {
        **_ZERO_RESOURCE_USAGE,
        "model_calls": 1,
        "input_tokens": 12,
        "output_tokens": 3,
        "total_tokens": 15,
    }


@pytest.mark.asyncio
async def test_subagent_terminal_progress_replay_is_atomic_and_hash_bound(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-subagent-terminal-replay",
        idempotency_key="subagent-terminal-replay",
    )
    claimed = await _claim(store, mission_id, version=0)
    operation_id = "subagent-terminal-parent"
    job_id = "subagent-terminal-job"
    terminal = _subagent_terminal_progress(
        operation_id=operation_id,
        job_id=job_id,
        result_version=1,
    )
    command = MissionAppendPayload(
        expected_state_version=claimed.state_version,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        items=[terminal],
    )

    first = await store.append_items_and_update_snapshot(mission_id, command)
    replayed = await store.append_items_and_update_snapshot(mission_id, command)

    assert replayed.mission.state_version == first.mission.state_version
    assert replayed.items[0].id == first.items[0].id
    with pytest.raises(DataServiceConflictError, match="divergent content"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=first.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    _subagent_terminal_progress(
                        operation_id=operation_id,
                        job_id=job_id,
                        result_version=2,
                    )
                ],
            ),
        )
    items = await store.list_items_page(
        mission_id,
        item_type="subagent_progress",
        operation_id=operation_id,
        limit=10,
    )
    assert len(items) == 1
    assert items[0].payload_json["result"] == {"version": 1}


@pytest.mark.asyncio
async def test_usage_receipt_requires_complete_matching_started_semantics(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-receipt-semantics",
        idempotency_key="receipt-semantics",
    )
    claimed = await _claim(store, mission_id, version=0)
    model_call_id = "model-call:workspace:receipt-semantics"
    orphan = _model_usage_receipt(
        model_call_id,
        usage={"input_tokens": 8, "output_tokens": 2, "total_tokens": 10},
    )

    with pytest.raises(
        DataServiceValidationError,
        match="requires a matching started model call",
    ):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=claimed.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[orphan],
            ),
        )

    started = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[_model_call_started(model_call_id, turn=2, attempt=1)],
        ),
    )
    mismatched = _model_usage_receipt(
        model_call_id,
        turn=2,
        attempt=2,
        usage={"input_tokens": 8, "output_tokens": 2, "total_tokens": 10},
    )
    with pytest.raises(
        DataServiceValidationError,
        match="does not match its started model call",
    ):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=started.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[mismatched],
            ),
        )

    zero_usage = _model_usage_receipt(
        model_call_id,
        turn=2,
        usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    )
    with pytest.raises(
        DataServiceValidationError,
        match="model ledger payload is invalid",
    ):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=started.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[zero_usage],
            ),
        )

    current = await store.load_run_snapshot(mission_id)
    assert current is not None
    assert current.snapshot_json["resource_usage"]["model_calls"] == 1
    assert current.snapshot_json["resource_usage"]["total_tokens"] == 0


@pytest.mark.asyncio
async def test_nonreceipt_model_terminal_replay_is_adopted_and_immutable(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-model-terminal-replay",
        idempotency_key="model-terminal-replay",
    )
    claimed = await _claim(store, mission_id, version=0)
    model_call_id = "model-call:workspace:terminal-replay"
    started = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[_model_call_started(model_call_id)],
        ),
    )
    terminal_command = MissionAppendPayload(
        expected_state_version=started.mission.state_version,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        items=[_model_call_terminal(model_call_id)],
    )

    first = await store.append_items_and_update_snapshot(
        mission_id,
        terminal_command,
    )
    replayed = await store.append_items_and_update_snapshot(
        mission_id,
        terminal_command,
    )
    states = await store.list_model_call_states(mission_id)

    assert replayed.mission.state_version == first.mission.state_version
    assert replayed.items[0].id == first.items[0].id
    assert len(states) == 1
    assert states[0].state.value == "unresolved"
    assert states[0].terminal is not None
    assert states[0].terminal.id == first.items[0].id
    with pytest.raises(
        DataServiceConflictError,
        match="already has a terminal ledger item",
    ):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=first.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    _model_usage_receipt(
                        model_call_id,
                        usage={
                            "input_tokens": 8,
                            "output_tokens": 2,
                            "total_tokens": 10,
                        },
                    )
                ],
            ),
        )


@pytest.mark.asyncio
async def test_open_or_unresolved_model_call_blocks_progression_and_dispatch(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-model-call-gates",
        idempotency_key="model-call-gates",
    )
    claimed = await _claim(store, mission_id, version=0)
    model_call_id = "model-call:workspace:gated"
    started = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[_model_call_started(model_call_id)],
        ),
    )

    with pytest.raises(DataServiceConflictError, match="open model calls"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=started.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                patch=MissionRunPatchPayload(status="failed"),
            ),
        )
    with pytest.raises(DataServiceConflictError, match="before operation dispatch"):
        await store.claim_operation(
            mission_id,
            MissionOperationClaimPayload(
                operation_key="tool-after-open-call",
                kind="tool",
                request_hash="a" * 64,
                claimant="tool-orchestrator",
                lease_epoch=claimed.lease_epoch,
            ),
        )
    with pytest.raises(DataServiceConflictError, match="cannot wait"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=started.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                patch=MissionRunPatchPayload(status="waiting"),
            ),
        )
    with pytest.raises(DataServiceConflictError, match="cannot be released"):
        await store.release_run_lease(
            mission_id,
            MissionLeaseReleasePayload(
                worker_id="worker-1",
                lease_epoch=claimed.lease_epoch,
                expected_state_version=started.mission.state_version,
            ),
        )
    with pytest.raises(DataServiceConflictError, match="before dispatch"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=started.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    _model_call_started("model-call:workspace:next-dispatch")
                ],
            ),
        )

    unresolved = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=started.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[_model_call_terminal(model_call_id)],
        ),
    )
    with pytest.raises(DataServiceConflictError, match="advance stages"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=unresolved.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                patch=MissionRunPatchPayload(active_stage_id="next-stage"),
            ),
        )
    terminal = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=unresolved.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="failed"),
        ),
    )

    assert terminal.mission.status.value == "failed"
    assert terminal.mission.snapshot_json["billing"]["state"] == (
        "reconciliation_required"
    )
    items = await store.list_items_page(mission_id, limit=100)
    assert len(
        [
            item
            for item in items
            if item.item_type == "billing_reconciliation_required"
        ]
    ) == 1
    assert not any(item.item_type == "billing_settled" for item in items)


@pytest.mark.asyncio
async def test_one_subagent_model_call_does_not_block_another_jobs_tool(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-concurrent-subagent-ledgers",
        idempotency_key="concurrent-subagent-ledgers",
    )
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _model_call_started(
                    "model-call:subagent:job-b",
                    producer="job-b",
                    parent_operation_id="subagent-parent",
                    job_id="job-b",
                )
            ],
        ),
    )

    operation = await store.claim_operation(
        mission_id,
        MissionOperationClaimPayload(
            operation_key="job-a-tool",
            kind="tool",
            request_hash="a" * 64,
            claimant="job-a",
            model_call_job_id="job-a",
            lease_epoch=claimed.lease_epoch,
        ),
    )

    assert operation.acquired is True


@pytest.mark.asyncio
async def test_terminal_transition_rejects_new_open_call_in_same_append(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-new-open-terminal",
        idempotency_key="new-open-terminal",
    )
    claimed = await _claim(store, mission_id, version=0)

    with pytest.raises(DataServiceConflictError, match="open model calls"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=claimed.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                items=[
                    _model_call_started("model-call:workspace:new-and-open")
                ],
                patch=MissionRunPatchPayload(status="failed"),
            ),
        )

    current = await store.load_run_snapshot(mission_id)
    assert current is not None and current.status.value == "created"
    assert await store.list_model_call_states(mission_id) == []


@pytest.mark.asyncio
async def test_lease_takeover_fences_stale_epoch_and_version(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    first = await _claim(store, mission_id, version=0, worker="worker-old")

    record = await store.repository.get_run(mission_id, for_update=True)
    assert record is not None
    record.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await mission_session.commit()

    second = await _claim(
        store,
        mission_id,
        version=first.state_version,
        worker="worker-new",
    )
    assert second.lease_epoch == first.lease_epoch + 1

    with pytest.raises(DataServiceConflictError, match="stale|fence"):
        await store.append_items_and_update_snapshot(
            mission_id,
            MissionAppendPayload(
                expected_state_version=first.state_version,
                lease_owner="worker-old",
                lease_epoch=first.lease_epoch,
                items=[MissionItemDraftPayload(item_type="status_update", phase="completed")],
            ),
        )


@pytest.mark.asyncio
async def test_reconciler_claims_due_dispatch_once_without_consuming_wakeup(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await store.claim_runnable_batch_skip_locked(MissionRunnableBatchClaimPayload(worker_id="reconciler-1", ttl_seconds=120, limit=10))
    assert [run.mission_id for run in claimed] == [mission_id]
    assert claimed[0].dispatch_epoch == 1
    assert claimed[0].dispatch_owner == "reconciler-1"
    assert claimed[0].next_wakeup_at is not None

    duplicate_hint = await store.claim_runnable_batch_skip_locked(MissionRunnableBatchClaimPayload(worker_id="reconciler-2", ttl_seconds=120, limit=10))
    assert duplicate_hint == []


@pytest.mark.asyncio
async def test_operation_claim_is_atomic_reusable_and_terminal_epoch_fenced(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    command = MissionOperationClaimPayload(
        operation_key="operation-1",
        kind="tool",
        request_hash="a" * 64,
        claimant="tool-call-1",
        lease_epoch=claimed.lease_epoch,
        ttl_seconds=30,
    )
    first = await store.claim_operation(mission_id, command)
    duplicate = await store.claim_operation(mission_id, command)
    assert first.acquired is True
    assert duplicate.acquired is False
    assert duplicate.receipt.receipt_id == first.receipt.receipt_id

    terminal = await store.finish_operation(
        mission_id,
        MissionOperationFinishPayload(
            operation_key="operation-1",
            kind="tool",
            request_hash="a" * 64,
            claimant="tool-call-1",
            lease_epoch=claimed.lease_epoch,
            claim_token=first.receipt.claim_token,
            status="succeeded",
            receipt_json={"outcome": {"ok": True}},
        ),
    )
    replay = await store.claim_operation(mission_id, command)
    assert terminal.finalized is True
    assert replay.acquired is False
    assert replay.receipt.receipt_json == {"outcome": {"ok": True}}


@pytest.mark.asyncio
async def test_cancelling_mission_closes_open_operation_receipts(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-cancel-open-operation",
        idempotency_key="cancel-open-operation",
    )
    claimed = await _claim(store, mission_id, version=0)
    operation = await store.claim_operation(
        mission_id,
        MissionOperationClaimPayload(
            operation_key="operation-cancelled",
            kind="tool",
            request_hash="c" * 64,
            claimant="tool-call-cancelled",
            lease_epoch=claimed.lease_epoch,
        ),
    )
    queued = await store.append_command_once(
        mission_id,
        MissionUserCommandPayload(
            command_id="cancel-with-open-operation",
            command_type="cancel",
            summary="Stop now",
        ),
    )

    applied = await store.apply_commands_and_advance_cursor(
        mission_id,
        MissionApplyCommandsPayload(
            expected_state_version=queued.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            through_command_seq=queued.mission.last_command_seq,
            patch=MissionRunPatchPayload(status="cancelled"),
        ),
    )
    terminal = await store.get_operation(mission_id, "operation-cancelled")

    assert operation.acquired is True
    assert applied.mission.status is MissionStatus.CANCELLED
    assert terminal is not None
    assert terminal.status.value == "unknown"
    assert terminal.receipt_json["reason"] == (
        "mission_cancelled_before_effect_confirmation"
    )


@pytest.mark.asyncio
async def test_operation_terminal_receipt_is_not_hidden_after_first_100_items(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-operation-terminal-page",
        idempotency_key="operation-terminal-page",
    )
    claimed = await _claim(store, mission_id, version=0)
    operation_key = "operation-terminal-after-page"
    operation = await store.claim_operation(
        mission_id,
        MissionOperationClaimPayload(
            operation_key=operation_key,
            kind="tool",
            request_hash="d" * 64,
            claimant="tool-call-terminal-page",
            lease_epoch=claimed.lease_epoch,
        ),
    )
    current = await store.load_run_snapshot(mission_id)
    assert current is not None
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=current.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="operation_progress",
                    operation_id=operation_key,
                    phase="progress",
                    producer="tool-call-terminal-page",
                    summary=f"progress {index}",
                )
                for index in range(99)
            ],
        ),
    )
    await store.finish_operation(
        mission_id,
        MissionOperationFinishPayload(
            operation_key=operation_key,
            kind="tool",
            request_hash="d" * 64,
            claimant="tool-call-terminal-page",
            lease_epoch=claimed.lease_epoch,
            claim_token=operation.receipt.claim_token,
            status="succeeded",
            receipt_json={"outcome": {"ok": True}},
        ),
    )

    receipt = await store.get_operation(mission_id, operation_key)

    assert receipt is not None
    assert receipt.status.value == "succeeded"
    assert receipt.receipt_json == {"outcome": {"ok": True}}


@pytest.mark.asyncio
async def test_operation_finish_atomically_projects_semantic_references_once(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    operation_claim = await store.claim_operation(
        mission_id,
        MissionOperationClaimPayload(
            operation_key="search-1",
            kind="tool",
            request_hash="b" * 64,
            claimant="tool-call-1",
            lease_epoch=claimed.lease_epoch,
        ),
    )
    command = MissionOperationFinishPayload(
        operation_key="search-1",
        kind="tool",
        request_hash="b" * 64,
        claimant="tool-call-1",
        lease_epoch=claimed.lease_epoch,
        claim_token=operation_claim.receipt.claim_token,
        stage_id="literature",
        producer="文献研究员",
        status="succeeded",
        receipt_json={"query": "federated LoRA"},
        references=[
            MissionSemanticReferencePayload(
                category="evidence",
                reference_id="https://example.test/paper",
                reference_kind="paper",
                title="Federated LoRA",
                uri="https://example.test/paper",
                source_type="paper",
                verified=True,
                metadata={"publisher": "Example Journal"},
            ),
            MissionSemanticReferencePayload(
                category="artifact",
                reference_id="artifact://gap-map",
                reference_kind="research_note",
                title="研究空白图谱",
            ),
        ],
    )

    first = await store.finish_operation(mission_id, command)
    replay = await store.finish_operation(mission_id, command)
    evidence_page = await store.list_evidence_projection_page(mission_id)
    artifact_page = await store.list_artifact_projection_page(mission_id)
    items = await store.list_items_page(mission_id, limit=20)
    semantic_items = {
        item.item_type: item
        for item in items
        if item.item_type in {"evidence", "artifact"}
    }

    assert first.finalized is True
    assert replay.finalized is False
    assert [item.title for item in evidence_page.items] == ["Federated LoRA"]
    assert evidence_page.items[0].source_label == "Example Journal"
    assert artifact_page.items == []
    assert artifact_page.page.total == 0
    assert [item.item_type for item in items].count("operation_terminal") == 1
    assert [item.item_type for item in items].count("evidence") == 1
    assert [item.item_type for item in items].count("artifact") == 1
    assert semantic_items["evidence"].payload_ref == "https://example.test/paper"
    assert semantic_items["artifact"].payload_ref == "artifact://gap-map"

    current = await store.load_run_snapshot(mission_id)
    assert current is not None
    await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=current.state_version,
            lease_owner="worker-1",
            lease_epoch=current.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-gap-map",
                    source_item_seq=semantic_items["artifact"].seq,
                    output_key="literature_gap_map",
                    target_kind="document",
                    target_room="documents",
                    title="研究空白图谱",
                    risk_level="medium",
                    preview_json={
                        "artifact_kind": "research_note",
                        "body": "stage-accepted result",
                    },
                )
            ],
        ),
    )
    view = await store.get_view(mission_id)
    artifact_page = await store.list_artifact_projection_page(mission_id)

    assert view is not None
    assert view.mission.evidence_count == 1
    assert view.mission.artifact_count == 1
    assert view.artifact_page.total == 1
    assert [item.title for item in artifact_page.items] == ["研究空白图谱"]


@pytest.mark.asyncio
async def test_operation_finish_reuses_mission_semantic_reference_projection(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-reference-ssot",
        idempotency_key="reference-ssot",
    )
    claimed = await _claim(store, mission_id, version=0)
    for index in range(2):
        reference = MissionSemanticReferencePayload(
            category="evidence",
            reference_id="upload://attachment-1",
            reference_kind="uploaded_file",
            title=("附件1.xlsx" if index == 0 else "附件1.xlsx（再次读取）"),
            source_type="upload",
            verified=True,
            metadata={"observed_at": f"2026-07-11T00:00:0{index}Z"},
        )
        operation_key = f"read-attachment-{index + 1}"
        operation = await store.claim_operation(
            mission_id,
            MissionOperationClaimPayload(
                operation_key=operation_key,
                kind="tool",
                request_hash=str(index + 1) * 64,
                claimant=f"tool-call-{index + 1}",
                lease_epoch=claimed.lease_epoch,
            ),
        )
        finished = await store.finish_operation(
            mission_id,
            MissionOperationFinishPayload(
                operation_key=operation_key,
                kind="tool",
                request_hash=str(index + 1) * 64,
                claimant=f"tool-call-{index + 1}",
                lease_epoch=claimed.lease_epoch,
                claim_token=operation.receipt.claim_token,
                status="succeeded",
                receipt_json={"read": index + 1},
                references=[reference],
            ),
        )
        assert finished.finalized is True

    current = await store.load_run_snapshot(mission_id)
    page = await store.list_evidence_projection_page(mission_id)
    evidence_items = await store.list_items_page(
        mission_id,
        item_type="evidence",
        limit=10,
    )

    assert current is not None
    assert page is not None
    assert current.evidence_count == 1
    assert page.page.total == 1
    assert [item.title for item in page.items] == ["附件1.xlsx"]
    assert len(evidence_items) == 1


@pytest.mark.asyncio
async def test_operation_finish_rejects_divergent_semantic_reference_reuse(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-reference-conflict",
        idempotency_key="reference-conflict",
    )
    claimed = await _claim(store, mission_id, version=0)

    for index, title in enumerate(("附件1.xlsx", "被悄悄改名的附件.xlsx"), start=1):
        operation_key = f"reference-conflict-{index}"
        operation = await store.claim_operation(
            mission_id,
            MissionOperationClaimPayload(
                operation_key=operation_key,
                kind="tool",
                request_hash=str(index) * 64,
                claimant=f"tool-call-reference-conflict-{index}",
                lease_epoch=claimed.lease_epoch,
            ),
        )
        finish = MissionOperationFinishPayload(
            operation_key=operation_key,
            kind="tool",
            request_hash=str(index) * 64,
            claimant=f"tool-call-reference-conflict-{index}",
            lease_epoch=claimed.lease_epoch,
            claim_token=operation.receipt.claim_token,
            status="succeeded",
            receipt_json={"read": index},
            references=[
                MissionSemanticReferencePayload(
                    category="evidence",
                    reference_id="upload://attachment-conflict",
                    reference_kind="uploaded_file",
                    title=title,
                    uri=(
                        "upload://attachment-conflict"
                        if index == 1
                        else "upload://different-attachment"
                    ),
                    source_type="upload",
                    verified=True,
                )
            ],
        )
        if index == 1:
            result = await store.finish_operation(mission_id, finish)
            assert result.finalized is True
        else:
            with pytest.raises(
                DataServiceConflictError,
                match="semantic reference identity",
            ):
                await store.finish_operation(mission_id, finish)

    page = await store.list_evidence_projection_page(mission_id)
    second_receipt = await store.get_operation(mission_id, "reference-conflict-2")

    assert page is not None
    assert [item.title for item in page.items] == ["附件1.xlsx"]
    assert second_receipt is not None
    assert second_receipt.status.value == "claimed"


@pytest.mark.asyncio
async def test_operation_reclaim_rejects_stale_attempt_token(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    claim_command = MissionOperationClaimPayload(
        operation_key="reclaimed-operation",
        kind="tool",
        request_hash="c" * 64,
        claimant="stable-operation-id",
        lease_epoch=claimed.lease_epoch,
        ttl_seconds=30,
    )
    first = await store.claim_operation(mission_id, claim_command)
    first_item = await mission_session.get(MissionItemRecord, first.receipt.receipt_id)
    assert first_item is not None
    expired_payload = {
        **dict(first_item.payload_json),
        "lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    await mission_session.execute(
        update(MissionItemRecord)
        .where(MissionItemRecord.id == first.receipt.receipt_id)
        .values(payload_json=expired_payload)
    )
    await mission_session.commit()

    second = await store.claim_operation(mission_id, claim_command)
    assert second.acquired is True
    assert second.receipt.attempt == 2
    assert second.receipt.claim_token != first.receipt.claim_token

    with pytest.raises(DataServiceConflictError, match="claim fence"):
        await store.finish_operation(
            mission_id,
            MissionOperationFinishPayload(
                operation_key=claim_command.operation_key,
                kind=claim_command.kind,
                request_hash=claim_command.request_hash,
                claimant=claim_command.claimant,
                lease_epoch=claim_command.lease_epoch,
                claim_token=first.receipt.claim_token,
                status="succeeded",
            ),
        )

    terminal = await store.finish_operation(
        mission_id,
        MissionOperationFinishPayload(
            operation_key=claim_command.operation_key,
            kind=claim_command.kind,
            request_hash=claim_command.request_hash,
            claimant=claim_command.claimant,
            lease_epoch=claim_command.lease_epoch,
            claim_token=second.receipt.claim_token,
            status="succeeded",
        ),
    )
    assert terminal.finalized is True


@pytest.mark.asyncio
async def test_mission_view_projects_retry_activity_without_exposing_snapshot(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    result = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            snapshot_json={
                "loop_guard": {"transient_failures": 2},
                "next_actions": ["retry_agent_step_after_backoff"],
            },
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert view.activity.state == "retrying"
    assert view.activity.attempt == 2
    assert "snapshot_json" not in view.mission.model_dump()
    assert view.mission.state_version == result.mission.state_version


@pytest.mark.asyncio
async def test_mission_view_retries_after_projection_version_drift(
    mission_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    current = await store.load_run_snapshot(mission_id)
    assert current is not None
    expected_version = current.state_version
    real_get_version = store.repository.get_run_state_version
    observed_calls = 0

    async def drifting_once(candidate_mission_id: str) -> int | None:
        nonlocal observed_calls
        observed_calls += 1
        if observed_calls == 1:
            return expected_version + 1
        return await real_get_version(candidate_mission_id)

    monkeypatch.setattr(store.repository, "get_run_state_version", drifting_once)

    view = await store.get_view(mission_id)

    assert view is not None
    assert view.mission.state_version == expected_version
    assert observed_calls == 4


@pytest.mark.asyncio
async def test_artifact_projection_retries_after_version_drift(
    mission_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    current = await store.load_run_snapshot(mission_id)
    assert current is not None
    expected_version = current.state_version
    real_get_version = store.repository.get_run_state_version
    observed_calls = 0

    async def drifting_once(candidate_mission_id: str) -> int | None:
        nonlocal observed_calls
        observed_calls += 1
        if observed_calls == 1:
            return expected_version + 1
        return await real_get_version(candidate_mission_id)

    monkeypatch.setattr(store.repository, "get_run_state_version", drifting_once)

    page = await store.list_artifact_projection_page(mission_id)

    assert page is not None
    assert page.items == []
    assert len(page.page.revision) == 64
    assert observed_calls == 4


@pytest.mark.asyncio
async def test_mission_view_fails_closed_after_repeated_projection_drift(
    mission_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    current = await store.load_run_snapshot(mission_id)
    assert current is not None
    expected_version = current.state_version

    async def always_drifting(_mission_id: str) -> int:
        return expected_version + 1

    monkeypatch.setattr(store.repository, "get_run_state_version", always_drifting)

    with pytest.raises(
        MissionProjectionStaleError,
        match="changed repeatedly",
    ) as raised:
        await store.get_view(mission_id)
    assert raised.value.code == "MISSION_PROJECTION_STALE"
    assert raised.value.detail == {
        "mission_id": mission_id,
        "attempts": 3,
        "start_state_version": expected_version + 1,
        "end_state_version": expected_version + 1,
    }


@pytest.mark.asyncio
async def test_mission_projection_is_bounded_and_pages_review_and_commit_history(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    now = datetime.now(UTC)
    review_records = [
        MissionReviewItemRecord(
            review_item_id=f"review-{index:04d}",
            mission_id=mission_id,
            source_item_seq=None,
            output_key=f"output-{index:04d}",
            target_kind="memory",
            target_room="memory",
            target_ref=f"memory-{index:04d}",
            title=f"Candidate {index}",
            risk_level="low",
            status="accepted",
            preview_json={"body": f"candidate-{index}"},
            preview_hash=f"{index:064x}",
            created_at=now,
            updated_at=now,
        )
        for index in range(120)
    ]
    commit_records = [
        MissionCommitRecord(
            commit_id=f"commit-{index:04d}",
            mission_id=mission_id,
            review_item_id=f"review-{index:04d}",
            commit_key=f"commit-key-{index:04d}",
            status="pending",
            actor_user_id="user-1",
            targets_json={},
            attempt_count=0,
            created_at=now,
        )
        for index in range(120)
    ]
    mission_session.add_all([*review_records, *commit_records])
    await mission_session.commit()

    statement_count = 0
    bind = mission_session.get_bind()

    def count_statement(*_args: object) -> None:
        nonlocal statement_count
        statement_count += 1

    event.listen(bind, "before_cursor_execute", count_statement)
    try:
        view = await store.get_view(mission_id, projection_item_limit=10)
    finally:
        event.remove(bind, "before_cursor_execute", count_statement)

    assert view is not None
    assert len(view.review_items) == 10
    assert view.review_summary.accepted == 120
    assert view.commit_summary.pending == 120
    assert statement_count <= 12

    first_reviews = await store.list_review_items_page(mission_id, limit=25)
    assert first_reviews.page.total == 120
    assert first_reviews.page.returned == 25
    assert first_reviews.page.next_cursor is not None
    second_reviews = await store.list_review_items_page(
        mission_id,
        limit=25,
        cursor=first_reviews.page.next_cursor,
    )
    assert {
        item.review_item_id for item in first_reviews.items
    }.isdisjoint(item.review_item_id for item in second_reviews.items)

    first_commits = await store.list_commits_page(mission_id, limit=25)
    assert first_commits.page.total == 120
    assert first_commits.page.returned == 25
    assert first_commits.page.next_cursor is not None
    second_commits = await store.list_commits_page(
        mission_id,
        limit=25,
        cursor=first_commits.page.next_cursor,
    )
    assert {item.commit_id for item in first_commits.items}.isdisjoint(
        item.commit_id for item in second_commits.items
    )


@pytest.mark.asyncio
async def test_artifact_projection_cursor_preserves_equal_source_sequences(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    now = datetime.now(UTC)
    mission_session.add(
        MissionItemRecord(
            id="artifact-source-1",
            mission_id=mission_id,
            seq=1,
            item_type="artifact",
            phase="completed",
            payload_json={},
            created_at=now,
        )
    )
    mission_session.add_all(
        [
            MissionReviewItemRecord(
                review_item_id=f"artifact-review-{suffix}",
                mission_id=mission_id,
                source_item_seq=1,
                output_key=f"artifact-output-{suffix}",
                target_kind="document",
                target_room="documents",
                target_ref=f"document-{suffix}",
                title=f"Artifact {suffix}",
                risk_level="low",
                status="pending",
                preview_json={"artifact_kind": "document"},
                preview_ref=(
                    "mpv1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    if suffix == "b"
                    else None
                ),
                preview_hash=("a" if suffix == "a" else "b") * 64,
                preview_expires_at=(
                    now + timedelta(hours=1) if suffix == "b" else None
                ),
                created_at=now,
                updated_at=now,
            )
            for suffix in ("a", "b")
        ]
    )
    await mission_session.commit()

    first = await store.list_artifact_projection_page(mission_id, limit=1)
    assert first.page.total == 2
    assert first.page.next_cursor == 1
    assert first.page.next_tiebreaker == "artifact-review-a"
    assert first.items[0].preview_available is False
    initial_revision = first.page.revision

    second = await store.list_artifact_projection_page(
        mission_id,
        after_seq=first.page.next_cursor,
        after_review_item_id=first.page.next_tiebreaker,
        limit=1,
    )
    assert [item.item_id for item in second.items] == ["artifact-review-b"]
    assert second.items[0].preview_available is True
    assert second.items[0].preview_expires_at is not None
    assert second.page.next_cursor is None
    assert second.page.revision == initial_revision
    view = await store.get_view(mission_id, projection_item_limit=1)
    assert view is not None
    assert view.artifact_page.revision == initial_revision

    await mission_session.execute(
        update(MissionRunRecord)
        .where(MissionRunRecord.mission_id == mission_id)
        .values(state_version=MissionRunRecord.state_version + 1)
    )
    await mission_session.commit()
    heartbeat_refresh = await store.list_artifact_projection_page(
        mission_id,
        limit=1,
    )
    assert heartbeat_refresh.page.revision == initial_revision

    mission_session.add(
        MissionCommitRecord(
            commit_id="artifact-commit-b",
            mission_id=mission_id,
            review_item_id="artifact-review-b",
            commit_key="artifact-commit-key-b",
            status="committed",
            actor_user_id="user-1",
            targets_json={"target_ref": "asset-b"},
            attempt_count=1,
            created_at=now,
            completed_at=now,
        )
    )
    await mission_session.commit()
    committed_page = await store.list_artifact_projection_page(
        mission_id,
        after_seq=first.page.next_cursor,
        after_review_item_id=first.page.next_tiebreaker,
        limit=1,
    )
    assert committed_page.items[0].committed is True
    assert committed_page.page.revision != initial_revision


@pytest.mark.asyncio
async def test_mission_view_projects_live_subagent_milestone(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    operation_id = "subagent-live-parent"
    summary = "已确认逐时功率平衡式，并统一风光、购售电与制氢制氨符号。"
    updated = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _subagent_spawned(operation_id),
                _subagent_live_progress(
                    operation_id=operation_id,
                    job_id="formula-worker",
                    summary=summary,
                ),
                _subagent_internal_progress(
                    operation_id=operation_id,
                    job_id="formula-worker",
                    summary="internal output contract retry",
                ),
            ],
            snapshot_json={
                "inflight_operation": {
                    "operation_id": operation_id,
                    "kind": "subagent",
                    "call_item_seq": 2,
                }
            },
            patch=MissionRunPatchPayload(
                status="planning",
                active_subagent_count_delta=1,
            ),
        ),
    )

    view = await store.get_view(mission_id)

    assert updated.mission.active_subagent_count == 1
    assert view is not None
    assert view.activity.state == "collaborating"
    assert len(view.subagents) == 1
    assert view.subagents[0].display_name == "公式核验员"
    assert view.subagents[0].status == "working"
    assert view.subagents[0].summary == summary
    assert view.team_summary == "1 位研究成员正在推进，已有 1 条可查看进展。"
    assert len(view.subagents[0].milestones) == 1
    assert view.subagents[0].milestones[0].kind == "formula"
    assert view.subagents[0].milestones[0].summary == summary


@pytest.mark.asyncio
async def test_mission_view_projects_only_the_latest_subagent_batch(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _subagent_spawned("older-batch"),
                _subagent_terminal_progress(
                    operation_id="older-batch",
                    job_id="older-worker",
                    result_version=1,
                ),
                _subagent_spawned("current-batch"),
                _subagent_live_progress(
                    operation_id="current-batch",
                    job_id="current-worker",
                    summary="已完成当前批次的约束核验。",
                ),
            ],
            snapshot_json={
                "inflight_operation": {
                    "operation_id": "current-batch",
                    "kind": "subagent",
                    "call_item_seq": 4,
                }
            },
            patch=MissionRunPatchPayload(
                status="planning",
                active_subagent_count_delta=1,
            ),
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert [member.subagent_id for member in view.subagents] == ["current-worker"]
    assert view.team_summary == "1 位研究成员正在推进，已有 1 条可查看进展。"


@pytest.mark.asyncio
async def test_mission_view_does_not_reuse_previous_members_before_new_batch_progress(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _subagent_spawned("completed-batch"),
                _subagent_terminal_progress(
                    operation_id="completed-batch",
                    job_id="old-worker",
                    result_version=1,
                ),
                _subagent_spawned("new-batch"),
            ],
            snapshot_json={
                "inflight_operation": {
                    "operation_id": "new-batch",
                    "kind": "subagent",
                    "call_item_seq": 4,
                }
            },
            patch=MissionRunPatchPayload(
                status="planning",
                active_subagent_count_delta=1,
            ),
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert view.activity.state == "collaborating"
    assert view.subagents == []
    assert view.team_summary is None


@pytest.mark.asyncio
async def test_mission_view_projects_model_outage_as_preserved_work(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="artifact",
                    phase="completed",
                    summary="Unreviewed internal artifact candidate",
                ),
                _subagent_spawned("subagent-outage-parent"),
                _subagent_terminal_progress(
                    operation_id="subagent-outage-parent",
                    job_id="auditor-1",
                    result_version=1,
                    summary="Subagent exhausted its tool-step budget",
                    display_name="严谨派阿澈",
                    role_label="modeling_method_auditor",
                    status="failed",
                )
            ],
            snapshot_json={
                "failure_reason": "model_service_unavailable",
                "mission_inputs": [
                    {"member_path": "A题/A题/附件1：负荷曲线.xlsx"},
                    {"member_path": "A题\\A题\\附件2：风光曲线.xlsx"},
                ],
            },
            patch=MissionRunPatchPayload(status="failed"),
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert view.activity.state == "unavailable"
    assert view.activity.title == "模型服务暂时不可用"
    assert view.activity.summary == "已保留完成阶段和待确认内容，稍后可在对话中继续。"
    assert view.failure is not None
    assert view.failure.category == "model_service"
    assert view.failure.recoverability == "retry_later"
    assert "无需重新上传材料" in view.failure.recommended_action
    assert view.mission.artifact_count == 1
    assert view.failure.preserved_progress.endswith("0 个成果。")
    assert view.input_summary.total == 2
    assert view.input_summary.names == ["附件1：负荷曲线.xlsx", "附件2：风光曲线.xlsx"]
    assert view.subagents[0].role_label == "专项查证"
    assert view.subagents[0].summary == "达到本轮工具调用上限，已保留可用进度。"


@pytest.mark.asyncio
async def test_terminal_subagent_projection_survives_activity_window_and_is_bounded(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    operation_id = "completed-batch-outside-activity-window"
    terminal_summary = "已完成模型推导并整理最终结论。"
    progressed = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _subagent_spawned(operation_id),
                *[
                    _subagent_live_progress(
                        operation_id=operation_id,
                        job_id="bounded-worker",
                        summary=f"已确认第 {index} 条模型约束。",
                    )
                    for index in range(1, 9)
                ],
                _subagent_terminal_progress(
                    operation_id=operation_id,
                    job_id="bounded-worker",
                    result_version=1,
                    summary=terminal_summary,
                ),
                MissionItemDraftPayload(
                    item_type="subagent_completed",
                    operation_id=operation_id,
                    phase="completed",
                    producer="workspace_agent",
                    summary="Subagent batch completed",
                ),
            ],
            snapshot_json={},
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=progressed.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="status_update",
                    operation_id=f"later-item-{index}",
                    phase="completed",
                    producer="mission_runtime",
                    summary=f"Later mission activity {index}",
                )
                for index in range(100)
            ],
            snapshot_json={},
            patch=MissionRunPatchPayload(status="failed"),
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert [member.subagent_id for member in view.subagents] == ["bounded-worker"]
    assert view.subagents[0].status == "done"
    assert view.subagents[0].summary == terminal_summary
    assert len(view.subagents[0].milestones) == 6
    assert [item.summary for item in view.subagents[0].milestones] == [
        f"已确认第 {index} 条模型约束。" for index in range(3, 9)
    ]


@pytest.mark.asyncio
async def test_mission_view_projects_agent_protocol_repair_as_recovering(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            snapshot_json={"next_actions": ["repair_structured_decision"]},
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert view.activity.state == "recovering"
    assert view.activity.title == "问津正在校正下一步"
    assert view.activity.summary == "任务进度已经保留，校正后会从当前阶段继续。"


@pytest.mark.asyncio
async def test_current_review_projection_pages_without_truncation_or_duplicates(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-review-projection-page",
        idempotency_key="review-projection-page",
    )
    claimed = await _claim(store, mission_id, version=0)
    await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id=f"review-page-{index}",
                    output_key=f"output-{index}",
                    target_kind="claim",
                    title=f"待确认内容 {index}",
                    risk_level="medium",
                    preview_json={"body": f"content {index}"},
                )
                for index in range(5)
            ],
        ),
    )

    view = await store.get_view(mission_id, projection_item_limit=2)
    first = await store.list_review_projection_page(mission_id, limit=2)
    assert view is not None and first is not None
    second = await store.list_review_projection_page(
        mission_id,
        cursor=first.page.next_cursor,
        limit=2,
    )
    assert second is not None
    third = await store.list_review_projection_page(
        mission_id,
        cursor=second.page.next_cursor,
        limit=2,
    )
    assert third is not None

    ids = [
        item.review_item_id
        for page in (first, second, third)
        for item in page.items
    ]
    assert view.review_page.total == 5
    assert view.review_page.next_cursor is not None
    assert first.page.total == second.page.total == third.page.total == 5
    assert len(ids) == len(set(ids)) == 5
    assert third.page.next_cursor is None


@pytest.mark.asyncio
async def test_mission_view_pages_long_evidence_ledger_without_truncating_summary(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="evidence",
                    phase="completed",
                    summary=f"Evidence {index}",
                    payload_json={
                        "title": f"Evidence {index}",
                        "source_type": "artifact",
                        "verified": True,
                    },
                )
                for index in range(60)
            ],
        ),
    )
    view = await store.get_view(mission_id, projection_item_limit=50)
    assert view is not None
    assert view.evidence_page.total == 60
    assert view.evidence_page.returned == 50
    assert view.evidence_page.next_cursor == 50
    assert len(view.evidence_items) == 50


@pytest.mark.asyncio
async def test_stale_queue_hint_cannot_claim_a_waiting_or_delayed_mission(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)

    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    await store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="request-1",
            reason="user_input",
            pending_request={"question": "Please provide the dataset."},
        ),
    )

    snapshot = await store.load_run_snapshot(mission_id)
    assert snapshot is not None
    assert snapshot.status == "waiting"
    assert snapshot.next_wakeup_at is None
    with pytest.raises(DataServiceConflictError, match="not runnable"):
        await _claim(store, mission_id, version=snapshot.state_version)

    record = await store.repository.get_run(mission_id, for_update=True)
    assert record is not None
    record.status = "planning"
    record.next_wakeup_at = datetime.now(UTC) + timedelta(minutes=5)
    await mission_session.commit()

    with pytest.raises(DataServiceConflictError, match="not runnable"):
        await _claim(store, mission_id, version=snapshot.state_version)


@pytest.mark.asyncio
async def test_view_projects_waiting_snapshot_as_typed_attention_request(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    await store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="request-materials-1",
            reason="external_data",
            pending_request={
                "request_id": "request-materials-1",
                "summary": "请上传题目 PDF 和已有数据表。",
                "blocking_user_inputs": ["题目 PDF", "已有数据表"],
            },
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None
    assert view.attention_request is not None
    assert view.attention_request.request_id == "request-materials-1"
    assert view.attention_request.reason == "external_data"
    assert view.attention_request.summary == "请上传题目 PDF 和已有数据表。"
    assert [item.label for item in view.attention_request.required_inputs] == [
        "题目 PDF",
        "已有数据表",
    ]
    assert {item.input_type for item in view.attention_request.required_inputs} == {"file"}
    assert [action.action_type for action in view.attention_request.actions] == [
        "reply_in_chat",
        "upload_file",
    ]


@pytest.mark.asyncio
async def test_view_projects_permission_request_as_explicit_decisions(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    planning = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    await store.release_run_lease(
        mission_id,
        MissionLeaseReleasePayload(
            worker_id="worker-1",
            lease_epoch=claimed.lease_epoch,
            expected_state_version=planning.mission.state_version,
        ),
    )
    await store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="permission-1",
            reason="permission",
            pending_request={
                "request_id": "permission-1",
                "summary": "需要访问 Python 包索引安装依赖。",
                "permission_context": {
                    "mission_id": mission_id,
                    "tool_name": "sandbox.install_dependencies",
                    "operation": "install:abc",
                    "risk_level": "medium",
                    "network_profile": "package-index",
                },
            },
        ),
    )

    view = await store.get_view(mission_id)

    assert view is not None and view.attention_request is not None
    assert [action.action_type for action in view.attention_request.actions] == [
        "permission_allow_once",
        "permission_allow_mission",
        "permission_reject",
    ]
    assert [action.label for action in view.attention_request.actions] == [
        "仅本次允许",
        "本任务内允许",
        "不允许",
    ]


@pytest.mark.asyncio
async def test_view_omits_attention_request_outside_waiting_state(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    view = await store.get_view(await _created(store))

    assert view is not None
    assert view.attention_request is None


@pytest.mark.asyncio
async def test_view_projects_required_assets_and_schema_from_agent_pause(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    paused = await store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="request-validation-data",
            reason="user_input",
            pending_request={
                "summary": "请提供真实观测数据后继续验证。",
                "required_assets": ["逐小时借还量", "逐小时天气"],
                "minimum_schema": "station_id、timestamp、rentals_out、returns_in",
            },
        ),
    )

    view = await store.get_view(mission_id)

    assert paused.mission.snapshot_json["pending_request"]["request_id"] == "request-validation-data"
    assert view is not None and view.attention_request is not None
    assert view.attention_request.summary == "请提供真实观测数据后继续验证。"
    assert [item.label for item in view.attention_request.required_inputs] == [
        "逐小时借还量",
        "逐小时天气",
        "字段与单位说明",
    ]
    assert [item.input_type for item in view.attention_request.required_inputs] == [
        "file",
        "file",
        "text",
    ]
    assert view.attention_request.required_inputs[-1].description == (
        "station_id、timestamp、rentals_out、returns_in"
    )
    assert [action.action_type for action in view.attention_request.actions] == [
        "reply_in_chat",
        "upload_file",
    ]


@pytest.mark.asyncio
async def test_command_is_durable_once_and_cursor_advances_with_driver_state(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    command = MissionUserCommandPayload(
        command_id="command-1",
        command_type="steer",
        summary="Focus on Non-IID evidence.",
        payload_json={"focus": "non_iid"},
    )

    first = await store.append_command_once(mission_id, command)
    replay = await store.append_command_once(mission_id, command)
    assert first.items[0].seq == replay.items[0].seq == 1
    assert replay.mission.state_version == first.mission.state_version
    with pytest.raises(DataServiceConflictError, match="command_id"):
        await store.append_command_once(
            mission_id,
            MissionUserCommandPayload(
                command_id="command-1",
                command_type="correction",
                payload_json={"focus": "privacy"},
            ),
        )

    claimed = await _claim(store, mission_id, version=first.mission.state_version)
    applied = await store.apply_commands_and_advance_cursor(
        mission_id,
        MissionApplyCommandsPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            through_command_seq=1,
            items=[
                MissionItemDraftPayload(
                    item_type="status_update",
                    phase="completed",
                    summary="Steering applied",
                )
            ],
            snapshot_json={"plan_summary": "Prioritize Non-IID."},
        ),
    )
    assert applied.mission.last_applied_command_seq == 1
    assert await store.list_unapplied_commands(mission_id) == []


@pytest.mark.asyncio
async def test_command_snapshot_cannot_overwrite_resource_usage_projection(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(
        store,
        thread_id="thread-command-resource",
        idempotency_key="command-resource",
    )
    queued = await store.append_command_once(
        mission_id,
        MissionUserCommandPayload(
            command_id="command-resource-1",
            command_type="steer",
            payload_json={"focus": "evidence"},
        ),
    )
    claimed = await _claim(
        store,
        mission_id,
        version=queued.mission.state_version,
    )
    metered = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                _model_call_started("model-call:workspace:command-resource")
            ],
        ),
    )

    with pytest.raises(
        DataServiceValidationError,
        match="resource_usage is DataService-owned",
    ):
        await store.apply_commands_and_advance_cursor(
            mission_id,
            MissionApplyCommandsPayload(
                expected_state_version=metered.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=claimed.lease_epoch,
                through_command_seq=queued.mission.last_command_seq,
                snapshot_json={"resource_usage": _ZERO_RESOURCE_USAGE},
            ),
        )

    applied = await store.apply_commands_and_advance_cursor(
        mission_id,
        MissionApplyCommandsPayload(
            expected_state_version=metered.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            through_command_seq=queued.mission.last_command_seq,
            snapshot_json={"plan_summary": "Use receipt-backed evidence."},
        ),
    )
    assert applied.mission.snapshot_json["resource_usage"]["model_calls"] == 1
    assert applied.mission.snapshot_json["plan_summary"] == (
        "Use receipt-backed evidence."
    )


@pytest.mark.asyncio
async def test_new_review_candidate_atomically_replaces_same_output(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    first_candidate = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="artifact",
                    phase="completed",
                    stage_id="question_1_model",
                    summary="第一问模型规格",
                    payload_json={"kind": "artifact_candidate"},
                    payload_ref="artifact-candidate:first",
                )
            ],
        ),
    )
    first = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=first_candidate.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-first",
                    source_item_seq=first_candidate.items[0].seq,
                    output_key="question_1_model",
                    target_kind="document",
                    target_room="documents",
                    title="第一问模型规格",
                    risk_level="medium",
                    preview_json={"content": "first"},
                )
            ],
        ),
    )

    best_candidate = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=first.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=first.mission.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="artifact",
                    phase="completed",
                    stage_id="question_1_model",
                    summary="第一问模型规格",
                    payload_json={"kind": "artifact_candidate"},
                    payload_ref="artifact-candidate:best",
                )
            ],
        ),
    )
    replacement = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=best_candidate.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=best_candidate.mission.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-best",
                    source_item_seq=best_candidate.items[0].seq,
                    output_key="question_1_model",
                    target_kind="document",
                    target_room="documents",
                    title="第一问模型规格",
                    risk_level="medium",
                    preview_json={"content": "best"},
                )
            ],
        ),
    )

    assert replacement.superseded_review_item_ids == ["review-first"]
    assert replacement.mission.pending_review_count == 1
    records = await store.list_review_items(mission_id)
    assert {item.review_item_id: item.status.value for item in records} == {
        "review-first": "superseded",
        "review-best": "pending",
    }
    view = await store.get_view(mission_id)
    assert view is not None
    assert [item.review_item_id for item in view.review_items] == ["review-best"]
    assert view.review_summary.pending == 1
    assert view.review_summary.superseded == 0
    assert view.artifact_page.total == 1
    assert [item.item_id for item in view.artifact_items] == ["review-best"]


@pytest.mark.asyncio
async def test_retryable_failed_commit_blocks_candidate_supersession(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    first = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-retryable",
                    output_key="question_1_model",
                    target_kind="document",
                    target_room="documents",
                    title="第一问模型规格",
                    risk_level="medium",
                    preview_json={"content": "first"},
                )
            ],
        ),
    )
    accepted = await store.apply_review_decisions(
        mission_id,
        MissionReviewDecisionsPayload(
            decision_id="decision-retryable",
            expected_state_version=first.mission.state_version,
            actor_user_id="user-1",
            decisions=[
                MissionReviewDecisionPayload(
                    review_item_id="review-retryable",
                    status="accepted",
                )
            ],
        ),
    )
    recorded = await store.record_commit(
        mission_id,
        MissionCommitCreatePayload(
            expected_state_version=accepted.mission.state_version,
            review_item_id="review-retryable",
            commit_key="commit-retryable",
            actor_user_id="user-1",
        ),
    )
    started = await store.start_commit(
        mission_id,
        recorded.commit.commit_id,
        MissionCommitStartPayload(attempt_token="attempt-retryable"),
    )
    failed = await store.finish_commit(
        mission_id,
        recorded.commit.commit_id,
        MissionCommitFinishPayload(
            attempt_token="attempt-retryable",
            status="failed",
            targets_json={},
            error_json={"code": "temporary_target_failure"},
        ),
    )
    next_candidate = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=failed.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=started.mission.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="artifact",
                    phase="completed",
                    stage_id="question_1_model",
                    payload_json={"kind": "artifact_candidate"},
                    payload_ref="artifact-candidate:replacement",
                )
            ],
        ),
    )

    with pytest.raises(DataServiceConflictError, match="retryable save"):
        await store.create_review_items(
            mission_id,
            MissionReviewItemsCreatePayload(
                expected_state_version=next_candidate.mission.state_version,
                lease_owner="worker-1",
                lease_epoch=next_candidate.mission.lease_epoch,
                review_items=[
                    MissionReviewItemDraftPayload(
                        review_item_id="review-replacement",
                        source_item_seq=next_candidate.items[0].seq,
                        output_key="question_1_model",
                        target_kind="document",
                        target_room="documents",
                        title="第一问模型规格",
                        risk_level="medium",
                        preview_json={"content": "replacement"},
                    )
                ],
            ),
        )

    current = {item.review_item_id: item.status.value for item in await store.list_review_items(mission_id)}
    assert current == {"review-retryable": "accepted"}


@pytest.mark.asyncio
async def test_new_review_candidate_replaces_same_document_destination_even_when_model_changes_output_key(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    materialization = {
        "operation": "documents.upsert_prism_file",
        "payload": {"path": "第一问求解.md", "content_inline": "first"},
    }
    first = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-path-first",
                    output_key="q1.solution_validation",
                    target_kind="document",
                    target_room="documents",
                    title="第一问求解",
                    risk_level="medium",
                    preview_json={"materialization": materialization},
                )
            ],
        ),
    )

    replacement = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=first.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=first.mission.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-path-best",
                    output_key="q1.question_solution",
                    target_kind="document",
                    target_room="documents",
                    title="第一问求解",
                    risk_level="medium",
                    preview_json={
                        "materialization": {
                            **materialization,
                            "payload": {
                                **materialization["payload"],
                                "path": "  第一问求解.md  ",
                                "content_inline": "best",
                            },
                        }
                    },
                )
            ],
        ),
    )

    assert replacement.superseded_review_item_ids == ["review-path-first"]
    assert replacement.mission.pending_review_count == 1


@pytest.mark.asyncio
async def test_review_and_commit_are_item_scoped_and_commit_replay_is_idempotent(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    staged = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-1",
                    output_key="literature_gap",
                    target_kind="document",
                    target_room="documents",
                    title="Literature gap draft",
                    risk_level="medium",
                    preview_json={"content": "draft"},
                )
            ],
        ),
    )
    assert staged.mission.pending_review_count == 1
    assert staged.items[0].preview_hash is not None
    assert staged.items[0].requires_explicit_review is False
    assert staged.items[0].batch_acceptable is True
    assert staged.items[0].suggested_selected is True

    planning = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=staged.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=staged.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    running = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=planning.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=planning.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    completed = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=running.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=running.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="completed"),
        ),
    )
    assert completed.mission.status == "completed"
    assert completed.mission.pending_review_count == 1

    decided = await store.apply_review_decisions(
        mission_id,
        MissionReviewDecisionsPayload(
            decision_id="decision-1",
            expected_state_version=completed.mission.state_version,
            actor_user_id="user-1",
            decisions=[MissionReviewDecisionPayload(review_item_id="review-1", status="accepted")],
        ),
    )
    assert decided.items[0].status == "accepted"
    assert decided.mission.pending_review_count == 0
    assert decided.mission.status == "completed"

    replayed_decision = await store.apply_review_decisions(
        mission_id,
        MissionReviewDecisionsPayload(
            decision_id="decision-1",
            expected_state_version=completed.mission.state_version,
            actor_user_id="user-1",
            decisions=[MissionReviewDecisionPayload(review_item_id="review-1", status="accepted")],
        ),
    )
    assert replayed_decision.mission.state_version == decided.mission.state_version
    with pytest.raises(DataServiceConflictError, match="decision_id"):
        await store.apply_review_decisions(
            mission_id,
            MissionReviewDecisionsPayload(
                decision_id="decision-1",
                expected_state_version=decided.mission.state_version,
                actor_user_id="user-1",
                decisions=[MissionReviewDecisionPayload(review_item_id="review-1", status="superseded")],
            ),
        )

    command = MissionCommitCreatePayload(
        expected_state_version=decided.mission.state_version,
        review_item_id="review-1",
        commit_key="commit-review-1",
        actor_user_id="user-1",
    )
    first = await store.record_commit(mission_id, command)
    replay = await store.record_commit(mission_id, command)
    assert first.created is True
    assert replay.created is False
    assert replay.commit.commit_id == first.commit.commit_id
    assert replay.mission.status == "completed"
    pending_commit_view = await store.get_view(mission_id)
    assert pending_commit_view is not None
    assert "commits" not in pending_commit_view.model_dump(mode="json")
    assert pending_commit_view.review_items[0].commit_status == "pending"
    assert pending_commit_view.review_items[0].commit_eligible is True
    loaded = await store.load_commit_for_review_item(mission_id, "review-1")
    assert loaded is not None
    assert loaded.commit.commit_id == first.commit.commit_id

    await mission_session.execute(update(MissionReviewItemRecord).where(MissionReviewItemRecord.review_item_id == "review-1").values(status="rejected"))
    await mission_session.commit()
    with pytest.raises(DataServiceConflictError, match="accepted"):
        await store.start_commit(
            mission_id,
            first.commit.commit_id,
            MissionCommitStartPayload(attempt_token="attempt-token-rejected"),
        )
    await mission_session.execute(update(MissionReviewItemRecord).where(MissionReviewItemRecord.review_item_id == "review-1").values(status="accepted"))
    await mission_session.commit()

    await store.start_commit(
        mission_id,
        first.commit.commit_id,
        MissionCommitStartPayload(attempt_token="attempt-token-0001"),
    )
    await mission_session.execute(
        update(MissionReviewItemRecord)
        .where(MissionReviewItemRecord.review_item_id == "review-1")
        .values(
            preview_ref="mpv1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            preview_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await mission_session.commit()
    protected_cleanup = await store.cleanup_expired_previews(
        MissionPreviewCleanupPayload(now=datetime.now(UTC))
    )
    assert protected_cleanup.review_item_ids == []
    protected_item = (await store.list_review_items(mission_id))[0]
    assert protected_item.status == "accepted"
    assert protected_item.preview_ref == "mpv1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    authority = MissionWriteAuthority(
        mission_id=mission_id,
        mission_review_item_id="review-1",
        mission_commit_id=first.commit.commit_id,
        attempt_token="attempt-token-0001",
    )
    await assert_active_mission_write(
        mission_session,
        authority=authority,
        workspace_id="workspace-1",
        required=True,
    )
    with pytest.raises(ValueError, match="mission_write_authority_lost"):
        await assert_active_mission_write(
            mission_session,
            authority=authority.model_copy(update={"attempt_token": "wrong-attempt-token"}),
            workspace_id="workspace-1",
            required=True,
        )
    applying_view = await store.get_view(mission_id)
    assert applying_view is not None
    assert applying_view.review_items[0].commit_status == "applying"
    assert applying_view.review_items[0].commit_eligible is False
    assert applying_view.review_items[0].commit_block_reason == "commit_in_progress"
    with pytest.raises(DataServiceConflictError, match="already applying"):
        await store.start_commit(
            mission_id,
            first.commit.commit_id,
            MissionCommitStartPayload(attempt_token="attempt-token-0002"),
        )
    await mission_session.execute(update(MissionCommitRecord).where(MissionCommitRecord.commit_id == first.commit.commit_id).values(attempt_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await mission_session.commit()
    recovered = await store.start_commit(
        mission_id,
        first.commit.commit_id,
        MissionCommitStartPayload(attempt_token="attempt-token-0002"),
    )
    assert recovered.commit.attempt_count == 2
    with pytest.raises(DataServiceConflictError, match="attempt fence"):
        await store.finish_commit(
            mission_id,
            first.commit.commit_id,
            MissionCommitFinishPayload(
                attempt_token="attempt-token-0001",
                status="committed",
                targets_json={"document_id": "document-1"},
            ),
        )
    await mission_session.execute(update(MissionRunRecord).where(MissionRunRecord.mission_id == mission_id).values(state_version=MissionRunRecord.state_version + 1))
    await mission_session.commit()
    committed = await store.finish_commit(
        mission_id,
        first.commit.commit_id,
        MissionCommitFinishPayload(
            attempt_token="attempt-token-0002",
            status="committed",
            targets_json={"document_id": "document-1"},
        ),
    )
    assert committed.commit.status == "committed"
    assert committed.commit.attempt_count == 2
    assert committed.mission.status == "completed"
    committed_view = await store.get_view(mission_id)
    assert committed_view is not None
    assert committed_view.review_items[0].commit_status == "committed"
    assert committed_view.review_items[0].commit_eligible is False
    assert committed_view.review_items[0].commit_block_reason == "already_committed"
    terminal_replay = await store.finish_commit(
        mission_id,
        first.commit.commit_id,
        MissionCommitFinishPayload(
            attempt_token="attempt-token-0002",
            status="committed",
            targets_json={"document_id": "document-1"},
        ),
    )
    assert terminal_replay.commit.status == "committed"
    with pytest.raises(DataServiceConflictError, match="terminal replay"):
        await store.finish_commit(
            mission_id,
            first.commit.commit_id,
            MissionCommitFinishPayload(
                attempt_token="attempt-token-stale",
                status="committed",
                targets_json={"document_id": "document-2"},
            ),
        )
    review_items = await store.list_review_items(mission_id)
    assert review_items[0].status == "committed"


@pytest.mark.asyncio
async def test_committed_review_makes_nonterminal_mission_durably_runnable(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    staged = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-runnable",
                    output_key="stage_result",
                    target_kind="document",
                    target_room="documents",
                    title="Stage result",
                    risk_level="medium",
                    preview_json={"content": "draft"},
                )
            ],
        ),
    )
    planning = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=staged.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=staged.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    _running = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=planning.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=planning.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    paused = await store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="pause-runnable",
            reason="approval",
            pending_request={"review_item_id": "review-runnable"},
            producer="mission_runtime",
        ),
    )
    decided = await store.apply_review_decisions(
        mission_id,
        MissionReviewDecisionsPayload(
            decision_id="decision-runnable",
            expected_state_version=paused.mission.state_version,
            actor_user_id="user-1",
            decisions=[
                MissionReviewDecisionPayload(
                    review_item_id="review-runnable",
                    status="accepted",
                )
            ],
        ),
    )
    assert decided.mission.status == "waiting"
    recorded = await store.record_commit(
        mission_id,
        MissionCommitCreatePayload(
            expected_state_version=decided.mission.state_version,
            review_item_id="review-runnable",
            commit_key="commit-runnable",
            actor_user_id="user-1",
        ),
    )
    started = await store.start_commit(
        mission_id,
        recorded.commit.commit_id,
        MissionCommitStartPayload(attempt_token="attempt-token-runnable"),
    )
    assert started.mission.next_wakeup_at is None

    committed = await store.finish_commit(
        mission_id,
        recorded.commit.commit_id,
        MissionCommitFinishPayload(
            attempt_token="attempt-token-runnable",
            status="committed",
            targets_json={"document_id": "document-runnable"},
        ),
    )

    assert committed.mission.status == "planning"
    assert committed.mission.next_wakeup_at is not None
    assert "pending_request" not in committed.mission.snapshot_json


@pytest.mark.asyncio
async def test_revision_decision_makes_nonterminal_mission_durably_runnable(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    staged = await store.create_review_items(
        mission_id,
        MissionReviewItemsCreatePayload(
            expected_state_version=claimed.state_version,
            lease_owner="worker-1",
            lease_epoch=claimed.lease_epoch,
            review_items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-revise",
                    output_key="stage_result",
                    target_kind="document",
                    target_room="documents",
                    title="Stage result",
                    risk_level="medium",
                    preview_json={"content": "draft"},
                )
            ],
        ),
    )
    planning = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=staged.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=staged.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="planning"),
        ),
    )
    _running = await store.append_items_and_update_snapshot(
        mission_id,
        MissionAppendPayload(
            expected_state_version=planning.mission.state_version,
            lease_owner="worker-1",
            lease_epoch=planning.mission.lease_epoch,
            patch=MissionRunPatchPayload(status="running"),
        ),
    )
    paused = await store.pause_run(
        mission_id,
        MissionPausePayload(
            request_id="pause-revise",
            reason="approval",
            pending_request={"review_item_id": "review-revise"},
            producer="mission_runtime",
        ),
    )

    decided = await store.apply_review_decisions(
        mission_id,
        MissionReviewDecisionsPayload(
            decision_id="decision-revise",
            expected_state_version=paused.mission.state_version,
            actor_user_id="user-1",
            decisions=[
                MissionReviewDecisionPayload(
                    review_item_id="review-revise",
                    status="needs_more_evidence",
                )
            ],
        ),
    )

    assert decided.mission.next_wakeup_at is not None
    assert decided.mission.status == "planning"
    assert "pending_request" not in decided.mission.snapshot_json


def test_snapshot_rejects_scalar_duplication_and_oversize() -> None:
    base = _create_payload().model_dump()
    with pytest.raises(ValueError, match="duplicates"):
        MissionCreatePayload(**{**base, "snapshot_json": {"status": "running"}})

    with pytest.raises(
        ValueError,
        match="duplicates MissionItem-derived projection.*subagent_summary",
    ):
        MissionCreatePayload(
            **{
                **base,
                "snapshot_json": {"subagent_summary": [{"status": "working"}]},
            }
        )

    with pytest.raises(ValueError, match="exceeds"):
        MissionCreatePayload(
            **{
                **base,
                "snapshot_json": {"plan_summary": "x" * MAX_MISSION_SNAPSHOT_BYTES},
            }
        )


@pytest.mark.asyncio
async def test_release_uses_version_and_epoch_fence(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    mission_id = await _created(store)
    claimed = await _claim(store, mission_id, version=0)
    released = await store.release_run_lease(
        mission_id,
        MissionLeaseReleasePayload(
            worker_id="worker-1",
            lease_epoch=claimed.lease_epoch,
            expected_state_version=claimed.state_version,
        ),
    )
    assert released.lease_owner is None
    with pytest.raises(DataServiceConflictError, match="stale|fence"):
        await store.release_run_lease(
            mission_id,
            MissionLeaseReleasePayload(
                worker_id="worker-1",
                lease_epoch=claimed.lease_epoch,
                expected_state_version=claimed.state_version,
            ),
        )

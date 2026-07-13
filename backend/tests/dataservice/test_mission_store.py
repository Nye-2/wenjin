"""High-value transaction tests for the canonical MissionStore."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.contracts.stage_acceptance import StageAcceptanceContract
from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.dataservice.common.errors import DataServiceConflictError
from src.dataservice.domains.mission.service import (
    MissionStore,
    _project_stage_instance_ids,
    _stage_projection_title,
)
from src.dataservice_client.contracts.mission import (
    MAX_MISSION_SNAPSHOT_BYTES,
    MissionAppendPayload,
    MissionApplyCommandsPayload,
    MissionCancelPayload,
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
    MissionUserCommandPayload,
)

MISSION_TABLES = [
    MissionRunRecord.__table__,
    MissionItemRecord.__table__,
    MissionReviewItemRecord.__table__,
    MissionCommitRecord.__table__,
]


def _per_item_stage_contract(stage_id: str, template: str) -> StageAcceptanceContract:
    return StageAcceptanceContract.model_validate(
        {
            "schema_version": "stage_acceptance_contract.v1",
            "contract_id": f"math.{stage_id}",
            "version": 1,
            "mission_policy_id": "math",
            "workspace_type": "math_modeling",
            "stage_id": stage_id,
            "stage_goal": "Complete one question stage.",
            "minimum_criteria": [
                {"criterion_id": "complete", "description": "The stage is complete."}
            ],
            "reviewer_roles": ["reviewer"],
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
    assert _stage_projection_title(
        workspace_type="math_modeling",
        stage_id="question_1_solution_validation",
        contracts=contracts,
    ) == "第 1 问求解与验证"


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
                "stage_acceptance": {
                    "question_1_model": {"result": "pass"},
                }
            },
            "runtime_context_json": {
                "required_stage_ids": [
                    "problem_understanding",
                    "question_model",
                    "question_solution_validation",
                    "paper_integration",
                ],
                "stage_contracts": {
                    contract.stage_id: contract.model_dump(mode="json")
                    for contract in contracts
                },
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
            items=[
                MissionReviewItemDraftPayload(
                    source_item_seq=source_seq,
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
        "paper_integration",
    ]
    assert [stage.title for stage in view.stage_summaries] == [
        "题目理解",
        "第 1 问建模",
        "第 1 问求解与验证",
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
        await connection.run_sync(
            lambda sync_connection: MissionRunRecord.metadata.create_all(
                sync_connection, tables=MISSION_TABLES
            )
        )
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
        runtime_context_json={"policy_ref": "policy-v1"},
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


@pytest.mark.asyncio
async def test_mission_stats_aggregate_only_mission_runs(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    first = await store.create_run(
        _create_payload(thread_id="thread-stats-1", idempotency_key="stats-1")
    )
    second = await store.create_run(
        _create_payload(thread_id="thread-stats-2", idempotency_key="stats-2")
    )
    await mission_session.execute(
        update(MissionRunRecord)
        .where(MissionRunRecord.mission_id == first.mission.mission_id)
        .values(status="completed", next_wakeup_at=None)
    )
    await mission_session.execute(
        update(MissionRunRecord)
        .where(MissionRunRecord.mission_id == second.mission.mission_id)
        .values(status="failed", next_wakeup_at=None)
    )
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
async def test_review_mode_command_updates_mission_without_waking_agent(
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

    assert result.mission.review_mode.value == "review_all"
    assert result.mission.last_applied_command_seq == result.mission.last_command_seq
    assert result.mission.next_wakeup_at is not None
    assert created.mission.next_wakeup_at is not None
    assert (
        result.mission.next_wakeup_at.replace(tzinfo=UTC).timestamp()
        == created.mission.next_wakeup_at.timestamp()
    )


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
            items=[
                MissionReviewItemDraftPayload(
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

    cleaned = await store.cleanup_expired_previews(
        MissionPreviewCleanupPayload(now=datetime.now(UTC))
    )
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
        await store.create_run(
            _create_payload(idempotency_key="mission-create-2")
        )

    await store.cancel_run(
        created.mission.mission_id,
        MissionCancelPayload(request_id="cancel-1", reason="Replace the task"),
    )
    replacement = await store.create_run(
        _create_payload(idempotency_key="mission-create-2")
    )
    assert replacement.created is True


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
                MissionItemDraftPayload(
                    item_type="plan", phase="completed", summary="Plan accepted"
                ),
                MissionItemDraftPayload(
                    item_type="stage_started",
                    phase="started",
                    stage_id="literature",
                ),
            ],
            snapshot_json={"plan_summary": "Literature first."},
            patch=MissionRunPatchPayload(
                status="planning", active_stage_id="literature"
            ),
        ),
    )

    assert [item.seq for item in result.items] == [1, 2]
    assert result.mission.last_item_seq == 2
    assert result.mission.state_version == claimed.state_version + 1
    assert result.mission.snapshot_json == {"plan_summary": "Literature first."}

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
            patch=MissionRunPatchPayload(
                context_checkpoint_ref="trace://checkpoint-1"
            ),
        ),
    )
    assert checkpoint.mission.context_checkpoint_ref == "trace://checkpoint-1"
    assert checkpoint.items[0].seq == 3

    result.items[0].payload_json["client_only"] = True
    persisted = await store.list_items_page(mission_id)
    assert "client_only" not in persisted[0].payload_json


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
    claimed = await store.claim_runnable_batch_skip_locked(
        MissionRunnableBatchClaimPayload(
            worker_id="reconciler-1", ttl_seconds=120, limit=10
        )
    )
    assert [run.mission_id for run in claimed] == [mission_id]
    assert claimed[0].dispatch_epoch == 1
    assert claimed[0].dispatch_owner == "reconciler-1"
    assert claimed[0].next_wakeup_at is not None

    duplicate_hint = await store.claim_runnable_batch_skip_locked(
        MissionRunnableBatchClaimPayload(
            worker_id="reconciler-2", ttl_seconds=120, limit=10
        )
    )
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
            status="succeeded",
            receipt_json={"outcome": {"ok": True}},
        ),
    )
    replay = await store.claim_operation(mission_id, command)
    assert terminal.finalized is True
    assert replay.acquired is False
    assert replay.receipt.receipt_json == {"outcome": {"ok": True}}


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
                    payload_json={"title": f"Evidence {index}", "verified": True},
                )
                for index in range(60)
            ],
            patch=MissionRunPatchPayload(evidence_count_delta=60),
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
async def test_view_omits_attention_request_outside_waiting_state(
    mission_session: AsyncSession,
) -> None:
    store = MissionStore(mission_session, autocommit=True)
    view = await store.get_view(await _created(store))

    assert view is not None
    assert view.attention_request is None


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

    claimed = await _claim(
        store, mission_id, version=first.mission.state_version
    )
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
            items=[
                MissionReviewItemDraftPayload(
                    review_item_id="review-1",
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
            decisions=[
                MissionReviewDecisionPayload(
                    review_item_id="review-1", status="accepted"
                )
            ],
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
            decisions=[
                MissionReviewDecisionPayload(
                    review_item_id="review-1", status="accepted"
                )
            ],
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
                decisions=[
                    MissionReviewDecisionPayload(
                        review_item_id="review-1", status="superseded"
                    )
                ],
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

    await mission_session.execute(
        update(MissionReviewItemRecord)
        .where(MissionReviewItemRecord.review_item_id == "review-1")
        .values(status="rejected")
    )
    await mission_session.commit()
    with pytest.raises(DataServiceConflictError, match="accepted"):
        await store.start_commit(
            mission_id,
            first.commit.commit_id,
            MissionCommitStartPayload(attempt_token="attempt-token-rejected"),
        )
    await mission_session.execute(
        update(MissionReviewItemRecord)
        .where(MissionReviewItemRecord.review_item_id == "review-1")
        .values(status="accepted")
    )
    await mission_session.commit()

    await store.start_commit(
        mission_id,
        first.commit.commit_id,
        MissionCommitStartPayload(
            attempt_token="attempt-token-0001"
        ),
    )
    with pytest.raises(DataServiceConflictError, match="already applying"):
        await store.start_commit(
            mission_id,
            first.commit.commit_id,
            MissionCommitStartPayload(attempt_token="attempt-token-0002"),
        )
    await mission_session.execute(
        update(MissionCommitRecord)
        .where(MissionCommitRecord.commit_id == first.commit.commit_id)
        .values(attempt_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
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
    await mission_session.execute(
        update(MissionRunRecord)
        .where(MissionRunRecord.mission_id == mission_id)
        .values(state_version=MissionRunRecord.state_version + 1)
    )
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


def test_snapshot_rejects_scalar_duplication_and_oversize() -> None:
    base = _create_payload().model_dump()
    with pytest.raises(ValueError, match="duplicates"):
        MissionCreatePayload(**{**base, "snapshot_json": {"status": "running"}})

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

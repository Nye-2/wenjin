from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    StageCriterion,
    StageInstantiationRule,
)
from src.dataservice_client.contracts.mission import (
    MissionItemDraftPayload,
    MissionLeaseClaimPayload,
    MissionReviewItemPayload,
    MissionReviewStatus,
    MissionRiskLevel,
    MissionStatus,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    BillingOutcome,
    MissionAgentDecision,
    MissionAgentProtocolError,
    MissionPauseRequest,
    MissionPortOutcome,
    MissionPortOutcomeStatus,
    MissionSliceLimits,
    MissionSliceOutcome,
    StageQualityOutcome,
    StageQualityVerdict,
)
from src.mission_runtime.reconciler import MissionReconciler
from src.mission_runtime.runtime import (
    MissionResumeRequestMismatchError,
    MissionStartRejectedError,
)

from .conftest import (
    FakeEvents,
    FakeMissionStore,
    FakeQuality,
    FakeTools,
    FakeWakeups,
    MutableClock,
    ScriptedAgent,
    SimulatedWorkerCrash,
    start_request,
)


def continue_decision(identifier: str) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=identifier,
        kind="continue",
        summary=f"continue {identifier}",
        snapshot_patch={"plan_summary": f"plan {identifier}"},
    )


def complete_decision(identifier: str = "complete-1") -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=identifier,
        kind="complete",
        summary="Mission output is ready",
        payload_json={"output_refs": ["artifact://draft"]},
    )


def tool_decision(operation_id: str) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=f"decision-{operation_id}",
        kind="tool",
        operation_id=operation_id,
        summary="Run structured research tool",
        payload_json={"tool_name": "native_web_search", "arguments": {"query": "federated PEFT"}},
    )


def quality_decision(operation_id: str) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=f"decision-{operation_id}",
        kind="quality",
        operation_id=operation_id,
        stage_id="question_1_solution_validation",
        summary="Evaluate current stage",
        payload_json={"candidate_refs": [], "assessment": {}},
    )


def understanding_quality_decision(
    operation_id: str,
    *,
    item_count: int | None,
) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=f"decision-{operation_id}",
        kind="quality",
        operation_id=operation_id,
        stage_id="problem_understanding",
        summary="Evaluate problem understanding and pin question count",
        payload_json={
            "candidate_refs": [],
            "item_counts": (
                {"problem_questions": item_count}
                if item_count is not None
                else {}
            ),
            "assessment": {},
        },
    )


class _PassingQualityWithResult:
    async def can_start(self, mission, stage_id):
        del mission, stage_id
        return True, ()

    async def evaluate(self, request):
        del request
        return StageQualityOutcome(
            verdict=StageQualityVerdict.PASS,
            summary="understanding passed",
            payload_json={"result": "pass"},
        )


def _per_item_runtime_context(*, terminal_outputs: bool = False) -> dict[str, Any]:
    understanding = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="math_modeling_solution.problem_understanding",
        version=1,
        mission_policy_id="math_modeling_solution",
        workspace_type="math_modeling",
        stage_id="problem_understanding",
        stage_goal="Understand and enumerate the problem questions.",
        minimum_criteria=(
            StageCriterion(
                criterion_id="question_inventory",
                description="All problem questions are identified.",
            ),
        ),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        advance_condition="Question inventory passes.",
        stop_condition="The problem statement cannot be understood.",
    )
    question_model = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="math_modeling_solution.question_model",
        version=1,
        mission_policy_id="math_modeling_solution",
        workspace_type="math_modeling",
        stage_id="question_model",
        stage_goal="Produce a validated model for one question.",
        minimum_criteria=(
            StageCriterion(
                criterion_id="validated_solution",
                description="The question solution is validated.",
            ),
        ),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        prerequisite_stage_ids=("problem_understanding",),
        instantiation=StageInstantiationRule(
            mode="per_item",
            source_context_key="problem_questions",
            instance_id_template="question_{index}_model",
        ),
        advance_condition="The question solution passes.",
        stop_condition="The question cannot be solved reliably.",
    )
    context: dict[str, Any] = {
        "required_stage_ids": ["question_model"],
        "stage_contracts": {
            understanding.stage_id: understanding.model_dump(mode="json"),
            question_model.stage_id: question_model.model_dump(mode="json"),
        },
    }
    if terminal_outputs:
        context["terminal_output_kinds"] = ["question_solution"]
    return context


@pytest.mark.asyncio
async def test_start_and_complete_mission(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))

    receipt = await runtime.start(start_request())
    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert receipt.created is True
    assert receipt.wakeup_published is True
    assert telemetry.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.lease_owner is None
    assert deps["billing"].settled == [receipt.mission_id]


@pytest.mark.asyncio
async def test_start_rejects_client_owned_stage_item_counts(runtime_factory) -> None:
    runtime, _deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))

    with pytest.raises(MissionStartRejectedError, match="server-owned"):
        await runtime.start(
            start_request(
                snapshot_json={"stage_item_counts": {"problem_questions": 2}},
            )
        )


@pytest.mark.asyncio
async def test_per_item_count_is_pinned_atomically_with_understanding_quality(
    runtime_factory,
) -> None:
    first = understanding_quality_decision(
        "quality-count-1",
        item_count=2,
    )
    changed = understanding_quality_decision(
        "quality-count-2",
        item_count=3,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([first, changed]),
        quality=_PassingQualityWithResult(),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(
        start_request(runtime_context_json=_per_item_runtime_context())
    )

    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)

    assert run is not None
    assert run.snapshot_json["stage_item_counts"] == {"problem_questions": 2}
    invalid = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "error"
        and item.operation_id == "decision-quality-count-2"
    ]
    assert "not_unlocked_by_stage" in invalid[-1].payload_json["detail"]


@pytest.mark.asyncio
async def test_understanding_pass_is_not_persisted_without_required_item_count(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [
                understanding_quality_decision(
                    "quality-count-missing",
                    item_count=None,
                )
            ]
        ),
        quality=_PassingQualityWithResult(),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(
        start_request(runtime_context_json=_per_item_runtime_context())
    )

    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert run is not None
    assert "stage_acceptance" not in run.snapshot_json
    invalid = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "error"
        and item.operation_id == "decision-quality-count-missing"
    ]
    assert "missing=problem_questions" in invalid[-1].payload_json["detail"]


@pytest.mark.asyncio
async def test_completion_expands_each_per_item_stage_instance(runtime_factory) -> None:
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([complete_decision("complete-1"), complete_decision("complete-2")]),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(
        start_request(runtime_context_json=_per_item_runtime_context())
    )
    persisted = deps["store"].runs[receipt.mission_id]
    persisted.snapshot_json.update(
        {
            "stage_item_counts": {"problem_questions": 2},
            "stage_acceptance": {"question_1_model": {"result": "pass"}},
        }
    )

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    persisted.snapshot_json["stage_acceptance"]["question_2_model"] = {
        "result": "pass"
    }
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert second.outcome == MissionSliceOutcome.COMPLETED
    invalid = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "error" and item.operation_id == "complete-1"
    ]
    assert "question_2_model" in invalid[-1].payload_json["detail"]


@pytest.mark.asyncio
async def test_completion_requires_each_terminal_candidate_to_be_user_viewable(runtime_factory) -> None:
    candidate_ref = "artifact-candidate:" + "a" * 64
    review = MissionAgentDecision(
        decision_id="decision-review-terminal",
        kind="review",
        operation_id="review-terminal",
        stage_id="question_1_model",
        summary="Expose the accepted terminal result",
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [
                complete_decision("complete-before-review"),
                review,
                complete_decision("complete-after-review"),
            ]
        ),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(
        start_request(
            runtime_context_json=_per_item_runtime_context(
                terminal_outputs=True
            )
        )
    )
    persisted = deps["store"].runs[receipt.mission_id]
    persisted.snapshot_json.update(
        {
            "stage_item_counts": {"problem_questions": 1},
            "stage_acceptance": {
                "question_1_model": {
                    "result": "pass",
                    "artifact_refs": [candidate_ref],
                }
            },
        }
    )
    deps["store"].seed_items(
        receipt.mission_id,
        [
            MissionItemDraftPayload(
                item_type="artifact",
                phase="completed",
                stage_id="question_1_model",
                producer="tool_orchestrator",
                summary="Verified question solution",
                payload_json={
                    "verified": True,
                    "reference_id": candidate_ref,
                    "metadata": {"artifact_kind": "question_solution"},
                },
            )
        ],
    )

    before_review = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-1",
    )
    exposed = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    completed = await runtime.run_slice(receipt.mission_id, worker_id="worker-3")

    assert before_review.outcome == MissionSliceOutcome.YIELDED
    assert exposed.outcome == MissionSliceOutcome.YIELDED
    assert completed.outcome == MissionSliceOutcome.COMPLETED
    assert deps["review"].calls == ["review-terminal"]
    review_items = deps["store"].review_items[receipt.mission_id]
    assert next(iter(review_items.values())).preview_json["candidate_ref"] == candidate_ref


@pytest.mark.asyncio
async def test_child_mission_inherits_only_passed_stage_receipts(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    runtime_context = {"policy_content_hash": "a" * 64}
    parent_receipt = await runtime.start(
        start_request(
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
        )
    )
    parent = deps["store"].runs[parent_receipt.mission_id]
    parent.snapshot_json["stage_acceptance"] = {
        "problem_understanding": {
            "stage_id": "problem_understanding",
            "result": "pass",
            "artifact_refs": ["problem-brief"],
        },
        "question_1_model": {
            "stage_id": "question_1_model",
            "result": "revise",
            "missing_criteria": ["validation_plan"],
        },
    }
    parent.status = MissionStatus.CANCELLED
    parent.state_version = 17
    parent.last_item_seq = 42
    review_common = {
        "mission_id": parent_receipt.mission_id,
        "output_key": "q1.problem_brief",
        "target_kind": "document",
        "target_room": "documents",
        "target_ref": "prism-file:problem-brief",
        "base_revision_ref": None,
        "base_hash": None,
        "title": "Problem brief",
        "summary": None,
        "risk_level": MissionRiskLevel.MEDIUM,
        "review_required_reason": None,
        "preview_json": {"artifact_kind": "modeling_problem_brief"},
        "preview_ref": None,
        "preview_hash": "b" * 64,
        "preview_expires_at": None,
        "requires_explicit_review": True,
        "batch_acceptable": True,
        "suggested_selected": False,
        "decision_json": None,
        "decided_by": None,
        "decided_at": None,
        "created_at": deps["clock"].now(),
    }
    deps["store"].review_items[parent_receipt.mission_id] = {
        "problem-brief": MissionReviewItemPayload(
            **review_common,
            review_item_id="problem-brief",
            source_item_seq=12,
            status=MissionReviewStatus.SUPERSEDED,
            updated_at=deps["clock"].now(),
        ),
        "problem-brief-final": MissionReviewItemPayload(
            **review_common,
            review_item_id="problem-brief-final",
            source_item_seq=31,
            status=MissionReviewStatus.COMMITTED,
            updated_at=deps["clock"].now() + timedelta(seconds=1),
        ),
    }

    child_receipt = await runtime.start(
        start_request(
            parent_mission_id=parent_receipt.mission_id,
            mission_idempotency_key="child-start-1",
            mission_policy_id="math_modeling_solution",
            model_id="gpt-5.6-luna",
            runtime_context_json=runtime_context,
            snapshot_json={"intake": {"scope": "question_1"}},
        )
    )
    child = await deps["store"].get(child_receipt.mission_id)

    assert child is not None
    assert child.snapshot_json["intake"] == {"scope": "question_1"}
    assert set(child.snapshot_json["stage_acceptance"]) == {"problem_understanding"}
    assert child.snapshot_json["mission_lineage"] == {
        "source_mission_id": parent_receipt.mission_id,
        "source_state_version": 17,
        "source_last_item_seq": 42,
        "source_status": "cancelled",
        "policy_content_hash": "a" * 64,
        "inherited_stage_ids": ["problem_understanding"],
        "upstream_refs": [
            {
                "stage_id": "problem_understanding",
                "source_ref": "problem-brief",
                "target_ref": "prism-file:problem-brief",
                "target_kind": "document",
                "output_key": "q1.problem_brief",
            }
        ],
    }

    persisted_child = deps["store"].runs[child.mission_id]
    persisted_child.status = MissionStatus.FAILED
    persisted_child.state_version = 23
    persisted_child.last_item_seq = 51
    grandchild_receipt = await runtime.start(
        start_request(
            parent_mission_id=child.mission_id,
            mission_idempotency_key="grandchild-start-1",
            mission_policy_id="math_modeling_solution",
            model_id="gpt-5.6-luna",
            runtime_context_json=runtime_context,
        )
    )
    grandchild = await deps["store"].get(grandchild_receipt.mission_id)

    assert grandchild is not None
    assert grandchild.snapshot_json["mission_lineage"]["upstream_refs"] == [
        {
            "stage_id": "problem_understanding",
            "source_ref": "problem-brief",
            "target_ref": "prism-file:problem-brief",
            "target_kind": "document",
            "output_key": "q1.problem_brief",
        }
    ]


@pytest.mark.asyncio
async def test_continuation_inherits_pinned_inputs_and_accepted_internal_refs(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    runtime_context = {"policy_content_hash": "a" * 64}
    first_input_ref = f"mission-input:{'1' * 64}"
    second_input_ref = f"mission-input:{'2' * 64}"
    candidate_ref = f"artifact-candidate:{'3' * 64}"

    def manifest(input_ref: str, source_digest: str) -> dict[str, Any]:
        digest = input_ref.removeprefix("mission-input:")
        return {
            "schema_version": "1",
            "input_ref": input_ref,
            "workspace_id": "workspace-1",
            "thread_id": "thread-1",
            "filename": f"{digest[:4]}.pdf",
            "mime_type": "application/pdf",
            "extractor": "pdf_text",
            "content_hash": f"sha256:{digest}",
            "source_content_hash": f"sha256:{source_digest}",
            "source_size_bytes": 100,
            "text_size_bytes": 80,
            "text_chars": 40,
        }

    parent_receipt = await runtime.start(
        start_request(
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
            snapshot_json={
                "mission_inputs": [manifest(first_input_ref, "4" * 64)],
            },
        )
    )
    parent = deps["store"].runs[parent_receipt.mission_id]
    parent.snapshot_json["stage_acceptance"] = {
        "question_3_model": {
            "stage_id": "question_3_model",
            "result": "pass",
            "artifact_refs": [candidate_ref],
            "evidence_refs": [first_input_ref],
        }
    }
    parent.snapshot_json["stage_item_counts"] = {"problem_questions": 3}
    deps["store"].seed_items(
        parent.mission_id,
        [
            MissionItemDraftPayload(
                item_type="artifact",
                operation_id="parent-question-3-candidate",
                phase="completed",
                stage_id="question_3_model",
                producer="tool_orchestrator",
                summary="Verified third-question model",
                payload_json={
                    "reference_id": candidate_ref,
                    "kind": "artifact_candidate",
                    "title": "第三问模型",
                    "verified": True,
                    "metadata": {},
                },
                payload_ref=candidate_ref,
            )
        ],
    )
    parent.status = MissionStatus.FAILED

    child_receipt = await runtime.start(
        start_request(
            parent_mission_id=parent_receipt.mission_id,
            mission_idempotency_key="continuation-inputs",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
            snapshot_json={
                "mission_inputs": [manifest(second_input_ref, "5" * 64)],
            },
        )
    )
    child = await deps["store"].get(child_receipt.mission_id)

    assert child is not None
    assert [
        item["input_ref"] for item in child.snapshot_json["mission_inputs"]
    ] == [first_input_ref, second_input_ref]
    assert child.snapshot_json["stage_item_counts"] == {"problem_questions": 3}
    assert child.snapshot_json["mission_lineage"]["upstream_refs"] == [
        {
            "stage_id": "question_3_model",
            "source_ref": candidate_ref,
            "target_ref": candidate_ref,
            "target_kind": "internal_candidate",
            "output_key": "",
        },
        {
            "stage_id": "question_3_model",
            "source_ref": first_input_ref,
            "target_ref": first_input_ref,
            "target_kind": "mission_input",
            "output_key": "",
        },
    ]
    lineaged_references = await runtime._reference_items(child.mission_id)
    assert [item.payload_ref for item in lineaged_references] == [candidate_ref]
    assert lineaged_references[0].mission_id == parent.mission_id

    await runtime.run_slice(child.mission_id, worker_id="worker-lineage-context")

    assert deps["agent"].contexts
    assert [
        item.payload_ref for item in deps["agent"].contexts[-1].reference_items
    ] == [candidate_ref]


@pytest.mark.asyncio
async def test_child_mission_rejects_unpinned_or_live_parent_state(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    parent_receipt = await runtime.start(
        start_request(
            mission_policy_id="math_modeling_solution",
            runtime_context_json={"policy_content_hash": "a" * 64},
        )
    )

    child_request = start_request(
        parent_mission_id=parent_receipt.mission_id,
        mission_idempotency_key="child-start-2",
        mission_policy_id="math_modeling_solution",
        runtime_context_json={"policy_content_hash": "b" * 64},
    )
    with pytest.raises(MissionStartRejectedError, match="must be terminal"):
        await runtime.start(child_request)

    deps["store"].runs[parent_receipt.mission_id].status = MissionStatus.CANCELLED
    with pytest.raises(MissionStartRejectedError, match="content hash"):
        await runtime.start(child_request)


@pytest.mark.asyncio
async def test_stage_guard_blocks_tool_before_prerequisites_pass(runtime_factory) -> None:
    tools = FakeTools()
    decision = tool_decision("guarded-tool").model_copy(update={"stage_id": "method"})
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([decision, complete_decision()]),
        tools=tools,
        quality=FakeQuality(missing_prerequisites=("scope",)),
    )
    receipt = await runtime.start(start_request(runtime_context_json={"stage_contracts": {"method": {}}}))

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert tools.calls == []
    items = deps["store"].items[receipt.mission_id]
    assert any(item.item_type == "error" and "prerequisites" in str(item.payload_json.get("detail") or "") for item in items)


@pytest.mark.asyncio
async def test_long_mission_advances_through_multiple_bounded_slices(runtime_factory) -> None:
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=1,
        max_tool_steps=4,
    )
    agent = ScriptedAgent(
        [
            continue_decision("plan-1"),
            continue_decision("plan-2"),
            complete_decision(),
        ]
    )
    runtime, deps = runtime_factory(agent=agent, limits=limits)
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    third = await runtime.run_slice(receipt.mission_id, worker_id="worker-3")

    assert [first.outcome, second.outcome, third.outcome] == [
        MissionSliceOutcome.YIELDED,
        MissionSliceOutcome.YIELDED,
        MissionSliceOutcome.COMPLETED,
    ]
    assert first.model_turns == second.model_turns == third.model_turns == 1
    assert third.lease_epoch == 3
    checkpoints = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "context_checkpoint"]
    assert len(checkpoints) == 2


@pytest.mark.asyncio
async def test_slice_yields_before_starting_an_expensive_step_without_time_reserve(
    runtime_factory,
) -> None:
    clock = MutableClock()

    async def slow_plan(_context: Any) -> MissionAgentDecision:
        clock.advance(6)
        return continue_decision("slow-plan")

    agent = ScriptedAgent([slow_plan, complete_decision()])
    runtime, deps = runtime_factory(
        agent=agent,
        clock=clock,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            next_step_reserve_seconds=5,
        ),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert first.outcome is MissionSliceOutcome.YIELDED
    assert first.model_turns == 1
    assert second.outcome is MissionSliceOutcome.COMPLETED
    assert len([item for item in deps["store"].items[receipt.mission_id] if item.item_type == "context_checkpoint"]) == 1


@pytest.mark.asyncio
async def test_stale_worker_cannot_write_after_lease_takeover(runtime_factory) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    limits = MissionSliceLimits(
        wall_time_seconds=1,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=6,
        max_model_turns=2,
        max_tool_steps=2,
    )

    async def takeover(_context: Any) -> MissionAgentDecision:
        clock.advance(7)
        current = await store.get(receipt.mission_id)
        assert current is not None
        await store.claim_lease(
            receipt.mission_id,
            MissionLeaseClaimPayload(
                worker_id="worker-new",
                expected_state_version=current.state_version,
                ttl_seconds=6,
            ),
        )
        return complete_decision()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([takeover]),
        clock=clock,
        store=store,
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-old")
    run = await store.get(receipt.mission_id)

    assert telemetry.outcome == MissionSliceOutcome.YIELDED
    assert telemetry.reason == "lease_fence_lost"
    assert run is not None and run.lease_owner == "worker-new"
    assert run.status.value == "running"
    assert deps["agent"].contexts


@pytest.mark.asyncio
async def test_expired_same_owner_lease_conflict_yields_without_retry_loop(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    heartbeat_calls = 0
    original_heartbeat = store.heartbeat_lease

    async def counting_heartbeat(mission_id: str, command: Any):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        return await original_heartbeat(mission_id, command)

    store.heartbeat_lease = counting_heartbeat  # type: ignore[method-assign]

    async def expire_lease(_context: Any) -> MissionAgentDecision:
        clock.advance(2)
        clock.advance_wall_clock(28)
        raise MissionAgentProtocolError("retry after the durable lease expired")

    runtime, _deps = runtime_factory(
        agent=ScriptedAgent([expire_lease]),
        clock=clock,
        store=store,
        limits=MissionSliceLimits(
            wall_time_seconds=20,
            shutdown_margin_seconds=1,
            heartbeat_interval_seconds=1,
            lease_ttl_seconds=25,
            max_model_turns=2,
            max_tool_steps=2,
        ),
    )
    receipt = await runtime.start(start_request())

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-old")

    assert telemetry.outcome == MissionSliceOutcome.YIELDED
    assert telemetry.reason == "lease_fence_lost"
    assert heartbeat_calls == 1


@pytest.mark.asyncio
async def test_event_publish_failure_never_rolls_back_mission(runtime_factory) -> None:
    events = FakeEvents(fail=True)
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([complete_decision()]),
        events=events,
    )

    receipt = await runtime.start(start_request())
    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert events.events == []


@pytest.mark.asyncio
async def test_dropped_continuation_is_recovered_by_reconciler(runtime_factory) -> None:
    failed_wakeups = FakeWakeups(fail=True)
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=1,
        max_tool_steps=2,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([continue_decision("plan-1")]),
        wakeups=failed_wakeups,
        limits=limits,
    )
    receipt = await runtime.start(start_request())
    yielded = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    due = await deps["store"].get(receipt.mission_id)

    recovered_wakeups = FakeWakeups()
    reconciler = MissionReconciler(
        store=deps["store"],
        wakeups=recovered_wakeups,
        events=deps["events"],
        clock=deps["clock"],
    )
    published = await reconciler.reconcile_once(worker_id="reconciler-1")

    assert yielded.outcome == MissionSliceOutcome.YIELDED
    assert yielded.continuation_published is False
    assert due is not None and due.next_wakeup_at is not None
    assert published == [receipt.mission_id]
    assert recovered_wakeups.published == [(receipt.mission_id, None)]


@pytest.mark.asyncio
async def test_reconciler_publish_failure_releases_dispatch_and_expiry_republishes(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]), wakeups=FakeWakeups(fail=True))
    receipt = await runtime.start(start_request())
    failed = MissionReconciler(
        store=deps["store"],
        wakeups=FakeWakeups(fail=True),
        events=deps["events"],
        clock=deps["clock"],
        lease_ttl_seconds=5,
    )
    assert await failed.reconcile_once(worker_id="reconciler-a") == []

    wakeups = FakeWakeups()
    healthy = MissionReconciler(
        store=deps["store"],
        wakeups=wakeups,
        events=deps["events"],
        clock=deps["clock"],
        lease_ttl_seconds=5,
    )
    assert await healthy.reconcile_once(worker_id="reconciler-b") == [receipt.mission_id]
    assert await healthy.reconcile_once(worker_id="reconciler-c") == []
    deps["clock"].advance(6)
    assert await healthy.reconcile_once(worker_id="reconciler-c") == [receipt.mission_id]


@pytest.mark.asyncio
async def test_command_arriving_during_model_turn_is_applied_at_next_safe_boundary(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    observed_command_contexts: list[int] = []

    async def concurrent_command(_context: Any) -> MissionAgentDecision:
        await store.append_command(
            receipt.mission_id,
            command_id="steer-1",
            command_type="correction",
            summary="Focus on Non-IID evaluation",
            payload_json={"constraint": "Non-IID"},
        )
        return continue_decision("stale-decision")

    def finish_after_command(context: Any) -> MissionAgentDecision:
        observed_command_contexts.append(len(context.pending_commands))
        return complete_decision()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([concurrent_command, finish_after_command]),
        clock=clock,
        store=store,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await store.get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None
    assert run.last_applied_command_seq == run.last_command_seq
    assert observed_command_contexts == [1]
    summaries = [item.summary for item in store.items[receipt.mission_id]]
    assert "continue stale-decision" not in summaries
    assert deps["agent"].contexts[0].pending_commands == []


@pytest.mark.asyncio
async def test_cancel_is_terminal_and_future_delivery_is_noop(runtime_factory) -> None:
    agent = ScriptedAgent([complete_decision()])
    runtime, deps = runtime_factory(agent=agent)
    receipt = await runtime.start(start_request())

    cancelled = await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-1",
        reason="User changed direction",
    )
    replay = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert cancelled.status.value == "cancelled"
    assert replay.outcome == MissionSliceOutcome.TERMINAL
    assert replay.reason == "mission_already_terminal"
    assert agent.contexts == []
    assert deps["billing"].settled == [receipt.mission_id]


@pytest.mark.asyncio
async def test_cancel_during_model_turn_stops_stale_driver_before_dispatch(
    runtime_factory,
) -> None:
    async def cancel_during_turn(_context: Any) -> MissionAgentDecision:
        await runtime.cancel(
            receipt.mission_id,
            request_id="cancel-concurrent",
            reason="Stop now",
        )
        return tool_decision("must-not-run")

    tools = FakeTools()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([cancel_during_turn]),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.TERMINAL
    assert result.reason == "mission_became_terminal_during_slice"
    assert run is not None and run.status.value == "cancelled"
    assert tools.calls == []


@pytest.mark.asyncio
async def test_terminal_mission_cannot_resume(runtime_factory) -> None:
    runtime, _deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    with pytest.raises(DataServiceClientError):
        await runtime.resume(
            receipt.mission_id,
            request_id="resume-after-complete",
            input_json={"continue": True},
        )


@pytest.mark.asyncio
async def test_budget_limit_yields_only_after_checkpoint_and_lease_release(
    runtime_factory,
) -> None:
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=1,
        max_tool_steps=2,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([continue_decision("plan-1")]),
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.YIELDED
    assert run is not None and run.lease_owner is None
    assert run.next_wakeup_at is not None
    assert run.context_checkpoint_ref is not None
    checkpoint = deps["store"].items[receipt.mission_id][-1]
    assert checkpoint.item_type == "context_checkpoint"
    assert checkpoint.payload_json["version"] == 2
    assert checkpoint.payload_json["objective"] == run.objective
    assert checkpoint.payload_json["recent_decisions"][0]["type"] == "plan"


@pytest.mark.asyncio
async def test_checkpoint_keeps_only_stable_reference_ids(runtime_factory) -> None:
    tools = FakeTools()
    tools.outcomes["search-1"] = MissionPortOutcome(
        status=MissionPortOutcomeStatus.COMPLETED,
        summary="tool completed",
        payload_json={
            "evidence_refs": [
                {
                    "ref_id": "evidence:verified-1",
                    "kind": "verified_source",
                    "metadata": {"preview": "x" * 20_000},
                },
                "evidence:verified-2",
            ],
            "artifact_refs": [
                {
                    "ref_id": "sandbox-artifact:result-1",
                    "kind": "sandbox_artifact",
                    "metadata": {"manifest": "y" * 20_000},
                }
            ],
        },
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-1")]),
        tools=tools,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            max_model_turns=1,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome is MissionSliceOutcome.YIELDED
    checkpoint = deps["store"].items[receipt.mission_id][-1]
    assert checkpoint.item_type == "context_checkpoint"
    assert checkpoint.payload_json["evidence_refs"] == [
        "evidence:verified-1",
        "evidence:verified-2",
    ]
    assert checkpoint.payload_json["artifact_refs"] == ["sandbox-artifact:result-1"]
    assert len(str(checkpoint.payload_json)) < 2_000


@pytest.mark.asyncio
async def test_duplicate_operation_id_does_not_repeat_tool_effect(runtime_factory) -> None:
    tools = FakeTools()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [
                tool_decision("search-1"),
                tool_decision("search-1"),
                complete_decision(),
            ]
        ),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert tools.calls == ["search-1"]
    assert tools.effects == {"search-1"}
    run = await deps["store"].get(receipt.mission_id)
    assert run is not None and run.status.value == "completed"


@pytest.mark.asyncio
async def test_crash_recovery_reuses_inflight_operation_id_after_higher_epoch(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    tools = FakeTools()
    tools.crash_once.add("search-crash")
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=4,
        max_tool_steps=4,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-crash"), complete_decision()]),
        clock=clock,
        store=store,
        tools=tools,
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    with pytest.raises(SimulatedWorkerCrash):
        await runtime.run_slice(receipt.mission_id, worker_id="worker-crashed")
    crashed = await store.get(receipt.mission_id)
    assert crashed is not None and crashed.lease_owner == "worker-crashed"

    clock.advance(21)
    recovered = await runtime.run_slice(receipt.mission_id, worker_id="worker-recovery")

    assert recovered.outcome == MissionSliceOutcome.COMPLETED
    assert recovered.lease_epoch == 2
    assert tools.calls == ["search-crash", "search-crash"]
    assert tools.effects == {"search-crash"}
    terminal = await deps["store"].get(receipt.mission_id)
    assert terminal is not None and terminal.status.value == "completed"


@pytest.mark.asyncio
async def test_billing_pause_uses_waiting_status_and_can_resume(runtime_factory) -> None:
    pause = MissionPauseRequest(
        request_id="budget-1",
        reason="budget",
        summary="Confirm mission credit use",
        pending_request={"credits": 8},
    )
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    deps["billing"].reservation_outcome = BillingOutcome(
        allowed=False,
        pause_request=pause,
        summary="Credits need confirmation",
    )
    receipt = await runtime.start(start_request())

    waiting = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert waiting.outcome == MissionSliceOutcome.WAITING
    assert run is not None and run.status.value == "waiting"
    assert run.snapshot_json["waiting_reason"] == "budget"
    assert run.lease_owner is None


@pytest.mark.asyncio
async def test_permission_pause_resume_matches_request_and_restores_inflight_tool(
    runtime_factory,
) -> None:
    class PausingTool:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        async def execute(self, request: Any) -> MissionPortOutcome:
            self.requests.append(request)
            if len(self.requests) == 1:
                return MissionPortOutcome(
                    status=MissionPortOutcomeStatus.WAITING,
                    summary="External source access needs confirmation",
                    pause_request=MissionPauseRequest(
                        request_id="permission-1",
                        reason="permission",
                        summary="Confirm external source access",
                        pending_request={"tool_name": request.tool_name},
                    ),
                )
            assert any(
                item.item_type == "resume_input" and item.operation_id.startswith("pause:permission-1:")
                for item in request.recent_items
            )
            return MissionPortOutcome(
                status=MissionPortOutcomeStatus.COMPLETED,
                summary="External source access completed",
                payload_json={"source_ref": "source://1"},
            )

    tools = PausingTool()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-permission"), complete_decision()]),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    waiting = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    paused = await deps["store"].get(receipt.mission_id)
    assert paused is not None
    pending_request = paused.snapshot_json["pending_request"]
    runtime_request_id = pending_request["request_id"]
    assert runtime_request_id.startswith("pause:permission-1:")
    assert pending_request["semantic_request_id"] == "permission-1"
    with pytest.raises(MissionResumeRequestMismatchError):
        await runtime.resume(
            receipt.mission_id,
            request_id="wrong-request",
            input_json={"decision": "allow_once"},
        )
    resumed = await runtime.resume(
        receipt.mission_id,
        request_id=runtime_request_id,
        input_json={"decision": "allow_once"},
    )
    replay = await runtime.resume(
        receipt.mission_id,
        request_id=runtime_request_id,
        input_json={"decision": "allow_once"},
    )
    completed = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert waiting.outcome == MissionSliceOutcome.WAITING
    assert resumed.state_version == replay.state_version
    assert completed.outcome == MissionSliceOutcome.COMPLETED
    assert len(tools.requests) == 2
    resume_items = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "resume_input"]
    assert len(resume_items) == 1


@pytest.mark.asyncio
async def test_repeated_semantic_pause_requests_receive_distinct_runtime_ids(runtime_factory) -> None:
    class RepeatingPauseTool:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, request: Any) -> MissionPortOutcome:
            self.calls += 1
            if self.calls <= 2:
                return MissionPortOutcome(
                    status=MissionPortOutcomeStatus.WAITING,
                    summary="Model provider is rate limited",
                    pause_request=MissionPauseRequest(
                        request_id="provider-rate-limit",
                        reason="external_data",
                        summary="Retry after the provider window clears",
                        pending_request={"retry_after_seconds": 45},
                    ),
                )
            return MissionPortOutcome(
                status=MissionPortOutcomeStatus.COMPLETED,
                summary="Model request completed",
                payload_json={"source_ref": "source://1"},
            )

    tools = RepeatingPauseTool()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-rate-limit"), complete_decision()]),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    first_wait = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    first_run = await deps["store"].get(receipt.mission_id)
    assert first_run is not None
    first_request = first_run.snapshot_json["pending_request"]
    await runtime.resume(
        receipt.mission_id,
        request_id=first_request["request_id"],
        input_json={"decision": "retry"},
    )

    second_wait = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    second_run = await deps["store"].get(receipt.mission_id)
    assert second_run is not None
    second_request = second_run.snapshot_json["pending_request"]

    assert first_wait.outcome == MissionSliceOutcome.WAITING
    assert second_wait.outcome == MissionSliceOutcome.WAITING
    assert first_request["semantic_request_id"] == "provider-rate-limit"
    assert second_request["semantic_request_id"] == "provider-rate-limit"
    assert first_request["request_id"] != second_request["request_id"]

    await runtime.resume(
        receipt.mission_id,
        request_id=second_request["request_id"],
        input_json={"decision": "retry"},
    )
    completed = await runtime.run_slice(receipt.mission_id, worker_id="worker-3")
    assert completed.outcome == MissionSliceOutcome.COMPLETED


@pytest.mark.asyncio
async def test_completed_mission_can_retain_pending_review_items(runtime_factory) -> None:
    review_decision = MissionAgentDecision(
        decision_id="review-decision-1",
        kind="review",
        operation_id="review-op-1",
        stage_id="stage-1",
        summary="Stage one draft is reviewable",
        payload_json={"candidate_ref": "artifact://draft"},
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([review_decision, complete_decision()]),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(start_request())
    stored = deps["store"].runs[receipt.mission_id]
    stored.active_stage_id = "stage-1"
    stored.snapshot_json["stage_acceptance"] = {
        "stage-1": {
            "result": "pass",
            "artifact_refs": ["artifact-candidate:" + "a" * 64],
        }
    }

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    assert first.outcome == MissionSliceOutcome.YIELDED
    checkpoints = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "context_checkpoint"]
    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.pending_review_count == 1
    review_items = await deps["store"].list_review_items(receipt.mission_id)
    assert review_items[0].target_kind == "document"
    assert len(review_items[0].preview_hash or "") == 64
    assert checkpoints[-1].payload_json["ledger_through_seq"] > 0


@pytest.mark.asyncio
async def test_terminal_review_pause_completes_execution_without_accepting_output(
    runtime_factory,
) -> None:
    review_decision = MissionAgentDecision(
        decision_id="review-final",
        kind="review",
        operation_id="review-op-final",
        stage_id="stage-1",
        summary="Final draft is reviewable",
        payload_json={"candidate_ref": "artifact://draft"},
    )
    review_pause = MissionAgentDecision(
        decision_id="pause-final-review",
        kind="pause",
        summary="Wait for final draft confirmation",
        pause_request=MissionPauseRequest(
            request_id="confirm-final-draft",
            reason="approval",
            summary="Please confirm the final draft",
            pending_request={"review_item_id": "review-review-op-final"},
        ),
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([review_decision, review_pause]),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(start_request())
    stored = deps["store"].runs[receipt.mission_id]
    stored.active_stage_id = "stage-1"
    stored.snapshot_json["stage_acceptance"] = {
        "stage-1": {
            "result": "pass",
            "artifact_refs": ["artifact-candidate:" + "a" * 64],
        }
    }

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    completed = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)
    review_items = await deps["store"].list_review_items(receipt.mission_id)
    pause_items = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "pause_request"
    ]
    terminal_update = next(
        item
        for item in reversed(deps["store"].items[receipt.mission_id])
        if item.item_type == "status_update"
    )

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert completed.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.pending_review_count == 1
    assert review_items[0].status.value == "pending"
    assert pause_items == []
    assert terminal_update.producer == "mission_runtime"
    assert terminal_update.payload_json == {"review_pending": True}


@pytest.mark.asyncio
async def test_transient_model_timeout_yields_with_backoff_without_failing(runtime_factory) -> None:
    def timeout(_context):
        raise TimeoutError("provider read timed out")

    runtime, deps = runtime_factory(agent=ScriptedAgent([timeout]))
    receipt = await runtime.start(start_request())
    wakeups_after_start = len(deps["wakeups"].published)

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.YIELDED
    assert run is not None and run.status.value == "running"
    assert run.next_wakeup_at == deps["clock"].now() + timedelta(seconds=5)
    assert len(deps["wakeups"].published) == wakeups_after_start + 1
    assert deps["wakeups"].delays[-1] == 5
    assert result.continuation_published is True
    assert run.snapshot_json["loop_guard"] == {
        "consecutive_failures": 0,
        "transient_failures": 1,
    }
    error = next(item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error")
    assert error.payload_json["recoverable"] is True


@pytest.mark.asyncio
async def test_successful_decision_clears_recovered_transient_error(runtime_factory) -> None:
    def timeout(_context):
        raise TimeoutError("provider read timed out")

    runtime, deps = runtime_factory(agent=ScriptedAgent([timeout, complete_decision()]))
    receipt = await runtime.start(start_request())

    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    deps["clock"].advance(5)
    completed = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)

    assert completed.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None
    assert "last_error" not in run.snapshot_json
    assert "degraded_reason" not in run.snapshot_json
    assert "next_actions" not in run.snapshot_json
    assert run.snapshot_json["loop_guard"] == {
        "consecutive_failures": 0,
        "transient_failures": 0,
    }


@pytest.mark.asyncio
async def test_stage_scoped_operation_updates_active_stage_without_continue(runtime_factory) -> None:
    decision = tool_decision("stage-tool").model_copy(update={"stage_id": "question_1_model"})
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([decision]),
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            max_model_turns=1,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.YIELDED
    assert run is not None and run.active_stage_id == "question_1_model"


@pytest.mark.asyncio
async def test_quality_revision_requires_new_stage_progress_before_retry(runtime_factory) -> None:
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([quality_decision("quality-1"), quality_decision("quality-2")]),
        quality=FakeQuality(verdict=StageQualityVerdict.REVISE),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    deps["store"].runs[receipt.mission_id].snapshot_json["stage_acceptance"] = {
        "question_1_solution_validation": {
            "result": "revise",
            "next_action": "revise_existing",
        }
    }
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert second.outcome == MissionSliceOutcome.YIELDED
    assert deps["quality"].calls == ["quality-1"]
    invalid = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error" and item.operation_id == "decision-quality-2"]
    assert invalid
    assert "next_action=" in invalid[-1].payload_json["detail"]


@pytest.mark.asyncio
async def test_repeated_stage_operation_failures_stop_without_unbounded_replanning(runtime_factory) -> None:
    tools = FakeTools()
    decisions = [tool_decision(f"failed-tool-{index}").model_copy(update={"stage_id": "question_1_solution_validation"}) for index in range(1, 4)]
    for decision in decisions:
        assert decision.operation_id is not None
        tools.outcomes[decision.operation_id] = MissionPortOutcome(
            status=MissionPortOutcomeStatus.FAILED,
            summary="script execution failed",
        )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(decisions),
        tools=tools,
        limits=MissionSliceLimits(
            max_model_turns=1,
            max_operation_failures_per_stage=3,
        ),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    third = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert second.outcome == MissionSliceOutcome.YIELDED
    assert third.outcome == MissionSliceOutcome.TERMINAL
    assert run is not None and run.status.value == "failed"
    assert run.snapshot_json["failure_reason"] == "stage_execution_failure_budget_exhausted"
    assert run.snapshot_json["operation_failure_guard"]["question_1_solution_validation"]["failure_count"] == 3
    errors = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error"]
    assert errors[-1].payload_json == {
        "failure_count": 3,
        "failure_limit": 3,
        "recoverable": False,
    }


@pytest.mark.asyncio
async def test_repeated_transient_model_timeouts_stop_instead_of_retrying_forever(
    runtime_factory,
) -> None:
    def timeout(_context):
        raise TimeoutError("provider read timed out")

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([timeout, timeout]),
        limits=MissionSliceLimits(max_transient_failures=2),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert second.outcome == MissionSliceOutcome.TERMINAL
    assert run is not None and run.status.value == "failed"
    assert run.snapshot_json["failure_reason"] == "model_service_unavailable"
    errors = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error"]
    assert errors[-1].payload_json["recoverable"] is False


@pytest.mark.asyncio
async def test_transient_provider_server_error_yields_with_backoff_without_failing(runtime_factory) -> None:
    class ProviderServerError(Exception):
        status_code = 502

    def unavailable(_context):
        raise ProviderServerError("upstream temporarily unavailable")

    runtime, deps = runtime_factory(agent=ScriptedAgent([unavailable]))
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.YIELDED
    assert run is not None and run.status.value == "running"
    assert run.next_wakeup_at == deps["clock"].now() + timedelta(seconds=5)
    assert run.snapshot_json["loop_guard"] == {
        "consecutive_failures": 0,
        "transient_failures": 1,
    }


@pytest.mark.asyncio
async def test_agent_protocol_error_is_repaired_inside_slice_without_error_item(
    runtime_factory,
) -> None:
    def malformed(_context):
        raise MissionAgentProtocolError("mission_step fields were invalid")

    def repaired(context):
        assert context.protocol_feedback == "mission_step fields were invalid"
        return complete_decision()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([malformed, repaired]),
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            max_model_turns=2,
        ),
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert result.model_turns == 2
    assert not any(item.item_type == "error" for item in deps["store"].items[receipt.mission_id])


@pytest.mark.asyncio
async def test_repeated_agent_protocol_error_yields_as_recoverable_schema_repair(
    runtime_factory,
) -> None:
    def malformed(_context):
        raise MissionAgentProtocolError("mission_step fields were invalid")

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([malformed, malformed]),
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            max_model_turns=2,
        ),
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.YIELDED
    assert run is not None and run.status.value == "running"
    assert run.snapshot_json["next_actions"] == ["repair_structured_decision"]
    error = next(item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error")
    assert error.payload_json["recoverable"] is True

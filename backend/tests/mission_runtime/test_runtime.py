from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest

from src.contracts.model_usage import ModelUsage, ModelUsageReceipt
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    StageCriterion,
    StageInstantiationRule,
)
from src.dataservice_client.contracts.mission import (
    MissionDispatchClaimPayload,
    MissionItemDraftPayload,
    MissionItemPhase,
    MissionLeaseClaimPayload,
    MissionLeaseReleasePayload,
    MissionReviewItemPayload,
    MissionReviewStatus,
    MissionRiskLevel,
    MissionStatus,
    MissionUserCommandPayload,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    MISSION_DISPATCH_TTL_SECONDS,
    MissionAgentDecision,
    MissionAgentProtocolError,
    MissionContinuationDirective,
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


def test_slice_limits_reject_a_heartbeat_that_cannot_refresh_before_expiry() -> None:
    with pytest.raises(ValueError, match="two heartbeat intervals"):
        MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=10,
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


def subagent_decision(operation_id: str) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=f"decision-{operation_id}",
        kind="subagent",
        operation_id=operation_id,
        stage_id="literature",
        summary="Delegate one bounded research facet",
        payload_json={
            "task_summary": "Inspect one bounded research facet",
            "input_scope": {"query": "federated PEFT"},
        },
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
            "item_counts": ({"problem_questions": item_count} if item_count is not None else {}),
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
            previous_item_prerequisite_templates=("question_{index}_solution_validation",),
        ),
        advance_condition="The question solution passes.",
        stop_condition="The question cannot be solved reliably.",
    )
    solution_validation = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="math_modeling_solution.question_solution_validation",
        version=1,
        mission_policy_id="math_modeling_solution",
        workspace_type="math_modeling",
        stage_id="question_solution_validation",
        stage_goal="Validate one question solution.",
        minimum_criteria=(
            StageCriterion(
                criterion_id="validated_result",
                description="The computed result is reproducible and validated.",
            ),
        ),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        instantiation=StageInstantiationRule(
            mode="per_item",
            source_context_key="problem_questions",
            instance_id_template="question_{index}_solution_validation",
            same_item_prerequisite_templates=("question_{index}_model",),
        ),
        advance_condition="The validated solution passes.",
        stop_condition="The solution cannot be validated reliably.",
    )
    paper_integration = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="math_modeling_solution.paper_integration",
        version=1,
        mission_policy_id="math_modeling_solution",
        workspace_type="math_modeling",
        stage_id="paper_integration",
        stage_goal="Integrate all validated questions.",
        minimum_criteria=(
            StageCriterion(
                criterion_id="integrated_paper",
                description="All validated question results are integrated.",
            ),
        ),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        all_item_prerequisite_templates=("question_{index}_solution_validation",),
        all_item_source_context_key="problem_questions",
        advance_condition="Every validated question is integrated.",
        stop_condition="The paper cannot be integrated reliably.",
    )
    context: dict[str, Any] = {
        "required_stage_ids": ["question_model"],
        "stage_contracts": {
            understanding.stage_id: understanding.model_dump(mode="json"),
            question_model.stage_id: question_model.model_dump(mode="json"),
            solution_validation.stage_id: solution_validation.model_dump(mode="json"),
            paper_integration.stage_id: paper_integration.model_dump(mode="json"),
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


@pytest.mark.asyncio
async def test_workspace_model_call_start_is_adopted_after_lost_append_ack(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    original_append = store.append_items
    lost_ack = False

    async def append_with_lost_start_ack(mission_id, command):
        nonlocal lost_ack
        result = await original_append(mission_id, command)
        if (
            not lost_ack
            and len(command.items) == 1
            and command.items[0].item_type == "model_call_started"
        ):
            lost_ack = True
            raise RuntimeError("model start append acknowledgement was lost")
        return result

    store.append_items = append_with_lost_start_ack  # type: ignore[method-assign]
    agent = ScriptedAgent([complete_decision()])
    runtime, deps = runtime_factory(
        agent=agent,
        clock=clock,
        store=store,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    items = deps["store"].items[receipt.mission_id]
    starts = [item for item in items if item.item_type == "model_call_started"]
    usage = [item for item in items if item.item_type == "usage_receipt"]
    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert lost_ack is True
    assert agent.provider_calls == 1
    assert len(starts) == len(usage) == 1
    assert starts[0].operation_id == usage[0].operation_id


@pytest.mark.asyncio
async def test_workspace_usage_receipt_is_idempotent_after_lost_append_ack(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    original_append = store.append_items
    lost_ack = False

    async def append_with_lost_usage_ack(mission_id, command):
        nonlocal lost_ack
        result = await original_append(mission_id, command)
        if (
            not lost_ack
            and len(command.items) == 1
            and command.items[0].item_type == "usage_receipt"
        ):
            lost_ack = True
            raise RuntimeError("usage append acknowledgement was lost")
        return result

    store.append_items = append_with_lost_usage_ack  # type: ignore[method-assign]
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([complete_decision()]),
        clock=clock,
        store=store,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    items = deps["store"].items[receipt.mission_id]
    starts = [item for item in items if item.item_type == "model_call_started"]
    usage = [item for item in items if item.item_type == "usage_receipt"]
    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert lost_ack is True
    assert len(starts) == len(usage) == 1
    assert usage[0].operation_id == starts[0].operation_id
    run = await deps["store"].get(receipt.mission_id)
    assert run is not None
    assert run.snapshot_json["resource_usage"]["model_calls"] == 1
    assert run.snapshot_json["resource_usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_cumulative_model_budget_stops_before_the_next_slice_call(
    runtime_factory,
) -> None:
    agent = ScriptedAgent([continue_decision("first-call")])
    runtime, deps = runtime_factory(
        agent=agent,
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 1,
                        "max_tool_operations": 2,
                        "max_subagent_jobs": 2,
                        "stop_after_total_tokens": 10_000,
                    }
                }
            }
        )
    )

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    run = await deps["store"].get(receipt.mission_id)
    assert first.outcome is MissionSliceOutcome.YIELDED
    assert second.outcome is MissionSliceOutcome.TERMINAL
    assert second.reason == "resource_budget_exhausted"
    assert run is not None and run.status is MissionStatus.FAILED
    assert run.snapshot_json["resource_usage"]["model_calls"] == 1
    assert run.snapshot_json["resource_budget_stop"]["dimensions"] == [
        "model_calls"
    ]
    assert len(agent.contexts) == 1


@pytest.mark.asyncio
async def test_token_threshold_equality_stops_before_next_provider_call(
    runtime_factory,
) -> None:
    agent = ScriptedAgent([continue_decision("threshold-reached")])
    runtime, deps = runtime_factory(agent=agent)
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 2,
                        "max_tool_operations": 2,
                        "max_subagent_jobs": 1,
                        "stop_after_total_tokens": 15,
                    }
                }
            }
        )
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert result.reason == "resource_budget_exhausted"
    assert agent.provider_calls == 1
    assert run is not None
    assert run.snapshot_json["resource_usage"]["total_tokens"] == 15
    assert run.snapshot_json["resource_budget_stop"]["dimensions"] == [
        "total_tokens"
    ]


@pytest.mark.asyncio
async def test_tool_budget_stops_before_the_tool_side_effect(runtime_factory) -> None:
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("tool-over-budget")]),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 2,
                        "max_tool_operations": 0,
                        "max_subagent_jobs": 1,
                        "stop_after_total_tokens": 10_000,
                    }
                }
            }
        )
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.FAILED
    assert run.snapshot_json["resource_budget_stop"]["dimensions"] == [
        "tool_operations"
    ]
    assert deps["tools"].calls == []


@pytest.mark.asyncio
async def test_review_mode_change_does_not_resume_waiting_mission(
    runtime_factory,
) -> None:
    agent = ScriptedAgent([])
    runtime, deps = runtime_factory(agent=agent)
    receipt = await runtime.start(start_request())
    stored = deps["store"].runs[receipt.mission_id]
    stored.status = MissionStatus.WAITING
    stored.next_wakeup_at = None
    stored.snapshot_json.update(
        {
            "waiting_reason": "permission",
            "pending_request": {"request_id": "permission-1"},
        }
    )
    await deps["store"].append_command(
        receipt.mission_id,
        MissionUserCommandPayload(
            command_id="review-mode-1",
            command_type="set_review_mode",
            payload_json={"review_mode": "review_all"},
        ),
    )

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert telemetry.outcome is MissionSliceOutcome.WAITING
    assert run is not None
    assert run.status is MissionStatus.WAITING
    assert run.review_mode.value == "review_all"
    assert run.snapshot_json["waiting_reason"] == "permission"
    assert run.snapshot_json["pending_request"] == {"request_id": "permission-1"}
    assert run.last_applied_command_seq == run.last_command_seq
    assert run.lease_owner is None
    assert run.next_wakeup_at is None
    assert agent.contexts == []


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
    receipt = await runtime.start(start_request(runtime_context_json=_per_item_runtime_context()))

    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)

    assert run is not None
    assert run.snapshot_json["stage_item_counts"] == {"problem_questions": 2}
    invalid = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error" and item.operation_id == "decision-quality-count-2"]
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
    receipt = await runtime.start(start_request(runtime_context_json=_per_item_runtime_context()))

    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert run is not None
    assert "stage_acceptance" not in run.snapshot_json
    invalid = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error" and item.operation_id == "decision-quality-count-missing"]
    assert "missing=problem_questions" in invalid[-1].payload_json["detail"]


@pytest.mark.asyncio
async def test_completion_expands_each_per_item_stage_instance(runtime_factory) -> None:
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([complete_decision("complete-1"), complete_decision("complete-2")]),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(start_request(runtime_context_json=_per_item_runtime_context()))
    persisted = deps["store"].runs[receipt.mission_id]
    persisted.snapshot_json.update(
        {
            "stage_item_counts": {"problem_questions": 2},
            "stage_acceptance": {"question_1_model": {"result": "pass"}},
        }
    )

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    persisted.snapshot_json["stage_acceptance"]["question_2_model"] = {"result": "pass"}
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert second.outcome == MissionSliceOutcome.COMPLETED
    invalid = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error" and item.operation_id == "complete-1"]
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
    receipt = await runtime.start(start_request(runtime_context_json=_per_item_runtime_context(terminal_outputs=True)))
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
async def test_review_continuation_invalidates_only_downstream_single_stages(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))

    def contract(stage_id: str, prerequisites: tuple[str, ...] = ()) -> dict[str, Any]:
        return StageAcceptanceContract(
            schema_version="stage_acceptance_contract.v2",
            contract_id=f"sci_research.{stage_id}",
            version=1,
            mission_policy_id="sci_research",
            workspace_type="sci",
            stage_id=stage_id,
            stage_goal=f"Complete {stage_id}.",
            minimum_criteria=(
                StageCriterion(
                    criterion_id=f"{stage_id}_quality",
                    description=f"{stage_id} is complete and well supported.",
                ),
            ),
            allowed_actions_if_failed=("revise_existing", "stop_execution"),
            prerequisite_stage_ids=prerequisites,
            advance_condition=f"{stage_id} passes.",
            stop_condition=f"{stage_id} cannot be completed.",
        ).model_dump(mode="json")

    runtime_context = {
        "policy_content_hash": "a" * 64,
        "stage_contracts": {
            "scope": contract("scope"),
            "literature": contract("literature", ("scope",)),
            "synthesis": contract("synthesis", ("literature",)),
        },
    }
    parent_receipt = await runtime.start(
        start_request(
            mission_policy_id="sci_research",
            runtime_context_json=runtime_context,
        )
    )
    parent = deps["store"].runs[parent_receipt.mission_id]
    parent.snapshot_json["stage_acceptance"] = {stage_id: {"stage_id": stage_id, "result": "pass"} for stage_id in ("scope", "literature", "synthesis")}
    parent.status = MissionStatus.COMPLETED

    child_receipt = await runtime.start(
        start_request(
            parent_mission_id=parent_receipt.mission_id,
            mission_idempotency_key="review-continuation-single",
            mission_policy_id="sci_research",
            runtime_context_json=runtime_context,
            continuation=MissionContinuationDirective(
                reason="needs_more_evidence",
                review_item_ids=("review-literature",),
                reset_stage_ids=("literature",),
                rationale="补充近期证据",
            ),
        )
    )
    child = await deps["store"].get(child_receipt.mission_id)

    assert child is not None
    assert set(child.snapshot_json["stage_acceptance"]) == {"scope"}
    assert child.snapshot_json["mission_lineage"]["invalidated_stage_ids"] == [
        "literature",
        "synthesis",
    ]


@pytest.mark.asyncio
async def test_review_continuation_closes_over_math_question_dependencies(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    runtime_context = {
        "policy_content_hash": "a" * 64,
        **_per_item_runtime_context(),
    }
    parent_receipt = await runtime.start(
        start_request(
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
        )
    )
    parent = deps["store"].runs[parent_receipt.mission_id]
    passed_stage_ids = (
        "problem_understanding",
        "question_1_model",
        "question_1_solution_validation",
        "question_2_model",
        "question_2_solution_validation",
        "question_3_model",
        "question_3_solution_validation",
        "paper_integration",
    )
    parent.snapshot_json["stage_acceptance"] = {stage_id: {"stage_id": stage_id, "result": "pass"} for stage_id in passed_stage_ids}
    parent.snapshot_json["stage_item_counts"] = {"problem_questions": 3}
    parent.status = MissionStatus.COMPLETED

    child_receipt = await runtime.start(
        start_request(
            parent_mission_id=parent_receipt.mission_id,
            mission_idempotency_key="review-continuation-math",
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
            continuation=MissionContinuationDirective(
                reason="regenerate",
                review_item_ids=("review-question-2",),
                reset_stage_ids=("question_2_model",),
            ),
        )
    )
    child = await deps["store"].get(child_receipt.mission_id)

    assert child is not None
    assert set(child.snapshot_json["stage_acceptance"]) == {
        "problem_understanding",
        "question_1_model",
        "question_1_solution_validation",
    }
    assert set(child.snapshot_json["mission_lineage"]["invalidated_stage_ids"]) == {
        "question_2_model",
        "question_2_solution_validation",
        "question_3_model",
        "question_3_solution_validation",
        "paper_integration",
    }
    assert child.snapshot_json["stage_item_counts"] == {"problem_questions": 3}


@pytest.mark.asyncio
async def test_review_continuation_drops_count_when_its_source_stage_is_invalidated(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    runtime_context = {
        "policy_content_hash": "a" * 64,
        **_per_item_runtime_context(),
    }
    parent_receipt = await runtime.start(
        start_request(
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
        )
    )
    parent = deps["store"].runs[parent_receipt.mission_id]
    parent.snapshot_json["stage_acceptance"] = {
        stage_id: {"stage_id": stage_id, "result": "pass"}
        for stage_id in (
            "problem_understanding",
            "question_1_model",
            "question_1_solution_validation",
            "question_2_model",
            "question_2_solution_validation",
            "paper_integration",
        )
    }
    parent.snapshot_json["stage_item_counts"] = {"problem_questions": 2}
    parent.status = MissionStatus.COMPLETED

    child_receipt = await runtime.start(
        start_request(
            parent_mission_id=parent_receipt.mission_id,
            mission_idempotency_key="review-continuation-reset-count-source",
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
            continuation=MissionContinuationDirective(
                reason="regenerate",
                review_item_ids=("review-problem",),
                reset_stage_ids=("problem_understanding",),
            ),
        )
    )
    child = await deps["store"].get(child_receipt.mission_id)

    assert child is not None
    assert "stage_item_counts" not in child.snapshot_json


@pytest.mark.asyncio
async def test_nonterminal_review_feedback_uses_the_continuation_invalidation_closure(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    runtime_context = {
        "policy_content_hash": "a" * 64,
        **_per_item_runtime_context(),
    }
    receipt = await runtime.start(
        start_request(
            workspace_type="math_modeling",
            mission_policy_id="math_modeling_solution",
            runtime_context_json=runtime_context,
        )
    )
    run = deps["store"].runs[receipt.mission_id]
    run.snapshot_json["stage_acceptance"] = {
        stage_id: {"stage_id": stage_id, "result": "pass"}
        for stage_id in (
            "problem_understanding",
            "question_1_model",
            "question_1_solution_validation",
            "question_2_model",
            "question_2_solution_validation",
            "question_3_model",
            "question_3_solution_validation",
            "paper_integration",
        )
    }
    run.snapshot_json["stage_item_counts"] = {"problem_questions": 3}
    await deps["store"].append_command(
        receipt.mission_id,
        MissionUserCommandPayload(
            command_id="review-feedback-1",
            command_type="review_feedback",
            summary="Regenerate question two",
            payload_json={
                "reason": "regenerate",
                "review_item_ids": ["review-question-2"],
                "reset_stage_ids": ["question_2_model"],
            },
        ),
    )

    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    updated = await deps["store"].get(receipt.mission_id)

    assert updated is not None
    assert set(updated.snapshot_json["stage_acceptance"]) == {
        "problem_understanding",
        "question_1_model",
        "question_1_solution_validation",
    }
    assert updated.snapshot_json["stage_item_counts"] == {"problem_questions": 3}
    assert updated.active_stage_id == "question_2_model"


@pytest.mark.asyncio
async def test_continuation_inherits_pinned_inputs_and_accepted_internal_refs(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    runtime_context = {
        "policy_content_hash": "a" * 64,
        **_per_item_runtime_context(),
    }
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
        "problem_understanding": {
            "stage_id": "problem_understanding",
            "result": "pass",
            "artifact_refs": [],
            "evidence_refs": [],
        },
        "question_3_model": {
            "stage_id": "question_3_model",
            "result": "pass",
            "artifact_refs": [candidate_ref],
            "evidence_refs": [first_input_ref],
        },
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
    assert [item["input_ref"] for item in child.snapshot_json["mission_inputs"]] == [first_input_ref, second_input_ref]
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
    assert [item.payload_ref for item in deps["agent"].contexts[-1].reference_items] == [candidate_ref]


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
        heartbeat_interval_seconds=2,
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
            heartbeat_interval_seconds=2,
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
async def test_tool_can_run_with_operation_window_even_when_another_model_call_cannot(
    runtime_factory,
) -> None:
    clock = MutableClock()
    tools = FakeTools()

    async def slow_tool_plan(_context: Any) -> MissionAgentDecision:
        clock.advance(6)
        return tool_decision("tool-after-planning")

    runtime, _deps = runtime_factory(
        agent=ScriptedAgent([slow_tool_plan]),
        tools=tools,
        clock=clock,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=2,
            next_step_reserve_seconds=5,
            tool_start_reserve_seconds=2,
        ),
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome is MissionSliceOutcome.YIELDED
    assert tools.calls == ["tool-after-planning"]


@pytest.mark.asyncio
async def test_subagent_quantum_stays_inside_the_parent_slice_window(
    runtime_factory,
) -> None:
    clock = MutableClock()
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        subagent_operation_time_seconds=60,
        lease_ttl_seconds=20,
        heartbeat_interval_seconds=2,
        max_model_turns=1,
        next_step_reserve_seconds=5,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([subagent_decision("long-worker")]),
        clock=clock,
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome is MissionSliceOutcome.YIELDED
    assert deps["subagents"].calls == ["long-worker"]
    assert deps["subagents"].deadlines == [110.0]


@pytest.mark.asyncio
async def test_subagent_quantum_yield_preserves_inflight_operation_across_delivery(
    runtime_factory,
) -> None:
    class QuantumSubagents:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, request: Any) -> MissionPortOutcome:
            self.calls += 1
            if self.calls == 1:
                return MissionPortOutcome(
                    status=MissionPortOutcomeStatus.YIELDED,
                    summary="One durable worker action completed",
                    payload_json={
                        "pending_job_ids": ["sj-1"],
                        "pending_reasons": {"sj-1": "capacity_saturated"},
                    },
                )
            return MissionPortOutcome(
                status=MissionPortOutcomeStatus.COMPLETED,
                summary="Worker synthesis completed",
                payload_json={"jobs": [{"job_id": "sj-1"}]},
            )

        async def adopt_terminal(self, request: Any) -> MissionPortOutcome | None:
            return None

    subagents = QuantumSubagents()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [subagent_decision("quantized-worker"), complete_decision()]
        ),
        subagents=subagents,
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    checkpointed = await deps["store"].get(receipt.mission_id)
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    completed = await deps["store"].get(receipt.mission_id)

    assert first.outcome is MissionSliceOutcome.YIELDED
    assert first.reason == "subagent_quantum_yielded"
    assert checkpointed is not None
    inflight = checkpointed.snapshot_json["inflight_operation"]
    assert inflight["operation_id"] == "quantized-worker"
    assert inflight["quantum_count"] == 1
    assert checkpointed.active_subagent_count == 1
    assert checkpointed.snapshot_json["inflight_operation"]["pending_reasons"] == {
        "sj-1": "capacity_saturated"
    }
    assert deps["wakeups"].delays[-1] == 5
    assert second.outcome is MissionSliceOutcome.COMPLETED
    assert completed is not None and completed.active_subagent_count == 0
    assert "inflight_operation" not in completed.snapshot_json
    assert subagents.calls == 2


@pytest.mark.asyncio
async def test_tool_with_a_long_pinned_budget_is_deferred_to_a_fresh_slice(
    runtime_factory,
) -> None:
    clock = MutableClock()
    tools = FakeTools()
    tools.required_budgets["native_web_search"] = 7

    async def slow_tool_plan(_context: Any) -> MissionAgentDecision:
        clock.advance(4)
        return tool_decision("long-tool")

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([slow_tool_plan, complete_decision()]),
        tools=tools,
        clock=clock,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=2,
            next_step_reserve_seconds=5,
            tool_start_reserve_seconds=2,
        ),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert first.outcome is MissionSliceOutcome.YIELDED
    assert tools.calls == []
    run = await deps["store"].get(receipt.mission_id)
    assert run is not None
    assert run.snapshot_json["inflight_operation"]["operation_id"] == "long-tool"
    started = next(
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.operation_id == "long-tool" and item.phase.value == "started"
    )
    assert started.payload_json["required_budget_seconds"] == 7

    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert second.outcome is MissionSliceOutcome.COMPLETED
    assert tools.calls == ["long-tool"]


def test_slice_limits_reject_an_unusable_shutdown_window() -> None:
    with pytest.raises(
        ValueError,
        match="shutdown_margin_seconds must be smaller than wall_time_seconds",
    ):
        MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=10,
            lease_ttl_seconds=30,
        )


@pytest.mark.asyncio
async def test_stale_worker_cannot_write_after_lease_takeover(runtime_factory) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    limits = MissionSliceLimits(
        wall_time_seconds=2,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=6,
        heartbeat_interval_seconds=1,
        max_model_turns=2,
        max_tool_steps=2,
    )

    async def takeover(_context: Any) -> MissionAgentDecision:
        clock.advance(7)
        current = await store.get(receipt.mission_id)
        assert current is not None
        dispatched = await store.claim_dispatch(
            receipt.mission_id,
            MissionDispatchClaimPayload(
                worker_id="takeover-dispatcher",
                expected_state_version=current.state_version,
                ttl_seconds=6,
            ),
        )
        await store.claim_lease(
            receipt.mission_id,
            MissionLeaseClaimPayload(
                worker_id="worker-new",
                dispatch_owner="takeover-dispatcher",
                dispatch_epoch=dispatched.dispatch_epoch,
                expected_state_version=dispatched.state_version,
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
async def test_long_model_call_is_cancelled_when_heartbeat_observes_lease_takeover(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    started = asyncio.Event()
    cancelled = asyncio.Event()
    heartbeat_attempted = asyncio.Event()

    async def takeover_during_heartbeat(mission_id: str, command: Any):
        del command
        current = store.runs[mission_id]
        current.lease_owner = "worker-new"
        current.lease_epoch += 1
        current.lease_expires_at = clock.now() + timedelta(seconds=20)
        heartbeat_attempted.set()
        raise DataServiceClientError("lease changed", status_code=409)

    store.heartbeat_lease = takeover_during_heartbeat  # type: ignore[method-assign]

    async def wait_for_takeover(_context: Any) -> MissionAgentDecision:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([wait_for_takeover]),
        clock=clock,
        store=store,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            heartbeat_interval_seconds=0.01,
            lease_ttl_seconds=20,
        ),
    )
    receipt = await runtime.start(start_request())
    slice_task = asyncio.create_task(
        runtime.run_slice(receipt.mission_id, worker_id="worker-old")
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    telemetry = await asyncio.wait_for(slice_task, timeout=1)
    await asyncio.wait_for(heartbeat_attempted.wait(), timeout=1)
    await asyncio.wait_for(cancelled.wait(), timeout=1)

    assert telemetry.outcome is MissionSliceOutcome.YIELDED
    assert telemetry.reason == "lease_fence_lost"
    assert deps["agent"].provider_calls == 1
    starts = [
        item
        for item in store.items[receipt.mission_id]
        if item.item_type == "model_call_started"
    ]
    assert len(starts) == 1
    assert not any(
        item.item_type in {"usage_receipt", "model_call_terminal"}
        for item in store.items[receipt.mission_id]
    )


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
    assert heartbeat_calls == 0


@pytest.mark.asyncio
async def test_long_operation_emits_durable_heartbeats_while_waiting(
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

    async def slow_completion(_context: Any) -> MissionAgentDecision:
        await asyncio.sleep(0.035)
        return complete_decision()

    runtime, _deps = runtime_factory(
        agent=ScriptedAgent([slow_completion]),
        clock=clock,
        store=store,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            heartbeat_interval_seconds=0.01,
            lease_ttl_seconds=20,
            max_model_turns=1,
            max_tool_steps=2,
        ),
    )
    receipt = await runtime.start(start_request())

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert telemetry.outcome == MissionSliceOutcome.COMPLETED
    assert heartbeat_calls >= 2


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
        heartbeat_interval_seconds=2,
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
async def test_stale_dispatch_generation_cannot_acquire_the_mission_lease(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    first_delivery = deps["wakeups"].deliveries[0]

    deps["clock"].advance(MISSION_DISPATCH_TTL_SECONDS + 1)
    reconciler = MissionReconciler(
        store=deps["store"],
        wakeups=deps["wakeups"],
        events=deps["events"],
        clock=deps["clock"],
    )
    assert await reconciler.reconcile_once(worker_id="reconciler-new") == [
        receipt.mission_id
    ]
    latest_delivery = deps["wakeups"].deliveries[-1]

    stale = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-stale",
        dispatch_owner=first_delivery[1],
        dispatch_epoch=first_delivery[2],
    )
    current = await deps["store"].get(receipt.mission_id)

    assert stale.outcome is MissionSliceOutcome.YIELDED
    assert stale.reason == "stale_delivery"
    assert current is not None and current.lease_owner is None

    accepted = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-current",
        dispatch_owner=latest_delivery[1],
        dispatch_epoch=latest_delivery[2],
    )
    assert accepted.outcome is MissionSliceOutcome.COMPLETED


@pytest.mark.asyncio
async def test_waiting_delivery_is_consumed_without_holding_the_dispatch_slot(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request())
    delivery = deps["wakeups"].deliveries[0]
    deps["store"].runs[receipt.mission_id].status = MissionStatus.WAITING

    result = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-waiting",
        dispatch_owner=delivery[1],
        dispatch_epoch=delivery[2],
    )
    waiting = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.WAITING
    assert result.reason == "mission_waiting_for_input"
    assert waiting is not None and waiting.dispatch_owner is None


@pytest.mark.asyncio
async def test_workspace_dispatch_turn_hands_off_to_the_older_waiting_mission(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    first = await runtime.start(
        start_request(
            mission_idempotency_key="workspace-slot-first",
            thread_id="workspace-slot-thread-first",
        )
    )
    deps["clock"].advance(1)
    second = await runtime.start(
        start_request(
            mission_idempotency_key="workspace-slot-second",
            thread_id="workspace-slot-thread-second",
        )
    )
    assert first.wakeup_published is True
    assert second.wakeup_published is False
    assert len(deps["wakeups"].deliveries) == 1
    first_delivery = deps["wakeups"].deliveries[0]
    first_run = await deps["store"].get(first.mission_id)
    assert first_run is not None
    first_claimed = await deps["store"].claim_lease(
        first.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-first",
            dispatch_owner=first_delivery[1],
            dispatch_epoch=first_delivery[2],
            expected_state_version=first_run.state_version,
            ttl_seconds=240,
        ),
    )

    deps["clock"].advance(1)
    await deps["store"].release_lease(
        first.mission_id,
        MissionLeaseReleasePayload(
            worker_id="worker-first",
            lease_epoch=first_claimed.lease_epoch,
            expected_state_version=first_claimed.state_version,
            next_wakeup_at=deps["clock"].now(),
        ),
    )
    assert await runtime.notify_runnable(first.mission_id) is False
    reconciler = MissionReconciler(
        store=deps["store"],
        wakeups=deps["wakeups"],
        events=deps["events"],
        clock=deps["clock"],
    )

    assert await reconciler.reconcile_once(worker_id="reconciler-slot") == [
        second.mission_id
    ]


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
            MissionUserCommandPayload(
                command_id="steer-1",
                command_type="correction",
                summary="Focus on Non-IID evaluation",
                payload_json={"constraint": "Non-IID"},
            ),
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
    items = store.items[receipt.mission_id]
    usage_receipts = [
        item
        for item in items
        if item.item_type == "usage_receipt"
        and item.producer == "workspace_agent"
    ]
    starts = [
        item
        for item in items
        if item.item_type == "model_call_started"
        and item.producer == "workspace_agent"
    ]
    assert len(usage_receipts) == len(starts) == 2
    assert [item.operation_id for item in usage_receipts] == [
        item.operation_id for item in starts
    ]
    applied = next(
        item
        for item in items
        if item.item_type == "status_update" and item.operation_id == "steer-1"
    )
    assert usage_receipts[0].seq < applied.seq


@pytest.mark.asyncio
async def test_invalid_prism_command_is_consumed_without_poisoning_mission(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    await deps["store"].append_command(
        receipt.mission_id,
        MissionUserCommandPayload(
            command_id="invalid-prism-command",
            command_type="steer",
            summary="Use this selection",
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
        ),
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)
    command_item = next(
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.operation_id == "invalid-prism-command"
        and item.item_type == "status_update"
    )

    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert run is not None
    assert run.last_applied_command_seq == run.last_command_seq
    assert "prism_context_ref" not in run.snapshot_json
    assert command_item.phase.value == "failed"
    assert command_item.payload_json["error_code"] == "invalid_prism_context"


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
    applied = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    replay = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert cancelled.status.value == "planning"
    assert applied.outcome == MissionSliceOutcome.TERMINAL
    assert applied.reason == "durable_command_applied"
    assert replay.outcome == MissionSliceOutcome.TERMINAL
    assert replay.reason == "mission_already_terminal"
    assert agent.contexts == []


@pytest.mark.asyncio
async def test_cancel_after_more_than_one_command_page_is_not_stranded(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    for index in range(120):
        await deps["store"].append_command(
            receipt.mission_id,
            MissionUserCommandPayload(
                command_id=f"steer-{index}",
                command_type="correction",
                summary=f"correction {index}",
                payload_json={"index": index},
            ),
        )
    await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-after-many-commands",
        reason="Stop after queued corrections",
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.CANCELLED
    assert run.last_applied_command_seq == run.last_command_seq
    assert deps["agent"].contexts == []


@pytest.mark.asyncio
async def test_pause_on_early_command_page_does_not_hide_later_cancel(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    await deps["store"].append_command(
        receipt.mission_id,
        MissionUserCommandPayload(
            command_id="pause-before-more-commands",
            command_type="pause",
            summary="Pause before the remaining queued commands",
        ),
    )
    for index in range(100):
        await deps["store"].append_command(
            receipt.mission_id,
            MissionUserCommandPayload(
                command_id=f"queued-correction-{index}",
                command_type="correction",
                summary=f"queued correction {index}",
                payload_json={"index": index},
            ),
        )
    await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-after-early-pause",
        reason="Cancel supersedes the earlier pause",
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.CANCELLED
    assert run.last_applied_command_seq == run.last_command_seq
    assert "pending_command_control" not in run.snapshot_json
    assert deps["agent"].contexts == []


@pytest.mark.asyncio
async def test_cancel_on_early_command_page_consumes_remaining_commands(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-before-more-commands",
        reason="Cancel before the remaining queued commands",
    )
    for index in range(100):
        await deps["store"].append_command(
            receipt.mission_id,
            MissionUserCommandPayload(
                command_id=f"post-cancel-correction-{index}",
                command_type="correction",
                summary=f"post-cancel correction {index}",
                payload_json={"index": index},
            ),
        )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.CANCELLED
    assert run.last_applied_command_seq == run.last_command_seq
    assert "pending_command_control" not in run.snapshot_json
    assert deps["agent"].contexts == []


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
    assert result.reason == "durable_command_applied"
    assert run is not None and run.status.value == "cancelled"
    assert tools.calls == []


@pytest.mark.asyncio
async def test_cancel_closes_recovered_inflight_operation_lifecycle(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    tools = FakeTools()
    tools.crash_once.add("cancel-after-crash")
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("cancel-after-crash")]),
        clock=clock,
        store=store,
        tools=tools,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=2,
            max_model_turns=4,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(start_request())

    with pytest.raises(SimulatedWorkerCrash):
        await runtime.run_slice(receipt.mission_id, worker_id="worker-crashed")
    await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-recovered-operation",
        reason="Stop the recovered operation",
    )
    clock.advance(21)

    result = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-cancel-recovery",
    )
    run = await deps["store"].get(receipt.mission_id)
    operation_items = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.operation_id == "cancel-after-crash"
    ]

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.CANCELLED
    assert "inflight_operation" not in run.snapshot_json
    assert [item.item_type for item in operation_items] == [
        "tool_call",
        "tool_result",
    ]
    assert operation_items[-1].phase is MissionItemPhase.CANCELLED
    assert operation_items[-1].payload_json["error_code"] == "cancelled_by_user"


@pytest.mark.asyncio
async def test_cancel_does_not_duplicate_existing_inflight_terminal(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    tools = FakeTools()
    tools.crash_once.add("terminal-before-cancel")
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("terminal-before-cancel")]),
        clock=clock,
        store=store,
        tools=tools,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=2,
            max_model_turns=4,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(start_request())

    with pytest.raises(SimulatedWorkerCrash):
        await runtime.run_slice(receipt.mission_id, worker_id="worker-crashed")
    deps["store"].seed_items(
        receipt.mission_id,
        [
            MissionItemDraftPayload(
                item_type="tool_result",
                operation_id="terminal-before-cancel",
                phase=MissionItemPhase.COMPLETED,
                producer="tool_orchestrator",
                summary="Tool already completed before cancellation was applied",
            )
        ],
    )
    await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-after-existing-terminal",
        reason="Stop the mission",
    )
    clock.advance(21)

    result = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-cancel-recovery",
    )
    operation_items = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.operation_id == "terminal-before-cancel"
    ]

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert [item.item_type for item in operation_items] == [
        "tool_call",
        "tool_result",
    ]
    assert operation_items[-1].phase is MissionItemPhase.COMPLETED


@pytest.mark.asyncio
async def test_cancel_closes_parent_batch_when_only_one_subagent_is_terminal(
    runtime_factory,
) -> None:
    class CrashingSubagents:
        async def run(self, request: Any) -> MissionPortOutcome:
            del request
            raise SimulatedWorkerCrash()

        async def adopt_terminal(self, request: Any) -> MissionPortOutcome | None:
            del request
            return None

    clock = MutableClock()
    store = FakeMissionStore(clock)
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([subagent_decision("partially-terminal-batch")]),
        clock=clock,
        store=store,
        subagents=CrashingSubagents(),
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=2,
            max_model_turns=4,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(start_request())

    with pytest.raises(SimulatedWorkerCrash):
        await runtime.run_slice(receipt.mission_id, worker_id="worker-crashed")
    deps["store"].seed_items(
        receipt.mission_id,
        [
            MissionItemDraftPayload(
                item_type="subagent_progress",
                operation_id="partially-terminal-batch",
                phase=MissionItemPhase.COMPLETED,
                producer="finished-member",
                summary="One member completed before the parent was cancelled",
                payload_json={
                    "job_id": "finished-member",
                    "lifecycle_phase": "terminal",
                },
            )
        ],
    )
    await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-partial-subagent-batch",
        reason="Stop the remaining members",
    )
    clock.advance(21)

    result = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-cancel-recovery",
    )
    operation_items = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.operation_id == "partially-terminal-batch"
    ]

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert [item.item_type for item in operation_items] == [
        "subagent_spawned",
        "subagent_progress",
        "subagent_completed",
    ]
    assert operation_items[-1].phase is MissionItemPhase.CANCELLED


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
        heartbeat_interval_seconds=2,
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
            heartbeat_interval_seconds=2,
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
async def test_terminal_operation_after_first_100_items_is_reused(
    runtime_factory,
) -> None:
    operation_id = "operation-terminal-after-first-page"
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [tool_decision(operation_id), complete_decision()]
        )
    )
    receipt = await runtime.start(start_request())
    deps["store"].seed_items(
        receipt.mission_id,
        [
            MissionItemDraftPayload(
                item_type="tool_progress",
                operation_id=operation_id,
                phase="progress",
                producer="tool_orchestrator",
                summary=f"progress {index}",
            )
            for index in range(100)
        ]
        + [
            MissionItemDraftPayload(
                item_type="tool_result",
                operation_id=operation_id,
                phase="completed",
                producer="tool_orchestrator",
                summary="Durable terminal tool result",
            )
        ],
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert deps["tools"].calls == []
    assert any(
        item.item_type == "status_update"
        and item.operation_id == operation_id
        and item.summary == "Previously completed operation reused"
        for item in deps["store"].items[receipt.mission_id]
    )


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
        heartbeat_interval_seconds=2,
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
async def test_parent_adopts_subagent_terminal_on_final_probe_before_failure(
    runtime_factory,
) -> None:
    class LostTerminalAckSubagents:
        def __init__(self) -> None:
            self.run_calls = 0
            self.adopt_calls = 0

        async def run(self, request):
            self.run_calls += 1
            raise RuntimeError(f"terminal ACK lost for {request.operation_id}")

        async def adopt_terminal(self, request):
            self.adopt_calls += 1
            if self.adopt_calls == 1:
                return None
            return MissionPortOutcome(
                status=MissionPortOutcomeStatus.COMPLETED,
                summary="durable subagent terminal adopted",
                payload_json={"result_ref": request.operation_id},
            )

    subagents = LostTerminalAckSubagents()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [subagent_decision("subagent-lost-ack"), complete_decision()]
        ),
        subagents=subagents,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)
    completed = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "subagent_completed"
    ]

    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert run is not None and run.status is MissionStatus.COMPLETED
    assert run.active_subagent_count == 0
    assert "inflight_operation" not in run.snapshot_json
    assert subagents.run_calls == 1
    assert subagents.adopt_calls == 2
    assert len(completed) == 1
    assert completed[0].phase.value == "completed"
    assert completed[0].summary == "durable subagent terminal adopted"


@pytest.mark.asyncio
async def test_inflight_tool_recovers_before_next_model_call_budget_check(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    tools = FakeTools()
    tools.crash_once.add("search-before-budget-stop")
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-before-budget-stop")]),
        clock=clock,
        store=store,
        tools=tools,
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            heartbeat_interval_seconds=2,
            max_model_turns=4,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 1,
                        "max_tool_operations": 2,
                        "max_subagent_jobs": 1,
                        "stop_after_total_tokens": 10_000,
                    }
                }
            }
        )
    )

    with pytest.raises(SimulatedWorkerCrash):
        await runtime.run_slice(receipt.mission_id, worker_id="worker-crashed")
    clock.advance(21)

    recovered = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-recovery",
    )

    run = await deps["store"].get(receipt.mission_id)
    assert recovered.outcome is MissionSliceOutcome.TERMINAL
    assert recovered.reason == "resource_budget_exhausted"
    assert run is not None and run.status is MissionStatus.FAILED
    assert tools.calls == [
        "search-before-budget-stop",
        "search-before-budget-stop",
    ]
    assert len(deps["agent"].contexts) == 1
    assert any(
        item.item_type == "tool_result"
        and item.operation_id == "search-before-budget-stop"
        and item.phase.value == "completed"
        for item in deps["store"].items[receipt.mission_id]
    )


@pytest.mark.asyncio
async def test_billing_admission_creates_durable_waiting_mission(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    deps["store"].admission_status = MissionStatus.WAITING
    receipt = await runtime.start(start_request())

    run = await deps["store"].get(receipt.mission_id)

    assert receipt.status == "waiting"
    assert receipt.wakeup_published is False
    assert run is not None and run.status.value == "waiting"
    assert run.snapshot_json["waiting_reason"] == "budget"
    assert run.snapshot_json["pending_request"]["request_type"] == "budget_confirmation"
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
            assert any(item.item_type == "resume_input" and item.operation_id == "permission-1" for item in request.recent_items)
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
    assert runtime_request_id == "permission-1"
    assert pending_request["summary"] == "Confirm external source access"
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
    pause_items = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "pause_request"]
    terminal_update = next(item for item in reversed(deps["store"].items[receipt.mission_id]) if item.item_type == "status_update")

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert completed.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.pending_review_count == 1
    assert review_items[0].status.value == "pending"
    assert pause_items == []
    assert terminal_update.producer == "mission_runtime"
    assert terminal_update.payload_json == {"review_pending": True}


@pytest.mark.asyncio
async def test_model_timeout_with_unknown_usage_fails_closed(runtime_factory) -> None:
    def timeout(_context):
        raise TimeoutError("provider read timed out")

    runtime, deps = runtime_factory(agent=ScriptedAgent([timeout]))
    receipt = await runtime.start(start_request())
    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert result.reason == "model_usage_reconciliation_required"
    assert run is not None and run.status is MissionStatus.FAILED
    assert run.snapshot_json["failure_reason"] == (
        "model_usage_reconciliation_required"
    )
    terminals = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "model_call_terminal"
    ]
    assert len(terminals) == 1
    assert terminals[0].payload_json["outcome"] == "unresolved"
    assert not any(
        item.item_type == "usage_receipt"
        for item in deps["store"].items[receipt.mission_id]
    )


@pytest.mark.asyncio
async def test_recovery_closes_orphaned_model_start_before_next_provider_call(
    runtime_factory,
) -> None:
    agent = ScriptedAgent([complete_decision()])
    runtime, deps = runtime_factory(agent=agent)
    receipt = await runtime.start(start_request())
    model_call_id = "model-call:workspace:orphaned-after-crash"
    deps["store"].seed_items(
        receipt.mission_id,
        [
            MissionItemDraftPayload(
                item_type="model_call_started",
                operation_id=model_call_id,
                phase="started",
                producer="workspace_agent",
                summary="Workspace Agent model call started",
                payload_json={
                    "model_call_id": model_call_id,
                    "model_id": "gpt-5.6-sol",
                    "turn": 1,
                    "attempt": 1,
                },
            )
        ],
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)
    states = await deps["store"].list_model_call_states(receipt.mission_id)

    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert result.reason == "model_usage_reconciliation_required"
    assert agent.provider_calls == 0
    assert run is not None and run.status is MissionStatus.FAILED
    assert len(states) == 1
    assert states[0].state.value == "unresolved"
    assert states[0].terminal is not None
    assert states[0].terminal.payload_json["error_type"] == (
        "ModelCallRecoveryUnresolved"
    )


@pytest.mark.asyncio
async def test_successful_decision_clears_recovered_transient_error(runtime_factory) -> None:
    class PreflightTimeout(TimeoutError):
        usage_not_incurred = True

    def timeout(_context):
        raise PreflightTimeout("provider request was not sent")

    runtime, deps = runtime_factory(agent=ScriptedAgent([timeout, complete_decision()]))
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    assert first.continuation_published is True
    assert deps["wakeups"].delays[-1] == 5
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
            heartbeat_interval_seconds=2,
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
    deps["clock"].advance(5)
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
async def test_repeated_quality_exceptions_share_the_stage_failure_guard(
    runtime_factory,
) -> None:
    class BrokenQuality(FakeQuality):
        async def evaluate(self, request):
            self.calls.append(request.operation_id)
            raise RuntimeError("quality provider unavailable")

    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [quality_decision("broken-quality-1"), quality_decision("broken-quality-2")]
        ),
        quality=BrokenQuality(),
        limits=MissionSliceLimits(
            max_model_turns=1,
            max_operation_failures_per_stage=2,
        ),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)

    assert first.outcome is MissionSliceOutcome.YIELDED
    assert second.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.FAILED
    assert run.snapshot_json["operation_failure_guard"][
        "question_1_solution_validation"
    ]["failure_count"] == 2


@pytest.mark.asyncio
async def test_repeated_review_exceptions_share_the_stage_failure_guard(
    runtime_factory,
) -> None:
    class BrokenReview:
        async def build_candidates(self, request):
            del request
            raise RuntimeError("review renderer unavailable")

    decisions = [
        MissionAgentDecision(
            decision_id=f"decision-review-failure-{index}",
            kind="review",
            operation_id=f"review-failure-{index}",
            stage_id="stage-1",
            summary="Build review candidates",
        )
        for index in range(2)
    ]
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(decisions),
        review=BrokenReview(),
        limits=MissionSliceLimits(
            max_model_turns=1,
            max_operation_failures_per_stage=2,
        ),
    )
    receipt = await runtime.start(start_request())
    persisted = deps["store"].runs[receipt.mission_id]
    persisted.active_stage_id = "stage-1"
    persisted.snapshot_json["stage_acceptance"] = {
        "stage-1": {
            "result": "pass",
            "artifact_refs": ["artifact-candidate:" + "a" * 64],
        }
    }

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await deps["store"].get(receipt.mission_id)

    assert first.outcome is MissionSliceOutcome.YIELDED
    assert second.outcome is MissionSliceOutcome.TERMINAL
    assert run is not None and run.status is MissionStatus.FAILED
    assert run.snapshot_json["operation_failure_guard"]["stage-1"][
        "failure_count"
    ] == 2


@pytest.mark.asyncio
async def test_repeated_transient_model_timeouts_stop_instead_of_retrying_forever(
    runtime_factory,
) -> None:
    class PreflightTimeout(TimeoutError):
        usage_not_incurred = True

    def timeout(_context):
        raise PreflightTimeout("provider request was not sent")

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([timeout, timeout]),
        limits=MissionSliceLimits(max_transient_failures=2),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    deps["clock"].advance(5)
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
        usage_not_incurred = True

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
            heartbeat_interval_seconds=2,
            max_model_turns=2,
        ),
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome is MissionSliceOutcome.COMPLETED
    assert result.model_turns == 2
    assert not any(item.item_type == "error" for item in deps["store"].items[receipt.mission_id])
    items = deps["store"].items[receipt.mission_id]
    starts = [item for item in items if item.item_type == "model_call_started"]
    usage = [item for item in items if item.item_type == "usage_receipt"]
    assert len(starts) == len(usage) == 2
    assert [item.operation_id for item in usage] == [
        item.operation_id for item in starts
    ]


@pytest.mark.asyncio
async def test_agent_protocol_feedback_survives_a_bounded_slice(
    runtime_factory,
) -> None:
    def malformed(_context):
        raise MissionAgentProtocolError("mission_step fields were invalid")

    def repaired(context):
        assert context.protocol_feedback == "mission_step fields were invalid"
        return complete_decision()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([malformed, repaired]),
        limits=MissionSliceLimits(max_model_turns=1),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    after_first = await deps["store"].get(receipt.mission_id)
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    completed = await deps["store"].get(receipt.mission_id)

    assert first.outcome is MissionSliceOutcome.YIELDED
    assert after_first is not None
    assert after_first.snapshot_json["protocol_repair"] == {
        "attempt": 1,
        "feedback": "mission_step fields were invalid",
    }
    assert second.outcome is MissionSliceOutcome.COMPLETED
    assert completed is not None
    assert "protocol_repair" not in completed.snapshot_json


@pytest.mark.asyncio
@pytest.mark.parametrize("zero_usage", [False, True])
async def test_successful_agent_response_without_measured_usage_fails_closed(
    runtime_factory,
    zero_usage: bool,
) -> None:
    class UnmeteredAgent:
        async def decide(self, context):
            decision = complete_decision("unmetered-complete")
            if not zero_usage:
                return decision
            return decision.model_copy(
                update={
                    "usage_receipt": ModelUsageReceipt(
                        model_id=context.mission.model_id,
                        provider_response_id="zero-usage-response",
                        usage=ModelUsage(),
                    )
                }
            )

    runtime, deps = runtime_factory(agent=UnmeteredAgent())
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert result.outcome is MissionSliceOutcome.TERMINAL
    assert result.reason == "model_usage_reconciliation_required"
    assert run is not None and run.status is MissionStatus.FAILED
    assert run.snapshot_json["failure_reason"] == (
        "model_usage_reconciliation_required"
    )
    assert not any(
        item.item_type == "usage_receipt"
        for item in deps["store"].items[receipt.mission_id]
    )
    terminals = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "model_call_terminal"
    ]
    assert len(terminals) == 1
    assert terminals[0].payload_json["outcome"] == "unresolved"


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
            heartbeat_interval_seconds=2,
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

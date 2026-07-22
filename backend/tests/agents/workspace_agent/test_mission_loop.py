from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage

from src.agents.workspace_agent.mission_loop import (
    WorkspaceMissionLoopAgent,
    _agent_item_projection,
    _agent_mission_projection,
    _hydrated_reference_reads,
    _mission_input_inventory,
    _quality_reference_inventory,
    _render_mission_state,
    _subagent_selectable_refs,
    _unique_reference_items,
    _validate_decision_context,
    _validate_decision_scope,
    mission_decision_tool,
    parse_mission_decision,
)
from src.agents.workspace_agent.prompts.mission import render_workspace_mission_prompt
from src.contracts.reasoning import ReasoningEffort
from src.contracts.review_policy import ReviewMode
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    StageCriterion,
    StageInstantiationRule,
)
from src.dataservice_client.contracts.mission import (
    MissionItemPayload,
    MissionItemPhase,
    MissionRunPayload,
    MissionStatus,
)
from src.mission_runtime.contracts import (
    MissionAgentDecision,
    MissionAgentProtocolError,
    MissionAgentUsageError,
    MissionDecisionKind,
    MissionLoopContext,
)


def _mission_payload() -> MissionRunPayload:
    now = datetime.now(UTC)
    return MissionRunPayload(
        mission_id="mission-1",
        parent_mission_id=None,
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
        workspace_type="math_modeling",
        mission_policy_id="math_modeling_solution",
        title="Solve question one",
        objective="Validate question one in the sandbox.",
        status=MissionStatus.RUNNING,
        review_mode=ReviewMode.REVIEW_ALL,
        active_stage_id="question_1_solution_validation",
        model_id="gpt-5.6-luna",
        reasoning_effort=ReasoningEffort.XHIGH,
        snapshot_json={"stage_status": {"question_1_model": "passed"}},
        runtime_context_json={"mission_policy_snapshot": {"large": "contract"}},
        context_checkpoint_ref="checkpoint://one",
        pending_review_count=0,
        evidence_count=2,
        artifact_count=1,
        active_subagent_count=0,
        mission_idempotency_key="mission-key",
        last_command_seq=1,
        last_applied_command_seq=1,
        next_wakeup_at=now,
        lease_owner="worker-1",
        lease_epoch=4,
        lease_expires_at=now,
        dispatch_owner="dispatcher-1",
        dispatch_epoch=3,
        dispatch_expires_at=now,
        state_version=12,
        last_item_seq=9,
        created_at=now,
        updated_at=now,
        started_at=now,
    )


def _mission_item(*, seq: int, item_type: str, payload: dict[str, object]) -> MissionItemPayload:
    return MissionItemPayload(
        id=f"item-{seq}",
        mission_id="mission-1",
        seq=seq,
        item_type=item_type,
        operation_id="read-model",
        phase=MissionItemPhase.COMPLETED,
        stage_id="question_1_solution_validation",
        producer="workspace_agent",
        summary=f"{item_type} summary",
        payload_json=payload,
        payload_ref="prism-file:model-spec",
        created_at=datetime.now(UTC),
    )


def test_mission_loop_never_parses_prose_or_multiple_frames() -> None:
    with pytest.raises(MissionAgentProtocolError, match="exactly one"):
        parse_mission_decision(AIMessage(content='{"kind":"complete"}'))

    with pytest.raises(MissionAgentProtocolError, match="exactly one"):
        parse_mission_decision(
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "mission_step", "args": {}, "id": "one"},
                    {"name": "mission_step", "args": {}, "id": "two"},
                ],
            )
        )


def test_mission_loop_rejects_malformed_provider_arguments() -> None:
    with pytest.raises(MissionAgentProtocolError, match="schema"):
        parse_mission_decision(
            AIMessage(
                content="ignored provider prose",
                tool_calls=[
                    {
                        "name": "mission_step",
                        "args": {"kind": "complete"},
                        "id": "bad-frame",
                    }
                ],
            )
        )


def _provider_response_context() -> MissionLoopContext:
    mission = _mission_payload().model_copy(
        update={
            "runtime_context_json": {
                "mission_policy_snapshot": {"id": "math_modeling_solution"},
                "stage_contracts": {
                    "question_1_solution_validation": {
                        "stage_id": "question_1_solution_validation"
                    }
                },
                "tool_policy": {"allowed_tool_ids": []},
                "worker_skill_snapshots": {},
            }
        }
    )
    return MissionLoopContext(
        mission=mission,
        model_turns_used=0,
        tool_steps_used=0,
        deadline_monotonic=100.0,
    )


class _ProviderResponseModel:
    def __init__(self, response: AIMessage) -> None:
        self.response = response

    def bind_tools(self, *args, **kwargs):
        del args, kwargs
        return self

    async def ainvoke(self, messages):
        del messages
        return self.response


@pytest.mark.asyncio
async def test_workspace_agent_protocol_error_carries_response_usage() -> None:
    response = AIMessage(
        content="malformed",
        id="mission-response-1",
        usage_metadata={
            "input_tokens": 40,
            "output_tokens": 5,
            "total_tokens": 45,
        },
    )
    agent = WorkspaceMissionLoopAgent(
        model_factory=lambda *args, **kwargs: _ProviderResponseModel(response)
    )

    with pytest.raises(MissionAgentProtocolError) as raised:
        await agent.decide(_provider_response_context())

    assert raised.value.usage_receipt is not None
    assert raised.value.usage_receipt.provider_response_id == "mission-response-1"
    assert raised.value.usage_receipt.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_workspace_agent_response_without_usage_fails_before_parsing() -> None:
    response = AIMessage(content="malformed", id="mission-response-unmetered")
    agent = WorkspaceMissionLoopAgent(
        model_factory=lambda *args, **kwargs: _ProviderResponseModel(response)
    )

    with pytest.raises(MissionAgentUsageError, match="non-zero usage"):
        await agent.decide(_provider_response_context())


def test_mission_loop_reports_the_invalid_encoded_field() -> None:
    arguments = {
        "decision_id": "tool-1",
        "kind": "tool",
        "summary": "Run the computation",
        "operation_id": "op-tool-1",
        "stage_id": "question_1_solution_validation",
        "risk_level": "low",
        "plan_json": "{}",
        "tool_name": "sandbox.run_python",
        "tool_arguments_json": "{invalid",
        "subagent_jobs": [],
        "quality_candidate_refs": [],
        "quality_criteria": [],
        "quality_evidence": [],
        "quality_exemplar_comparisons": [],
        "quality_item_counts": [],
        "quality_blocking_user_inputs": [],
        "review_summary": None,
        "review_items": [],
        "failure_reason": None,
        "pause_request": None,
    }

    with pytest.raises(
        MissionAgentProtocolError,
        match="tool_arguments_json must contain valid JSON",
    ):
        parse_mission_decision(
            AIMessage(
                content="",
                tool_calls=[{"name": "mission_step", "args": arguments, "id": "bad-json"}],
            )
        )


def test_mission_loop_decodes_provider_json_object_fields() -> None:
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mission_step",
                    "args": {
                        "decision_id": "plan-1",
                        "kind": "continue",
                        "summary": "Plan the first stage",
                        "operation_id": None,
                        "stage_id": "materials_inventory",
                        "risk_level": None,
                        "plan_json": '{"next":"inspect materials"}',
                        "tool_name": None,
                        "tool_arguments_json": "{}",
                        "subagent_jobs": [],
                        "quality_candidate_refs": [],
                        "quality_criteria": [],
                        "quality_blocking_user_inputs": [],
                        "review_summary": None,
                        "review_items": [],
                        "failure_reason": None,
                        "pause_request": None,
                    },
                    "id": "frame-1",
                }
            ],
        )
    )

    assert decision.payload_json == {"next": "inspect materials"}
    assert decision.snapshot_patch == {}


def test_mission_loop_provider_schema_is_strict_recursively() -> None:
    schema = mission_decision_tool()["function"]["parameters"]

    def assert_strict_objects(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            assert "default" not in node
            assert "uniqueItems" not in node
            for value in node.values():
                assert_strict_objects(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict_objects(value)

    assert_strict_objects(schema)


def test_mission_loop_provider_schema_pins_authoritative_quality_refs() -> None:
    candidate_ref = "artifact-candidate:" + "a" * 64
    evidence_ref = "sandbox-artifact:" + "b" * 64

    schema = mission_decision_tool(
        quality_candidate_refs=(candidate_ref,),
        quality_evidence_refs=(evidence_ref,),
        quality_item_count_sources=("problem_questions",),
    )["function"]["parameters"]

    assert schema["properties"]["quality_candidate_refs"]["items"]["enum"] == [
        candidate_ref
    ]
    definitions = schema["$defs"]
    assert definitions["_ProviderQualityEvidence"]["properties"]["evidence_id"][
        "enum"
    ] == [evidence_ref]
    assert definitions["_ProviderQualityCriterion"]["properties"][
        "supporting_refs"
    ]["items"]["enum"] == [candidate_ref, evidence_ref]
    assert definitions["_ProviderStageItemCount"]["properties"][
        "source_context_key"
    ]["enum"] == ["problem_questions"]


def test_mission_prompt_projects_canonical_tool_schema_and_source_boundary() -> None:
    prompt = render_workspace_mission_prompt(
        {
            "mission_policy_snapshot": {"id": "math_modeling_solution"},
            "stage_contracts": {"problem_understanding": {"stage_id": "problem_understanding"}},
            "tool_policy": {
                "allowed_tool_ids": [
                    "source.import_candidate",
                    "sandbox.run_python",
                ]
            },
            "worker_skill_snapshots": {},
        }
    )

    assert "canonical_tool_contracts" in prompt
    assert '"citation_key"' in prompt
    assert '"verification_ref"' in prompt
    assert "artifact-candidate:<sha256>" in prompt
    assert "only after the corresponding stage passed" in prompt
    assert '"script"' in prompt
    assert "A user chat message" in prompt
    assert "is Mission context, not a source candidate" in prompt
    assert "question_1_model" in prompt
    assert "A per_item contract is a stage family" in prompt
    assert "Subagents are bounded collaborators, not relays" in prompt
    assert "canonical tools directly from the WorkspaceAgent" in prompt
    assert "never retry an equivalent delegation" in prompt
    assert "snapshot_json.mission_lineage.upstream_refs" in prompt
    assert "canonical internal handoff between stages" in prompt
    assert "artifact.read_candidate" in prompt


def test_mission_scope_accepts_only_canonical_per_item_stage_instances() -> None:
    contract = StageAcceptanceContract(
        schema_version="stage_acceptance_contract.v2",
        contract_id="math.question_model",
        version=1,
        mission_policy_id="math",
        workspace_type="math_modeling",
        stage_id="question_model",
        stage_goal="Model one parsed question.",
        minimum_criteria=(StageCriterion(criterion_id="valid", description="Model is valid."),),
        allowed_actions_if_failed=("revise_existing", "stop_execution"),
        instantiation=StageInstantiationRule(
            mode="per_item",
            source_context_key="problem_questions",
            instance_id_template="question_{index}_model",
        ),
        advance_condition="The instance passes.",
        stop_condition="No valid model can be produced.",
    )
    runtime = {
        "stage_contracts": {contract.stage_id: contract.model_dump(mode="json")},
        "tool_policy": {"allowed_tool_ids": []},
        "worker_skill_snapshots": {},
    }

    _validate_decision_scope(
        MissionAgentDecision(
            decision_id="continue-question-1",
            kind=MissionDecisionKind.CONTINUE,
            summary="Plan question one.",
            stage_id="question_1_model",
        ),
        runtime,
    )

    for invalid_stage_id in ("question_model", "question_0_model", "question_01_model"):
        with pytest.raises(MissionAgentProtocolError, match="pinned by MissionPolicy"):
            _validate_decision_scope(
                MissionAgentDecision(
                    decision_id=f"continue-{invalid_stage_id}",
                    kind=MissionDecisionKind.CONTINUE,
                    summary="Invalid stage.",
                    stage_id=invalid_stage_id,
                ),
                runtime,
            )


def test_mission_prompt_rejects_tool_without_canonical_schema() -> None:
    with pytest.raises(ValueError, match="no canonical input schema"):
        render_workspace_mission_prompt(
            {
                "mission_policy_snapshot": {"id": "test"},
                "stage_contracts": {"stage": {"stage_id": "stage"}},
                "tool_policy": {"allowed_tool_ids": ["unknown.tool"]},
                "worker_skill_snapshots": {},
            }
        )


def test_mission_loop_maps_typed_subagent_jobs_to_runtime_scope() -> None:
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mission_step",
                    "args": {
                        "decision_id": "delegate-1",
                        "kind": "subagent",
                        "summary": "Draft the grounded materials inventory",
                        "operation_id": "op-delegate-1",
                        "stage_id": "materials_inventory",
                        "risk_level": "low",
                        "plan_json": "{}",
                        "tool_name": None,
                        "tool_arguments_json": "{}",
                        "subagent_jobs": [
                            {
                                "display_name": "材料整理师",
                                "role_label": "软著材料专员",
                                "worker_skill_id": "software-documenter",
                                "task_summary": "Separate known facts from missing materials",
                                "task_input_json": '{"known_facts":["React"]}',
                                "selected_refs": ["prism-file:input-1"],
                                "budget": {
                                    "max_turns": 4,
                                    "max_tool_steps": 0,
                                    "max_context_bytes": 96000,
                                    "max_result_bytes": 48000,
                                },
                            }
                        ],
                        "quality_candidate_refs": [],
                        "quality_criteria": [],
                        "quality_blocking_user_inputs": [],
                        "review_summary": None,
                        "review_items": [],
                        "failure_reason": None,
                        "pause_request": None,
                    },
                    "id": "frame-subagent",
                }
            ],
        )
    )

    job = decision.payload_json["input_scope"]["jobs"][0]
    assert job["worker_skill_id"] == "software-documenter"
    assert job["known_facts"] == ["React"]
    assert job["budget"]["max_turns"] == 4


def test_mission_scope_rejects_placeholder_or_output_selected_refs() -> None:
    runtime = {
        "stage_contracts": {},
        "tool_policy": {"allowed_tool_ids": []},
        "worker_skill_snapshots": {
            "experiment-analyst": {
                "contract": {},
                "allowed_tool_ids": [],
            }
        },
    }
    for invalid_ref in ("sandbox-artifact:pending", "sbxout_not-a-selected-ref"):
        with pytest.raises(MissionAgentProtocolError, match="receipt-backed"):
            _validate_decision_scope(
                    MissionAgentDecision(
                        decision_id=f"delegate-{invalid_ref}",
                        kind=MissionDecisionKind.SUBAGENT,
                        summary="Delegate validation.",
                        operation_id=f"op-delegate-{invalid_ref}",
                    payload_json={
                        "input_scope": {
                            "jobs": [
                                {
                                    "worker_skill_id": "experiment-analyst",
                                    "selected_refs": [invalid_ref],
                                }
                            ]
                        }
                    },
                ),
                runtime,
            )


def test_mission_scope_rejects_selected_ref_unreadable_by_worker_skill() -> None:
    candidate_ref = "artifact-candidate:" + "a" * 64
    runtime = {
        "stage_contracts": {},
        "tool_policy": {"allowed_tool_ids": ["artifact.read_candidate"]},
        "worker_skill_snapshots": {
            "methodology-designer": {
                "contract": {},
                "allowed_tool_ids": [],
            }
        },
    }
    decision = MissionAgentDecision(
        decision_id="delegate-methodology",
        kind=MissionDecisionKind.SUBAGENT,
        summary="Delegate model design.",
        operation_id="delegate-methodology",
        payload_json={
            "input_scope": {
                "jobs": [
                    {
                        "worker_skill_id": "methodology-designer",
                        "selected_refs": [candidate_ref],
                    }
                ]
            }
        },
    )

    with pytest.raises(MissionAgentProtocolError, match="cannot hydrate selected_refs"):
        _validate_decision_scope(decision, runtime)

    runtime["worker_skill_snapshots"]["methodology-designer"][
        "allowed_tool_ids"
    ] = ["artifact.read_candidate"]
    _validate_decision_scope(decision, runtime)


def test_mission_scope_rejects_duplicate_subagent_selected_refs() -> None:
    candidate_ref = "artifact-candidate:" + "a" * 64
    runtime = {
        "stage_contracts": {},
        "tool_policy": {"allowed_tool_ids": ["artifact.read_candidate"]},
        "worker_skill_snapshots": {
            "manuscript-writer": {
                "contract": {},
                "allowed_tool_ids": ["artifact.read_candidate"],
            }
        },
    }
    decision = MissionAgentDecision(
        decision_id="delegate-duplicate-refs",
        kind=MissionDecisionKind.SUBAGENT,
        summary="Delegate manuscript integration.",
        operation_id="delegate-duplicate-refs",
        payload_json={
            "input_scope": {
                "jobs": [
                    {
                        "worker_skill_id": "manuscript-writer",
                        "selected_refs": [candidate_ref, candidate_ref],
                    }
                ]
            }
        },
    )

    with pytest.raises(MissionAgentProtocolError, match="unique refs"):
        _validate_decision_scope(decision, runtime)


def test_mission_loop_maps_typed_review_items_to_atomic_candidates() -> None:
    arguments = {
        "decision_id": "review-1",
        "kind": "review",
        "summary": "Prepare the materials inventory for review",
        "operation_id": "op-review-1",
        "stage_id": "materials_inventory",
        "risk_level": "medium",
        "plan_json": "{}",
        "tool_name": None,
        "tool_arguments_json": "{}",
        "subagent_jobs": [],
        "quality_candidate_refs": [],
        "quality_criteria": [],
        "quality_blocking_user_inputs": [],
        "review_summary": "One grounded draft is ready",
        "review_items": [
            {
                "candidate_ref": "artifact-candidate:" + "a" * 64,
                "output_key": "literature_positioning",
                "target_kind": "document",
                "target_room": "documents",
                "target_ref": None,
                "base_revision_ref": None,
                "base_hash": None,
                "title": "软著材料盘点",
                "summary": "Known facts and missing evidence",
                "risk_level": "medium",
                "review_required_reason": "Document write requires confirmation",
            }
        ],
        "failure_reason": None,
        "pause_request": None,
    }
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mission_step",
                    "args": arguments,
                    "id": "frame-review",
                }
            ],
        )
    )

    item = decision.payload_json["items"][0]
    assert item["target_room"] == "documents"
    assert item["candidate_ref"] == "artifact-candidate:" + "a" * 64
    assert "preview_json" not in item
    assert "review_item_id" not in item

    arguments["review_items"][0]["review_item_id"] = "model-owned-id"
    with pytest.raises(MissionAgentProtocolError, match="did not match the schema"):
        parse_mission_decision(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "mission_step",
                        "args": arguments,
                        "id": "frame-review-with-id",
                    }
                ],
            )
        )


def test_mission_loop_maps_quality_assessment_without_snapshot_side_channel() -> None:
    base = {
        "decision_id": "quality-1",
        "kind": "quality",
        "summary": "Evaluate the materials inventory",
        "operation_id": "op-quality-1",
        "stage_id": "materials_inventory",
        "risk_level": "medium",
        "plan_json": "{}",
        "tool_name": None,
        "tool_arguments_json": "{}",
        "subagent_jobs": [],
        "quality_candidate_refs": ["artifact-candidate:" + "b" * 64],
        "quality_item_counts": [
            {"source_context_key": "problem_questions", "count": 3}
        ],
        "quality_criteria": [
            {
                "criterion_id": "software_identity",
                "status": "pass",
                "supporting_refs": ["artifact-candidate:" + "b" * 64],
                "rationale": "Identity fields are explicit.",
            }
        ],
        "quality_exemplar_comparisons": [
            {
                "exemplar_ref_id": "software.inventory.excellent.v1",
                "verdict": "meets",
                "criterion_ids": ["software_identity"],
                "note": "The candidate matches the pinned example characteristics.",
            }
        ],
        "quality_blocking_user_inputs": [],
        "review_summary": None,
        "review_items": [],
        "failure_reason": None,
        "pause_request": None,
    }
    decision = parse_mission_decision(
        AIMessage(
            content="",
            tool_calls=[{"name": "mission_step", "args": base, "id": "frame-quality"}],
        )
    )

    assessment = decision.payload_json["assessment"]
    assert decision.payload_json["item_counts"] == {"problem_questions": 3}
    assert assessment["criterion_assessments"][0]["criterion_id"] == "software_identity"
    assert "artifacts" not in assessment
    assert "critiques" not in assessment
    assert assessment["exemplar_comparisons"][0]["verdict"] == "meets"


def test_mission_loop_rejects_duplicate_immutable_read_with_completed_result() -> None:
    input_ref = "mission-input:" + "a" * 64
    tool_call = _mission_item(
        seq=10,
        item_type="tool_call",
        payload={
            "tool_name": "workspace.read_input",
            "arguments": {"input_ref": input_ref},
        },
    ).model_copy(update={"operation_id": "read-input-1"})
    tool_result = _mission_item(
        seq=11,
        item_type="tool_result",
        payload={"tool_name": "workspace.read_input", "content": "immutable text"},
    ).model_copy(update={"operation_id": "read-input-1"})
    context = MissionLoopContext(
        mission=_mission_payload(),
        recent_items=[tool_call, tool_result],
        reference_items=[],
        model_turns_used=1,
        tool_steps_used=1,
        deadline_monotonic=1000.0,
    )
    decision = MissionAgentDecision(
        decision_id="read-input-again",
        kind=MissionDecisionKind.TOOL,
        operation_id="read-input-2",
        stage_id="question_1_solution_validation",
        summary="Read the same immutable input again",
        payload_json={
            "tool_name": "workspace.read_input",
            "arguments": {"input_ref": input_ref},
        },
    )

    with pytest.raises(MissionAgentProtocolError, match="already completed"):
        _validate_decision_context(decision, context)


def test_durable_reference_receipt_blocks_read_after_recent_window_rolls() -> None:
    candidate_ref = "artifact-candidate:" + "a" * 64
    receipt = _mission_item(
        seq=4,
        item_type="evidence",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(
        update={
            "operation_id": "read-candidate-1",
            "payload_ref": candidate_ref,
        }
    )
    context = MissionLoopContext(
        mission=_mission_payload(),
        recent_items=[],
        reference_items=[receipt],
        model_turns_used=4,
        tool_steps_used=4,
        deadline_monotonic=1000.0,
    )
    decision = MissionAgentDecision(
        decision_id="read-candidate-again",
        kind=MissionDecisionKind.TOOL,
        operation_id="read-candidate-2",
        stage_id="question_1_solution_validation",
        summary="Read the same immutable candidate again",
        payload_json={
            "tool_name": "artifact.read_candidate",
            "arguments": {"candidate_ref": candidate_ref},
        },
    )

    assert _hydrated_reference_reads([receipt]) == [
        {
            "ref": candidate_ref,
            "tool_name": "artifact.read_candidate",
            "stage_id": "question_1_solution_validation",
            "summary": "evidence summary",
            "operation_id": "read-candidate-1",
        }
    ]
    with pytest.raises(MissionAgentProtocolError, match="already completed"):
        _validate_decision_context(decision, context)


def test_agent_mission_projection_excludes_runtime_and_worker_coordination_state() -> None:
    projection = _agent_mission_projection(_mission_payload())

    assert projection["objective"] == "Validate question one in the sandbox."
    assert projection["active_stage_id"] == "question_1_solution_validation"
    assert projection["snapshot_json"]["stage_status"]["question_1_model"] == "passed"
    assert "runtime_context_json" not in projection
    assert "context_checkpoint_ref" not in projection
    assert "mission_idempotency_key" not in projection
    assert "lease_owner" not in projection
    assert "lease_epoch" not in projection
    assert "dispatch_owner" not in projection
    assert "next_wakeup_at" not in projection


def test_mission_state_projects_pinned_inputs_as_authoritative_ready_inventory() -> None:
    mission = _mission_payload().model_copy(
        update={
            "snapshot_json": {
                "mission_inputs": [
                    {
                        "input_ref": "mission-input:" + "a" * 64,
                        "filename": "附件1.xlsx",
                        "member_path": "赛题/附件1.xlsx",
                        "extractor": "xlsx_text",
                        "text_chars": 571,
                    }
                ]
            }
        }
    )

    assert _mission_input_inventory(mission) == [
        {
            "input_ref": "mission-input:" + "a" * 64,
            "filename": "附件1.xlsx",
            "member_path": "赛题/附件1.xlsx",
            "extractor": "xlsx_text",
            "text_chars": 571,
            "status": "ready",
        }
    ]
def test_agent_item_projection_keeps_semantics_once_and_compacts_receipts() -> None:
    body = "SENTINEL_DOCUMENT_BODY"
    terminal = _mission_item(seq=1, item_type="operation_terminal", payload={"content": body})
    evidence = _mission_item(seq=2, item_type="evidence", payload={"content": body})
    tool_result = _mission_item(seq=3, item_type="tool_result", payload={"content": body})
    command = _mission_item(seq=4, item_type="command_received", payload={"instruction": "continue"})

    assert "payload_json" not in _agent_item_projection(terminal)
    assert "payload_json" not in _agent_item_projection(evidence)
    assert _agent_item_projection(tool_result)["payload_json"] == {"content": body}
    assert _agent_item_projection(command)["payload_json"] == {"instruction": "continue"}

    rendered = _render_mission_state(
        MissionLoopContext(
            mission=_mission_payload(),
            pending_commands=[command],
            recent_items=[terminal, evidence, tool_result],
            model_turns_used=1,
            tool_steps_used=2,
            deadline_monotonic=100.0,
        )
    )
    state = json.loads(rendered)

    assert rendered.count(body) == 1
    assert state["pending_commands"][0]["payload_json"] == {"instruction": "continue"}
    assert "runtime_context_json" not in state["mission"]


def test_quality_reference_inventory_exposes_exact_candidate_receipt() -> None:
    candidate_ref = "artifact-candidate:" + "b" * 64
    candidate = _mission_item(
        seq=5,
        item_type="artifact",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "title": "第一问模型",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(update={"payload_ref": candidate_ref})

    inventory = _quality_reference_inventory([candidate])

    assert inventory["candidates"] == [
        {
            "ref": candidate_ref,
            "mission_id": "mission-1",
            "stage_id": "question_1_solution_validation",
            "kind": "artifact_candidate",
            "title": "第一问模型",
            "content_evidence_surfaces": [],
            "supported_claim_refs": [],
            "subagent_readable": True,
        }
    ]


def test_quality_reference_inventory_projects_candidate_as_content_backed_evidence() -> None:
    candidate_ref = "artifact-candidate:" + "c" * 64
    upstream_ref = "artifact-candidate:" + "d" * 64
    visual_ref = "academic-visual:q3-policy-summary"
    candidate = _mission_item(
        seq=6,
        item_type="artifact",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "title": "完整论文",
            "verified": True,
            "metadata": {
                "preview_text": (
                        f"# 完整论文\n\nC1 对应 {upstream_ref}。\n\n"
                        f"图 1 对应 {visual_ref}。\n\n"
                        "## AI 使用披露与责任\n\n"
                        "D1: 人工智能仅辅助结构组织，作者复核了全部数据、方法与结论并承担最终责任。"
                ),
                "source_refs": [upstream_ref, visual_ref],
            },
        },
    ).model_copy(update={"payload_ref": candidate_ref})

    inventory = _quality_reference_inventory([candidate])

    assert inventory["candidates"][0]["ref"] == candidate_ref
    assert inventory["candidates"][0]["mission_id"] == "mission-1"
    assert inventory["candidates"][0]["content_evidence_surfaces"] == [
        "ai_use_disclosure",
        "claim_evidence_alignment",
        "writing",
    ]
    assert inventory["candidates"][0]["supported_claim_refs"] == ["C1"]
    assert inventory["evidence"] == []


def test_reference_projection_preserves_equal_sequences_across_lineage() -> None:
    parent = _mission_item(
        seq=5,
        item_type="artifact",
        payload={"reference_id": "artifact-candidate:" + "a" * 64},
    ).model_copy(update={"mission_id": "mission-parent"})
    child = _mission_item(
        seq=5,
        item_type="artifact",
        payload={"reference_id": "artifact-candidate:" + "b" * 64},
    )

    projected = _unique_reference_items([parent, child, parent])

    assert {(item.mission_id, item.seq) for item in projected} == {
        ("mission-parent", 5),
        ("mission-1", 5),
    }


def test_subagent_reference_schema_is_inventory_bound() -> None:
    visual_ref = "academic-visual:avc_result_1"
    text_ref = "sandbox-artifact:" + "c" * 64
    schema = mission_decision_tool(
        subagent_selected_refs=(visual_ref, text_ref, visual_ref)
    )
    selected = schema["function"]["parameters"]["$defs"][
        "_ProviderSubagentJob"
    ]["properties"]["selected_refs"]

    assert selected["items"]["enum"] == [visual_ref, text_ref]

    empty_schema = mission_decision_tool()
    empty_selected = empty_schema["function"]["parameters"]["$defs"][
        "_ProviderSubagentJob"
    ]["properties"]["selected_refs"]
    assert empty_selected["maxItems"] == 0


def test_subagent_selectable_refs_exclude_binary_sandbox_artifacts() -> None:
    visual_ref = "academic-visual:avc_result_1"
    text_ref = "sandbox-artifact:" + "c" * 64
    image_ref = "sandbox-artifact:" + "d" * 64
    items = [
        _mission_item(
            seq=5,
            item_type="artifact",
            payload={
                "reference_id": visual_ref,
                "kind": "academic_visual_candidate",
                "title": "第三问策略对比",
                "verified": True,
                "metadata": {},
            },
        ),
        _mission_item(
            seq=6,
            item_type="evidence",
            payload={
                "reference_id": text_ref,
                "kind": "sandbox_artifact_manifest",
                "verified": True,
                "metadata": {
                    "kind": "application/json",
                    "size_bytes": 128,
                    "surfaces": ["experiment"],
                },
            },
        ),
        _mission_item(
            seq=7,
            item_type="evidence",
            payload={
                "reference_id": image_ref,
                "kind": "sandbox_artifact_manifest",
                "verified": True,
                "metadata": {
                    "kind": "image/png",
                    "size_bytes": 128,
                    "surfaces": ["figure_data_consistency"],
                },
            },
        ),
    ]

    inventory = _quality_reference_inventory(items)

    assert set(_subagent_selectable_refs(inventory)) == {visual_ref, text_ref}
    image = next(item for item in inventory["evidence"] if item["ref"] == image_ref)
    assert image["subagent_readable"] is False


def test_tool_context_rejects_mistyped_artifact_candidate_ref() -> None:
    candidate_ref = "artifact-candidate:" + "b" * 64
    candidate = _mission_item(
        seq=5,
        item_type="artifact",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(update={"payload_ref": candidate_ref})
    context = MissionLoopContext(
        mission=_mission_payload(),
        pending_commands=[],
        recent_items=[candidate],
        model_turns_used=1,
        tool_steps_used=0,
        deadline_monotonic=100.0,
    )
    decision = MissionAgentDecision(
        decision_id="read-candidate",
        kind=MissionDecisionKind.TOOL,
        summary="Read the accepted upstream candidate.",
        operation_id="read-candidate",
        payload_json={
            "tool_name": "artifact.read_candidate",
            "arguments": {"candidate_ref": candidate_ref + "bb"},
        },
    )

    with pytest.raises(MissionAgentProtocolError, match="copy an exact internal candidate ref"):
        _validate_decision_context(decision, context)

    valid = decision.model_copy(
        update={
            "payload_json": {
                **decision.payload_json,
                "arguments": {"candidate_ref": candidate_ref},
            }
        }
    )
    _validate_decision_context(valid, context)


@pytest.mark.parametrize(
    "candidate_ref",
    [
        "artifact-candidate:" + "d" * 64,
        "academic-visual:avc_inherited_figure",
    ],
)
def test_tool_context_allows_exact_inherited_candidate_ref(candidate_ref: str) -> None:
    mission = _mission_payload().model_copy(
        update={
            "parent_mission_id": "mission-parent",
            "snapshot_json": {
                "mission_lineage": {
                    "upstream_refs": [
                        {
                            "stage_id": "question_3_model",
                            "source_ref": candidate_ref,
                            "target_ref": candidate_ref,
                            "target_kind": "internal_candidate",
                            "output_key": "",
                        }
                    ]
                }
            },
        }
    )
    context = MissionLoopContext(
        mission=mission,
        pending_commands=[],
        recent_items=[],
        model_turns_used=0,
        tool_steps_used=0,
        deadline_monotonic=100.0,
    )
    decision = MissionAgentDecision(
        decision_id="read-inherited-candidate",
        kind=MissionDecisionKind.TOOL,
        summary="Read the inherited third-question model.",
        operation_id="read-inherited-candidate",
        payload_json={
            "tool_name": "artifact.read_candidate",
            "arguments": {"candidate_ref": candidate_ref},
        },
    )

    _validate_decision_context(decision, context)


def test_quality_context_accepts_durable_evidence_outside_recent_events() -> None:
    candidate_ref = "artifact-candidate:" + "b" * 64
    evidence_ref = "sandbox-artifact:" + "c" * 64
    candidate = _mission_item(
        seq=105,
        item_type="artifact",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(update={"payload_ref": candidate_ref})
    evidence = _mission_item(
        seq=5,
        item_type="evidence",
        payload={
            "reference_id": evidence_ref,
            "kind": "sandbox_artifact_manifest",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(update={"payload_ref": evidence_ref})
    context = MissionLoopContext(
        mission=_mission_payload(),
        pending_commands=[],
        recent_items=[candidate],
        reference_items=[evidence],
        model_turns_used=1,
        tool_steps_used=1,
        deadline_monotonic=100.0,
    )
    decision = MissionAgentDecision(
        decision_id="quality-durable-evidence",
        kind=MissionDecisionKind.QUALITY,
        summary="Assess question one",
        stage_id="question_1_solution_validation",
        operation_id="quality-durable-evidence",
        payload_json={
            "candidate_refs": [candidate_ref],
            "assessment": {
                "criterion_assessments": [
                    {
                        "criterion_id": "result_validity",
                        "status": "pass",
                        "supporting_refs": [candidate_ref, evidence_ref],
                        "rationale": "Uses durable candidate and evidence receipts.",
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": evidence_ref,
                        "surface": "experiment_reproducibility",
                        "claim_ids": [],
                    }
                ],
            },
        },
    )

    _validate_decision_context(decision, context)

    invented = decision.model_copy(
        update={
            "payload_json": {
                **decision.payload_json,
                "assessment": {
                    **decision.payload_json["assessment"],
                    "evidence": [
                        {
                            "evidence_id": "sandbox-artifact:" + "d" * 64,
                            "surface": "experiment_reproducibility",
                            "claim_ids": [],
                        }
                    ],
                },
            }
        }
    )
    with pytest.raises(MissionAgentProtocolError, match="quality_evidence"):
        _validate_decision_context(invented, context)

    invalid_surface = decision.model_copy(
        update={
            "payload_json": {
                **decision.payload_json,
                "assessment": {
                    **decision.payload_json["assessment"],
                    "evidence": [
                        {
                            "evidence_id": evidence_ref,
                            "surface": "literature",
                            "claim_ids": [],
                        }
                    ],
                },
            }
        }
    )
    with pytest.raises(MissionAgentProtocolError, match="exact surface"):
        _validate_decision_context(invalid_surface, context)


def test_quality_context_rejects_invented_support_before_runtime() -> None:
    candidate_ref = "artifact-candidate:" + "b" * 64
    candidate = _mission_item(
        seq=5,
        item_type="artifact",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(update={"payload_ref": candidate_ref})
    context = MissionLoopContext(
        mission=_mission_payload(),
        pending_commands=[],
        recent_items=[candidate],
        model_turns_used=1,
        tool_steps_used=1,
        deadline_monotonic=100.0,
    )
    decision = MissionAgentDecision(
        decision_id="quality-invalid-ref",
        kind=MissionDecisionKind.QUALITY,
        summary="Assess question one",
        stage_id="question_1_solution_validation",
        operation_id="quality-invalid-ref",
        payload_json={
            "candidate_refs": [candidate_ref],
            "assessment": {
                "criterion_assessments": [
                    {
                        "criterion_id": "result_validity",
                        "status": "pass",
                        "supporting_refs": ["sha256:" + "c" * 64],
                        "rationale": "Invalid reconstructed ref.",
                    }
                ],
                "evidence": [],
            },
        },
    )

    with pytest.raises(MissionAgentProtocolError, match="supporting_refs"):
        _validate_decision_context(decision, context)

    valid = decision.model_copy(
        update={
            "payload_json": {
                **decision.payload_json,
                "assessment": {
                    "criterion_assessments": [
                        {
                            "criterion_id": "result_validity",
                            "status": "pass",
                            "supporting_refs": [candidate_ref],
                            "rationale": "Uses the exact candidate receipt.",
                        }
                    ],
                    "evidence": [],
                },
            }
        }
    )
    _validate_decision_context(valid, context)


def test_quality_context_rejects_parent_candidate_as_current_stage_output() -> None:
    candidate_ref = "artifact-candidate:" + "e" * 64
    parent_candidate = _mission_item(
        seq=5,
        item_type="artifact",
        payload={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "verified": True,
            "metadata": {},
        },
    ).model_copy(
        update={
            "mission_id": "mission-parent",
            "payload_ref": candidate_ref,
        }
    )
    context = MissionLoopContext(
        mission=_mission_payload(),
        recent_items=[],
        reference_items=[parent_candidate],
        model_turns_used=1,
        tool_steps_used=1,
        deadline_monotonic=100.0,
    )
    decision = MissionAgentDecision(
        decision_id="quality-parent-candidate",
        kind=MissionDecisionKind.QUALITY,
        summary="Assess the current stage",
        stage_id="question_1_solution_validation",
        operation_id="quality-parent-candidate",
        payload_json={
            "candidate_refs": [candidate_ref],
            "assessment": {
                "criterion_assessments": [],
                "evidence": [],
            },
        },
    )

    with pytest.raises(MissionAgentProtocolError, match="unavailable"):
        _validate_decision_context(decision, context)


def test_agent_item_projection_externalizes_large_semantic_payloads() -> None:
    body = "large-result-body" * 1000
    tool_result = _mission_item(
        seq=5,
        item_type="tool_result",
        payload={"content": body, "metadata": {"content_hash": "a" * 64}},
    )

    projection = _agent_item_projection(tool_result)

    assert body not in json.dumps(projection)
    assert projection["payload_ref"] == "prism-file:model-spec"
    assert projection["payload_json"] == {
        "context_externalized": True,
        "payload_bytes": len(
            json.dumps(
                tool_result.payload_json,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ),
        "payload_keys": ["content", "metadata"],
        "authoritative_ref": "prism-file:model-spec",
    }


def test_agent_item_projection_keeps_normal_academic_document_inline() -> None:
    body = "model-specification-content" * 240
    tool_result = _mission_item(
        seq=5,
        item_type="tool_result",
        payload={"content": body, "metadata": {"content_hash": "a" * 64}},
    )

    projection = _agent_item_projection(tool_result)

    assert projection["payload_json"]["content"] == body
    assert "context_externalized" not in projection["payload_json"]

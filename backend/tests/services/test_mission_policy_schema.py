"""MissionPolicy, WorkerSkill and immutable bundle validation."""

import pytest
from pydantic import ValidationError

from src.contracts.mission_budget import MissionExecutionBudget
from src.contracts.mission_policy import (
    CompletionContract,
    CompletionTarget,
    MinimumContextRequirement,
    MissionAntiExample,
    MissionExample,
    MissionGoal,
    MissionPolicy,
    MissionPolicyDisplay,
    MissionRoutingPolicy,
    ReviewPolicy,
    ToolPolicy,
    VersionedPolicyRef,
    WorkerSkill,
    WorkerSkillExample,
)
from src.contracts.research_evidence import (
    NON_BYPASSABLE_REVIEW_RISKS,
    requires_user_review,
)
from src.contracts.stage_acceptance import StageAcceptanceContract, StageCriterion
from src.services.mission_policy_schema import resolve_mission_policy_bundle


def _stage(**updates) -> StageAcceptanceContract:
    payload = {
        "schema_version": "stage_acceptance_contract.v2",
        "contract_id": "sci_research.scope_topic",
        "version": 1,
        "mission_policy_id": "sci_research",
        "workspace_type": "sci",
        "stage_id": "scope_topic",
        "stage_goal": "Freeze scope.",
        "minimum_criteria": (StageCriterion(criterion_id="bounded", description="Scope is bounded."),),
        "allowed_actions_if_failed": ("revise_existing", "stop_execution"),
        "recommended_model_effort": "high",
        "advance_condition": "Scope passes.",
        "stop_condition": "Scope cannot be made feasible.",
    }
    payload.update(updates)
    return StageAcceptanceContract.model_validate(payload)


def _policy(stage: StageAcceptanceContract, **updates) -> MissionPolicy:
    payload = {
        "schema_version": "mission_policy.v1",
        "id": "sci_research",
        "version": 1,
        "workspace_type": "sci",
        "display": MissionPolicyDisplay(name="SCI 研究", description="研究任务"),
        "routing": MissionRoutingPolicy(
            when_to_use=("系统研究",),
            not_for=("短问答",),
            positive_examples=("找研究空白", "设计实验", "写论文"),
            negative_examples=("解释概念", "改一句话", "列期刊名"),
        ),
        "mission": MissionGoal(
            objective="Produce grounded research.",
            target_outcomes=("research_brief",),
            hard_constraints=("stage contracts decide progression",),
        ),
        "execution_budget": MissionExecutionBudget(
            max_model_calls=32,
            max_tool_operations=64,
            max_subagent_jobs=8,
            stop_after_total_tokens=100_000,
        ),
        "minimum_context": {"topic": MinimumContextRequirement(requirement="required", ask="研究什么？")},
        "stage_contract_refs": (stage.immutable_ref(),),
        "tool_policy": ToolPolicy(allowed_tool_groups=("workspace_read",)),
        "allowed_worker_skills": ("task-scope-planner",),
        "review_policy": ReviewPolicy(non_bypassable_risks=tuple(sorted(NON_BYPASSABLE_REVIEW_RISKS))),
        "sandbox_policy_ref": VersionedPolicyRef(policy_id="sandbox.research", version=1),
        "examples": (
            MissionExample(
                example_id="excellent-1",
                input_summary="A bounded research task",
                expected_characteristics=("evidence grounded",),
            ),
        ),
        "anti_examples": (MissionAntiExample(description="Trend mashup", failure_reason="No gap"),),
        "completion_contract": CompletionContract(
            default_target="brief",
            targets={
                "brief": CompletionTarget(
                    stage_ids=("scope_topic",),
                    terminal_output_kinds=("research_brief",),
                )
            },
        ),
    }
    payload.update(updates)
    return MissionPolicy.model_validate(payload)


def test_resolved_policy_pins_stage_contract_hash() -> None:
    stage = _stage()
    policy = _policy(stage)

    bundle = resolve_mission_policy_bundle(policy, (stage,))

    data = bundle.to_catalog_data()
    assert data["schema_version"] == "mission_policy.v1"
    assert data["content_hash"] == policy.immutable_ref().sha256
    assert data["resolved_stage_contracts"][0]["stage_id"] == "scope_topic"


def test_stage_hash_mismatch_fails_closed() -> None:
    stage = _stage()
    changed = stage.model_copy(update={"stage_goal": "Changed goal."})
    policy = _policy(stage)

    with pytest.raises(ValueError, match="hash/version mismatch"):
        resolve_mission_policy_bundle(policy, (changed,))


def test_completion_target_cannot_reference_unknown_stage() -> None:
    stage = _stage()
    policy = _policy(
        stage,
        completion_contract=CompletionContract(
            default_target="bad",
            targets={
                "bad": CompletionTarget(
                    stage_ids=("missing_stage",),
                    terminal_output_kinds=("result",),
                )
            },
        ),
    )

    with pytest.raises(ValueError, match="unknown stages"):
        resolve_mission_policy_bundle(policy, (stage,))


def test_review_policy_cannot_remove_non_bypassable_risks() -> None:
    with pytest.raises(ValidationError, match="cannot bypass"):
        ReviewPolicy(non_bypassable_risks=("citation",))


@pytest.mark.parametrize("mode", ["review_all", "balanced_default", "auto_draft"])
def test_high_risk_review_cannot_be_bypassed_by_mode(mode: str) -> None:
    assert requires_user_review(("claim", "statistics"), review_mode=mode) is True


def test_old_graph_and_team_fields_are_rejected() -> None:
    stage = _stage()
    payload = _policy(stage).model_dump(mode="json")
    payload["graph_template"] = {"phases": []}
    payload["team_policy"] = {"core_templates": ["research_scout.v1"]}

    with pytest.raises(ValidationError):
        MissionPolicy.model_validate(payload)


def test_reasoning_effort_vocabulary_is_closed() -> None:
    payload = _stage().model_dump(mode="json")
    payload["recommended_model_effort"] = "ultra"

    with pytest.raises(ValidationError):
        StageAcceptanceContract.model_validate(payload)


def test_worker_skill_is_bounded_and_has_no_lifecycle_gate_field() -> None:
    skill = WorkerSkill(
        schema_version="worker_skill.v1",
        id="research-scout",
        version=1,
        role_hint="Source scout",
        instructions=("Find verified sources.",),
        input_contract={"type": "object"},
        output_contract={
            "type": "object",
            "required": ["summary", "evidence_refs", "artifact_refs", "warnings"],
            "properties": {
                "summary": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "artifact_refs": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        },
        quality_focus=("source identity",),
        examples=(
            WorkerSkillExample(
                task="Find sources",
                strong_output_characteristics=("stable refs",),
            ),
        ),
    )

    assert skill.immutable_ref().sha256
    assert "quality_gates" not in skill.model_dump(mode="json")


def test_worker_skill_rejects_open_nested_output_objects() -> None:
    with pytest.raises(ValidationError, match="open object schema"):
        WorkerSkill(
            schema_version="worker_skill.v1",
            id="open-output",
            version=1,
            role_hint="Open output",
            instructions=("Return structured findings.",),
            input_contract={"type": "object"},
            output_contract={
                "type": "object",
                "required": ["summary", "evidence_refs", "artifact_refs", "warnings"],
                "properties": {
                    "summary": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "artifact_refs": {"type": "array", "items": {"type": "string"}},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "findings": {"type": "array", "items": {"type": "object"}},
                },
            },
            quality_focus=("schema",),
            examples=(
                WorkerSkillExample(
                    task="Return findings",
                    strong_output_characteristics=("closed schema",),
                ),
            ),
        )


def test_worker_skill_requiring_artifact_refs_must_allow_artifact_render() -> None:
    with pytest.raises(ValidationError, match="must allow artifact_render"):
        WorkerSkill(
            schema_version="worker_skill.v1",
            id="writer",
            version=1,
            role_hint="Writer",
            instructions=("Stage the deliverable.",),
            allowed_tool_groups=("workspace_read",),
            input_contract={"type": "object"},
            output_contract={
                "type": "object",
                "required": ["summary", "evidence_refs", "artifact_refs", "warnings"],
                "properties": {
                    "summary": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "artifact_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
            quality_focus=("reviewability",),
            examples=(
                WorkerSkillExample(
                    task="Draft a document",
                    strong_output_characteristics=("previewable artifact",),
                ),
            ),
        )


def test_worker_skill_rejects_old_role_prompt_shape() -> None:
    with pytest.raises(ValidationError):
        WorkerSkill.model_validate(
            {
                "schema_version": "worker_skill.v1",
                "id": "old",
                "version": 1,
                "role_hint": "Old",
                "role_prompt": "giant prompt",
                "instructions": ["bounded"],
                "input_contract": {"type": "object"},
                "output_contract": {
                    "type": "object",
                    "required": ["summary", "evidence_refs", "artifact_refs", "warnings"],
                },
                "quality_focus": ["quality"],
                "examples": [{"task": "test", "strong_output_characteristics": ["good"]}],
            }
        )

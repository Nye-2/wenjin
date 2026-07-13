"""Provider-structured mission-loop decisions for the single WorkspaceAgent."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.workspace_agent.prompts import render_workspace_mission_prompt
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    stage_id_matches_contract,
)
from src.mission_runtime.contracts import (
    MissionAgentDecision,
    MissionDecisionKind,
    MissionLoopContext,
)
from src.models import create_chat_model
from src.models.provider_schema import parse_json_object, strict_provider_schema


class WorkspaceMissionLoopProtocolError(RuntimeError):
    """The provider violated the strict WorkspaceAgent mission-loop contract."""


ModelFactory = Callable[..., BaseChatModel]


class _ProviderMissionPause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)
    reason: Literal[
        "clarification",
        "approval",
        "user_input",
        "permission",
        "external_data",
        "budget",
        "review",
    ]
    summary: str = Field(min_length=1, max_length=4000)
    pending_request_json: str


class _ProviderSubagentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns: int = Field(ge=1, le=24)
    max_tool_steps: int = Field(ge=0, le=32)
    max_context_bytes: int = Field(ge=4096, le=512_000)
    max_result_bytes: int = Field(ge=1024, le=512_000)


class _ProviderSubagentJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    role_label: str = Field(min_length=1, max_length=80)
    worker_skill_id: str = Field(min_length=1, max_length=160)
    task_summary: str = Field(min_length=1, max_length=4000)
    task_input_json: str
    selected_refs: list[str] = Field(max_length=100)
    budget: _ProviderSubagentBudget


class _ProviderReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_item_id: str = Field(min_length=1, max_length=36)
    source_item_seq: int | None = Field(ge=1)
    target_kind: str = Field(min_length=1, max_length=80)
    target_room: str | None = Field(max_length=80)
    target_ref: str | None = Field(max_length=2048)
    base_revision_ref: str | None = Field(max_length=2048)
    base_hash: str | None = Field(max_length=128)
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(max_length=4000)
    risk_level: Literal["low", "medium", "high"]
    review_required_reason: str | None = Field(max_length=4000)
    preview_json: str = Field(description="JSON object containing a complete user-previewable candidate, usually markdown content.")
    preview_ref: str | None = Field(max_length=2048)
    preview_expires_at: datetime | None = None


class _ProviderQualityCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=160)
    status: Literal["pass", "fail", "unknown"]
    supporting_refs: list[str] = Field(max_length=100)
    rationale: str = Field(max_length=4000)


class _ProviderQualityArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=2048)
    kind: str = Field(min_length=1, max_length=160)
    content_hash: str = Field(min_length=8, max_length=128)
    manifest_ref: str | None = Field(max_length=2048)
    script_ref: str | None = Field(max_length=2048)
    data_refs: list[str] = Field(max_length=100)
    metadata_json: str


class _ProviderQualityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=2048)
    surface: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=160)
    source_ref: str | None = Field(max_length=2048)
    claim_ids: list[str] = Field(max_length=100)


class _ProviderQualityCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_role: str = Field(min_length=1, max_length=160)
    verdict: Literal["pass", "revise"]
    criterion_ids: list[str] = Field(max_length=100)
    note: str = Field(max_length=4000)


class _ProviderQualityExemplarComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exemplar_ref_id: str = Field(min_length=1, max_length=300)
    verdict: Literal["below", "meets", "exceeds"]
    criterion_ids: list[str] = Field(max_length=100)
    note: str = Field(max_length=4000)


class _ProviderMissionDecision(BaseModel):
    """Provider-safe wire shape; open objects cross the boundary as JSON text."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1, max_length=160)
    kind: MissionDecisionKind
    summary: str = Field(min_length=1, max_length=4000)
    operation_id: str | None
    stage_id: str | None
    risk_level: Literal["low", "medium", "high"] | None
    plan_json: str
    tool_name: str | None
    tool_arguments_json: str
    subagent_jobs: list[_ProviderSubagentJob] = Field(max_length=8)
    quality_candidate_refs: list[str] = Field(max_length=100)
    quality_criteria: list[_ProviderQualityCriterion] = Field(max_length=100)
    quality_evidence: list[_ProviderQualityEvidence] = Field(default_factory=list, max_length=100)
    quality_artifacts: list[_ProviderQualityArtifact] = Field(max_length=100)
    quality_output_refs: list[str] = Field(max_length=100)
    quality_critiques: list[_ProviderQualityCritique] = Field(max_length=32)
    quality_exemplar_comparisons: list[_ProviderQualityExemplarComparison] = Field(
        default_factory=list,
        max_length=32,
    )
    quality_blocking_user_inputs: list[str] = Field(max_length=32)
    review_summary: str | None = Field(max_length=4000)
    review_items: list[_ProviderReviewItem] = Field(max_length=100)
    failure_reason: str | None
    pause_request: _ProviderMissionPause | None

    def to_domain(self) -> MissionAgentDecision:
        pause = None
        if self.pause_request is not None:
            pause = {
                "request_id": self.pause_request.request_id,
                "reason": self.pause_request.reason,
                "summary": self.pause_request.summary,
                "pending_request": parse_json_object(
                    self.pause_request.pending_request_json,
                    field_name="pause_request.pending_request_json",
                ),
            }
        payload = self._domain_payload()
        return MissionAgentDecision.model_validate(
            {
                "decision_id": self.decision_id,
                "kind": self.kind,
                "summary": self.summary,
                "operation_id": self.operation_id,
                "stage_id": self.stage_id,
                "risk_level": self.risk_level,
                "payload_json": payload,
                "snapshot_patch": {},
                "pause_request": pause,
            }
        )

    def _domain_payload(self) -> dict[str, Any]:
        if self.kind is MissionDecisionKind.CONTINUE:
            return parse_json_object(self.plan_json, field_name="plan_json")
        if self.kind is MissionDecisionKind.TOOL:
            return {
                "tool_name": self.tool_name,
                "arguments": parse_json_object(
                    self.tool_arguments_json,
                    field_name="tool_arguments_json",
                ),
            }
        if self.kind is MissionDecisionKind.SUBAGENT:
            jobs = []
            for job in self.subagent_jobs:
                jobs.append(
                    {
                        "display_name": job.display_name,
                        "role_label": job.role_label,
                        "worker_skill_id": job.worker_skill_id,
                        "task_summary": job.task_summary,
                        **parse_json_object(job.task_input_json, field_name="task_input_json"),
                        "selected_refs": job.selected_refs,
                        "budget": job.budget.model_dump(mode="json"),
                    }
                )
            return {"task_summary": self.summary, "input_scope": {"jobs": jobs}}
        if self.kind is MissionDecisionKind.QUALITY:
            return {
                "candidate_refs": self.quality_candidate_refs,
                "assessment": {
                    "criterion_assessments": [item.model_dump(mode="json") for item in self.quality_criteria],
                    "evidence": [{**item.model_dump(mode="json"), "status": "unverified", "metadata": {}} for item in self.quality_evidence],
                    "artifacts": [
                        {
                            **item.model_dump(mode="json", exclude={"metadata_json"}),
                            "metadata": parse_json_object(
                                item.metadata_json,
                                field_name="quality_artifacts.metadata_json",
                            ),
                        }
                        for item in self.quality_artifacts
                    ],
                    "output_refs": self.quality_output_refs,
                    "critiques": [item.model_dump(mode="json") for item in self.quality_critiques],
                    "exemplar_comparisons": [item.model_dump(mode="json") for item in self.quality_exemplar_comparisons],
                    "blocking_user_inputs": self.quality_blocking_user_inputs,
                },
            }
        if self.kind is MissionDecisionKind.REVIEW:
            return {
                "summary": self.review_summary or self.summary,
                "items": [
                    {
                        **item.model_dump(
                            mode="json",
                            exclude={"preview_json"},
                        ),
                        "preview_json": parse_json_object(
                            item.preview_json,
                            field_name="review_items.preview_json",
                        ),
                    }
                    for item in self.review_items
                ],
            }
        if self.kind is MissionDecisionKind.FAIL:
            return {"failure_reason": self.failure_reason or "mission_failed"}
        return {}


def mission_decision_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "mission_step",
            "description": "Choose exactly one durable next step for the active Wenjin mission.",
            "parameters": strict_provider_schema(_ProviderMissionDecision.model_json_schema()),
            "strict": True,
        },
    }


def parse_mission_decision(message: AIMessage) -> MissionAgentDecision:
    """Accept one provider tool frame and never recover an action from prose."""
    calls = message.tool_calls
    if len(calls) != 1:
        raise WorkspaceMissionLoopProtocolError("WorkspaceAgent mission loop requires exactly one structured action")
    call = calls[0]
    if str(call.get("name") or "") != "mission_step":
        raise WorkspaceMissionLoopProtocolError("Unknown WorkspaceAgent mission action")
    arguments = call.get("args")
    if not isinstance(arguments, dict):
        raise WorkspaceMissionLoopProtocolError("Mission action arguments must be an object")
    try:
        return _ProviderMissionDecision.model_validate(arguments).to_domain()
    except Exception as exc:
        raise WorkspaceMissionLoopProtocolError("WorkspaceAgent returned malformed mission action arguments") from exc


class WorkspaceMissionLoopAgent:
    """The durable side of WorkspaceAgent; this is not a second agent topology."""

    def __init__(self, *, model_factory: ModelFactory = create_chat_model) -> None:
        self._model_factory = model_factory

    async def decide(self, context: MissionLoopContext) -> MissionAgentDecision:
        runtime = _require_runtime_contract(context)
        model = self._model_factory(
            context.mission.model_id,
            reasoning_effort=context.mission.reasoning_effort.value,
            max_retries=0,
        )
        bound = model.bind_tools(
            [mission_decision_tool()],
            tool_choice="mission_step",
            strict=True,
        )
        response = await bound.ainvoke(
            [
                SystemMessage(content=render_workspace_mission_prompt(runtime)),
                HumanMessage(content=_render_mission_state(context)),
            ]
        )
        if not isinstance(response, AIMessage):
            raise WorkspaceMissionLoopProtocolError("WorkspaceAgent mission provider returned a non-message response")
        decision = parse_mission_decision(response)
        _validate_decision_scope(decision, runtime)
        return _attach_usage(decision, response)


def _require_runtime_contract(context: MissionLoopContext) -> dict[str, Any]:
    runtime = context.mission.runtime_context_json
    policy = runtime.get("mission_policy_snapshot")
    stages = runtime.get("stage_contracts")
    tool_policy = runtime.get("tool_policy")
    skill_snapshots = runtime.get("worker_skill_snapshots")
    if not isinstance(policy, dict) or not isinstance(stages, dict) or not stages:
        raise WorkspaceMissionLoopProtocolError("Mission policy snapshot is unavailable")
    if not isinstance(tool_policy, dict):
        raise WorkspaceMissionLoopProtocolError("Mission tool policy snapshot is unavailable")
    if not isinstance(skill_snapshots, dict):
        raise WorkspaceMissionLoopProtocolError("Mission WorkerSkill snapshots are unavailable")
    return runtime


def _render_mission_state(context: MissionLoopContext) -> str:
    payload = {
        "mission": context.mission.model_dump(mode="json", exclude_none=True),
        "pending_commands": [item.model_dump(mode="json", exclude_none=True) for item in context.pending_commands],
        "recent_items": [item.model_dump(mode="json", exclude_none=True) for item in context.recent_items[-24:]],
        "slice_budget": {
            "model_turns_used": context.model_turns_used,
            "tool_steps_used": context.tool_steps_used,
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _stage_id_is_pinned(
    stages: dict[str, Any],
    stage_id: str,
) -> bool:
    try:
        contracts = tuple(StageAcceptanceContract.model_validate(candidate) for candidate in stages.values())
        return any(stage_id_matches_contract(contract, stage_id) for contract in contracts)
    except ValidationError as exc:
        raise WorkspaceMissionLoopProtocolError("Pinned stage contract is malformed") from exc


def _validate_decision_scope(
    decision: MissionAgentDecision,
    runtime: dict[str, Any],
) -> None:
    stages = runtime["stage_contracts"]
    if decision.stage_id is not None and not _stage_id_is_pinned(stages, decision.stage_id):
        raise WorkspaceMissionLoopProtocolError(f"Mission action selected an unpinned stage: {decision.stage_id}")
    if decision.kind is MissionDecisionKind.TOOL:
        tool_name = str(decision.payload_json.get("tool_name") or "")
        allowed = runtime["tool_policy"].get("allowed_tool_ids") or []
        if tool_name not in allowed:
            raise WorkspaceMissionLoopProtocolError(f"Mission action selected a tool outside the pinned policy: {tool_name}")
    if decision.kind is MissionDecisionKind.SUBAGENT:
        input_scope = decision.payload_json.get("input_scope")
        if not isinstance(input_scope, dict):
            raise WorkspaceMissionLoopProtocolError("Subagent input_scope must be an object")
        jobs = input_scope.get("jobs", [])
        if jobs and not isinstance(jobs, list):
            raise WorkspaceMissionLoopProtocolError("Subagent jobs must be a list")
        allowed_tools = set(runtime["tool_policy"].get("allowed_tool_ids") or [])
        skill_snapshots = runtime["worker_skill_snapshots"]
        allowed_skills = set(skill_snapshots)
        for job in jobs:
            if not isinstance(job, dict):
                raise WorkspaceMissionLoopProtocolError("Subagent job must be an object")
            forbidden = {
                "worker_skill",
                "allowed_tools",
                "output_schema",
                "exit_criteria",
                "system_prompt",
                "prompt",
                "tools",
                "config",
            }
            supplied = sorted(forbidden.intersection(job))
            if supplied:
                raise WorkspaceMissionLoopProtocolError("Subagent job attempted to provide runtime-owned skill configuration: " + ", ".join(supplied))
            skill_id = str(job.get("worker_skill_id") or "")
            if not skill_id or skill_id not in allowed_skills:
                raise WorkspaceMissionLoopProtocolError("Subagent job requested an unpinned worker skill")
            snapshot = skill_snapshots.get(skill_id)
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("contract"), dict):
                raise WorkspaceMissionLoopProtocolError("Pinned WorkerSkill snapshot is malformed")
            if not set(snapshot.get("allowed_tool_ids") or ()).issubset(allowed_tools):
                raise WorkspaceMissionLoopProtocolError("Pinned WorkerSkill exceeds the Mission tool policy")


def _attach_usage(
    decision: MissionAgentDecision,
    response: AIMessage,
) -> MissionAgentDecision:
    usage = response.usage_metadata
    if not usage:
        return decision
    patch = dict(decision.snapshot_patch)
    patch["last_model_usage"] = {key: int(value) for key, value in usage.items() if isinstance(value, int) and value >= 0}
    return decision.model_copy(update={"snapshot_patch": patch})


__all__ = [
    "WorkspaceMissionLoopAgent",
    "WorkspaceMissionLoopProtocolError",
    "mission_decision_tool",
    "parse_mission_decision",
]

"""Provider-structured mission-loop decisions for the single WorkspaceAgent."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.workspace_agent.prompts import render_workspace_mission_prompt
from src.contracts.model_usage import ModelUsage, ModelUsageReceipt
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    stage_id_matches_contract,
)
from src.dataservice_client.contracts.mission import MissionItemPayload, MissionRunPayload
from src.mission_runtime.contracts import (
    MISSION_MODEL_MAX_OUTPUT_TOKENS,
    MISSION_MODEL_REQUEST_TIMEOUT_SECONDS,
    MissionAgentDecision,
    MissionAgentProtocolError,
    MissionAgentResponseError,
    MissionAgentUsageError,
    MissionDecisionKind,
    MissionLoopContext,
)
from src.mission_runtime.reference_authority import (
    canonical_reference_read,
    canonical_reference_read_for_receipt,
    evidence_authority_index,
    is_internal_candidate_reference,
)
from src.models import create_chat_model
from src.models.provider_schema import (
    ProviderToolPayloadError,
    parse_json_object,
    strict_provider_schema,
)

ModelFactory = Callable[..., BaseChatModel]

_AGENT_MISSION_FIELDS = frozenset(
    {
        "mission_id",
        "parent_mission_id",
        "workspace_id",
        "thread_id",
        "workspace_type",
        "mission_policy_id",
        "title",
        "objective",
        "status",
        "review_mode",
        "active_stage_id",
        "model_id",
        "reasoning_effort",
        "snapshot_json",
        "pending_review_count",
        "evidence_count",
        "artifact_count",
        "active_subagent_count",
        "last_command_seq",
        "last_applied_command_seq",
        "state_version",
        "last_item_seq",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    }
)
_AGENT_ITEM_FIELDS = frozenset(
    {
        "seq",
        "item_type",
        "operation_id",
        "phase",
        "stage_id",
        "producer",
        "summary",
        "risk_level",
        "payload_ref",
        "created_at",
    }
)
_RECEIPT_ONLY_ITEM_TYPES = frozenset(
    {
        "artifact",
        "context_checkpoint",
        "evidence",
        "operation_claim",
        "operation_terminal",
        "output",
    }
)
# Keep ordinary academic briefs/specifications available to the parent loop.
# Large datasets, logs, and generated artifacts still travel by canonical ref.
_AGENT_INLINE_PAYLOAD_LIMIT_BYTES = 16 * 1024
_IMMUTABLE_READ_TOOL_IDS = frozenset(
    {
        "artifact.read_candidate",
        "sandbox.read_artifact",
        "sandbox.read_output_ref",
        "workspace.read_asset",
        "workspace.read_input",
    }
)


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

    candidate_ref: str = Field(
        pattern=r"^(?:artifact-candidate:[0-9a-f]{64}|academic-visual:[A-Za-z0-9._:-]{1,160})$",
        max_length=180,
    )
    output_key: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z0-9][a-z0-9_.:-]*$",
    )
    target_kind: str = Field(min_length=1, max_length=80)
    target_room: str | None = Field(max_length=80)
    target_ref: str | None = Field(max_length=2048)
    base_revision_ref: str | None = Field(max_length=2048)
    base_hash: str | None = Field(max_length=128)
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(max_length=4000)
    risk_level: Literal["low", "medium", "high"]
    review_required_reason: str | None = Field(max_length=4000)


class _ProviderQualityCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=160)
    status: Literal["pass", "fail", "unknown"]
    supporting_refs: list[str] = Field(max_length=100)
    rationale: str = Field(min_length=20, max_length=4000)


class _ProviderQualityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=2048)
    surface: str = Field(min_length=1, max_length=160)
    claim_ids: list[str] = Field(max_length=100)


class _ProviderQualityExemplarComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exemplar_ref_id: str = Field(min_length=1, max_length=300)
    verdict: Literal["below", "meets", "exceeds"]
    criterion_ids: list[str] = Field(max_length=100)
    note: str = Field(max_length=4000)


class _ProviderStageItemCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_context_key: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_.:-]*$",
    )
    count: int = Field(ge=1, le=100)


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
    quality_exemplar_comparisons: list[_ProviderQualityExemplarComparison] = Field(
        default_factory=list,
        max_length=32,
    )
    quality_item_counts: list[_ProviderStageItemCount] = Field(
        default_factory=list,
        max_length=16,
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
            item_counts: dict[str, int] = {}
            for item in self.quality_item_counts:
                if item.source_context_key in item_counts:
                    raise ProviderToolPayloadError(
                        "quality_item_counts contains a duplicate source_context_key"
                    )
                item_counts[item.source_context_key] = item.count
            return {
                "candidate_refs": self.quality_candidate_refs,
                "item_counts": item_counts,
                "assessment": {
                    "criterion_assessments": [item.model_dump(mode="json") for item in self.quality_criteria],
                    "evidence": [{**item.model_dump(mode="json"), "status": "unverified", "metadata": {}} for item in self.quality_evidence],
                    "exemplar_comparisons": [item.model_dump(mode="json") for item in self.quality_exemplar_comparisons],
                    "blocking_user_inputs": self.quality_blocking_user_inputs,
                },
            }
        if self.kind is MissionDecisionKind.REVIEW:
            return {
                "summary": self.review_summary or self.summary,
                "items": [item.model_dump(mode="json") for item in self.review_items],
            }
        if self.kind is MissionDecisionKind.FAIL:
            return {"failure_reason": self.failure_reason or "mission_failed"}
        return {}


def mission_decision_tool(
    *,
    subagent_selected_refs: tuple[str, ...] = (),
    quality_candidate_refs: tuple[str, ...] = (),
    quality_evidence_refs: tuple[str, ...] = (),
    quality_item_count_sources: tuple[str, ...] = (),
) -> dict[str, Any]:
    parameters = strict_provider_schema(_ProviderMissionDecision.model_json_schema())
    candidate_refs = list(dict.fromkeys(quality_candidate_refs))
    evidence_refs = list(dict.fromkeys(quality_evidence_refs))
    item_count_sources = list(dict.fromkeys(quality_item_count_sources))
    authoritative_refs = list(dict.fromkeys((*candidate_refs, *evidence_refs)))
    if candidate_refs:
        parameters["properties"]["quality_candidate_refs"]["items"]["enum"] = (
            candidate_refs
        )
    else:
        parameters["properties"]["quality_candidate_refs"]["maxItems"] = 0
    definitions = parameters.get("$defs") or {}
    selected_refs = list(dict.fromkeys(subagent_selected_refs))
    if selected_refs:
        definitions["_ProviderSubagentJob"]["properties"]["selected_refs"][
            "items"
        ]["enum"] = selected_refs
    else:
        definitions["_ProviderSubagentJob"]["properties"]["selected_refs"][
            "maxItems"
        ] = 0
    if evidence_refs:
        definitions["_ProviderQualityEvidence"]["properties"]["evidence_id"][
            "enum"
        ] = evidence_refs
    if authoritative_refs:
        definitions["_ProviderQualityCriterion"]["properties"]["supporting_refs"][
            "items"
        ]["enum"] = authoritative_refs
    if item_count_sources:
        definitions["_ProviderStageItemCount"]["properties"][
            "source_context_key"
        ]["enum"] = item_count_sources
    return {
        "type": "function",
        "function": {
            "name": "mission_step",
            "description": "Choose exactly one durable next step for the active Wenjin mission.",
            "parameters": parameters,
            "strict": True,
        },
    }


def parse_mission_decision(message: AIMessage) -> MissionAgentDecision:
    """Accept one provider tool frame and never recover an action from prose."""
    calls = message.tool_calls
    if len(calls) != 1:
        raise MissionAgentProtocolError("Return exactly one mission_step action")
    call = calls[0]
    if str(call.get("name") or "") != "mission_step":
        raise MissionAgentProtocolError("Return the mission_step action, not another tool")
    arguments = call.get("args")
    if not isinstance(arguments, dict):
        raise MissionAgentProtocolError("mission_step arguments must be a JSON object")
    try:
        return _ProviderMissionDecision.model_validate(arguments).to_domain()
    except ValidationError as exc:
        issues = [f"{'.'.join(str(part) for part in issue['loc'])}:{issue['type']}" for issue in exc.errors(include_input=False)[:8]]
        detail = ", ".join(issues) or "schema validation failed"
        raise MissionAgentProtocolError(f"mission_step arguments did not match the schema ({detail})") from exc
    except ProviderToolPayloadError as exc:
        raise MissionAgentProtocolError(str(exc)) from exc


class WorkspaceMissionLoopAgent:
    """The durable side of WorkspaceAgent; this is not a second agent topology."""

    def __init__(self, *, model_factory: ModelFactory = create_chat_model) -> None:
        self._model_factory = model_factory

    async def decide(self, context: MissionLoopContext) -> MissionAgentDecision:
        runtime = _require_runtime_contract(context)
        reference_inventory = _quality_reference_inventory(
            _unique_reference_items(
                [*context.reference_items, *context.recent_items]
            )
        )
        model = self._model_factory(
            context.mission.model_id,
            reasoning_effort=context.mission.reasoning_effort.value,
            request_timeout=MISSION_MODEL_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
            max_output_tokens=MISSION_MODEL_MAX_OUTPUT_TOKENS,
        )
        bound = model.bind_tools(
            [
                mission_decision_tool(
                    subagent_selected_refs=_subagent_selectable_refs(
                        reference_inventory
                    ),
                    quality_candidate_refs=tuple(
                        str(item["ref"])
                        for item in reference_inventory["candidates"]
                        if item.get("mission_id") == context.mission.mission_id
                    ),
                    quality_evidence_refs=tuple(
                        str(item["ref"])
                        for item in reference_inventory["evidence"]
                    ),
                    quality_item_count_sources=tuple(
                        sorted(
                            {
                                str(instantiation["source_context_key"])
                                for contract in runtime["stage_contracts"].values()
                                if isinstance(contract, dict)
                                and isinstance(
                                    instantiation := contract.get("instantiation"),
                                    dict,
                                )
                                and instantiation.get("mode") == "per_item"
                                and instantiation.get("source_context_key")
                            }
                        )
                    ),
                )
            ],
            tool_choice="mission_step",
            strict=True,
        )
        messages = [SystemMessage(content=render_workspace_mission_prompt(runtime))]
        if context.protocol_feedback:
            messages.append(SystemMessage(content=(f"Your previous mission_step response violated the structured contract. Correct it now: {context.protocol_feedback}. Return exactly one mission_step tool call and no prose.")))
        messages.append(HumanMessage(content=_render_mission_state(context)))
        response = await bound.ainvoke(messages)
        usage_receipt = _model_usage_receipt(response, model_id=context.mission.model_id)
        if not isinstance(response, AIMessage):
            raise MissionAgentProtocolError(
                "Return one structured mission_step response",
                usage_receipt=usage_receipt,
            )
        try:
            decision = parse_mission_decision(response)
            _validate_decision_scope(decision, runtime)
            _validate_decision_context(decision, context)
        except MissionAgentProtocolError as exc:
            raise MissionAgentProtocolError(
                str(exc),
                usage_receipt=usage_receipt,
            ) from exc
        except Exception as exc:
            raise MissionAgentResponseError(
                "Mission response validation failed",
                usage_receipt=usage_receipt,
            ) from exc
        return decision.model_copy(update={"usage_receipt": usage_receipt})


def _require_runtime_contract(context: MissionLoopContext) -> dict[str, Any]:
    runtime = context.mission.runtime_context_json
    policy = runtime.get("mission_policy_snapshot")
    stages = runtime.get("stage_contracts")
    tool_policy = runtime.get("tool_policy")
    skill_snapshots = runtime.get("worker_skill_snapshots")
    if not isinstance(policy, dict) or not isinstance(stages, dict) or not stages:
        raise RuntimeError("Mission policy snapshot is unavailable")
    if not isinstance(tool_policy, dict):
        raise RuntimeError("Mission tool policy snapshot is unavailable")
    if not isinstance(skill_snapshots, dict):
        raise RuntimeError("Mission WorkerSkill snapshots are unavailable")
    return runtime


def _render_mission_state(context: MissionLoopContext) -> str:
    reference_items = _unique_reference_items(
        [*context.reference_items, *context.recent_items]
    )
    payload = {
        "mission": _agent_mission_projection(context.mission),
        "pending_commands": [_agent_item_projection(item) for item in context.pending_commands],
        "recent_items": [_agent_item_projection(item) for item in context.recent_items[-24:]],
        "quality_reference_inventory": _quality_reference_inventory(
            reference_items
        ),
        "hydrated_reference_reads": _hydrated_reference_reads(reference_items),
        "slice_budget": {
            "model_turns_used": context.model_turns_used,
            "tool_steps_used": context.tool_steps_used,
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _agent_mission_projection(mission: MissionRunPayload) -> dict[str, Any]:
    """Project durable Mission state without duplicating runtime-owned contracts."""
    return mission.model_dump(
        mode="json",
        include=_AGENT_MISSION_FIELDS,
        exclude_none=True,
    )


def _agent_item_projection(item: MissionItemPayload) -> dict[str, Any]:
    """Keep one semantic payload while retaining lightweight ledger receipts."""
    include = set(_AGENT_ITEM_FIELDS)
    if item.item_type not in _RECEIPT_ONLY_ITEM_TYPES:
        include.add("payload_json")
    projection = item.model_dump(mode="json", include=include, exclude_none=True)
    payload = projection.get("payload_json")
    if isinstance(payload, dict):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > _AGENT_INLINE_PAYLOAD_LIMIT_BYTES:
            projection["payload_json"] = {
                "context_externalized": True,
                "payload_bytes": len(encoded),
                "payload_keys": sorted(str(key) for key in payload)[:32],
                "authoritative_ref": item.payload_ref,
            }
    return projection


def _quality_reference_inventory(
    items: list[MissionItemPayload],
) -> dict[str, list[dict[str, Any]]]:
    """Project exact receipt-backed refs without exposing full receipt payloads."""
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    verified_receipts: dict[str, tuple[str, dict[str, object]]] = {}
    authorities = evidence_authority_index(items)
    for item in items:
        if item.phase.value != "completed":
            continue
        payload = item.payload_json
        payload_reference = str(payload.get("reference_id") or "").strip()
        payload_kind = str(payload.get("kind") or "").strip()
        payload_metadata = payload.get("metadata")
        if (
            payload_reference
            and payload_kind
            and payload.get("verified") is True
            and isinstance(payload_metadata, dict)
        ):
            verified_receipts[payload_reference] = (
                payload_kind,
                payload_metadata,
            )
        payload_ref = str(item.payload_ref or "").strip()
        candidate_ref = payload_reference or payload_ref
        if (
            is_internal_candidate_reference(candidate_ref)
            and item.item_type == "artifact"
            and payload.get("verified") is True
            and isinstance(payload_metadata, dict)
        ):
            authority = authorities.get(candidate_ref)
            candidates.setdefault(
                (item.mission_id, candidate_ref),
                {
                    "ref": candidate_ref,
                    "mission_id": item.mission_id,
                    "stage_id": item.stage_id,
                    "kind": str(payload.get("kind") or "internal_candidate"),
                    "title": str(payload.get("title") or item.summary or "")[:300],
                    "content_evidence_surfaces": (
                        sorted(authority.surfaces) if authority is not None else []
                    ),
                    "supported_claim_refs": (
                        sorted(authority.supported_claims)
                        if authority is not None
                        else []
                    ),
                    "subagent_readable": (
                        canonical_reference_read_for_receipt(
                            candidate_ref,
                            kind=payload_kind,
                            metadata=payload_metadata,
                        )
                        is not None
                    ),
                },
            )
            continue
    for authority in authorities.values():
        if authority.kind == "artifact_candidate":
            continue
        receipt = verified_receipts.get(authority.evidence_id)
        evidence[authority.evidence_id] = {
            "ref": authority.evidence_id,
            "stage_id": authority.stage_id,
            "kind": authority.kind,
            "surfaces": sorted(authority.surfaces),
            "supported_claim_refs": sorted(authority.supported_claims),
            "title": authority.title,
            "subagent_readable": (
                receipt is not None
                and canonical_reference_read_for_receipt(
                    authority.evidence_id,
                    kind=receipt[0],
                    metadata=receipt[1],
                )
                is not None
            ),
        }
    return {
        "candidates": list(candidates.values()),
        "evidence": list(evidence.values()),
    }


def _subagent_selectable_refs(
    inventory: dict[str, list[dict[str, Any]]],
) -> tuple[str, ...]:
    """Expose only receipt-backed refs with one canonical hydration route."""

    refs = (
        str(item.get("ref") or "")
        for item in [*inventory["candidates"], *inventory["evidence"]]
        if item.get("subagent_readable") is True
    )
    return tuple(
        dict.fromkeys(ref for ref in refs if canonical_reference_read(ref) is not None)
    )


def _unique_reference_items(
    items: list[MissionItemPayload],
) -> list[MissionItemPayload]:
    """Merge durable reference projections with recent terminal tool receipts."""
    by_identity = {(item.mission_id, item.seq): item for item in items}
    return sorted(
        by_identity.values(),
        key=lambda item: (item.created_at, item.mission_id, item.seq),
    )


def _hydrated_reference_reads(
    items: list[MissionItemPayload],
) -> list[dict[str, str | None]]:
    """Project durable successful context hydration independently of recent events."""

    hydrated: dict[str, dict[str, str | None]] = {}
    for item in items:
        if item.item_type != "evidence" or item.phase.value != "completed":
            continue
        payload = item.payload_json
        metadata = payload.get("metadata")
        ref = str(payload.get("reference_id") or item.payload_ref or "").strip()
        kind = str(payload.get("kind") or "").strip()
        if (
            payload.get("verified") is not True
            or not ref
            or not kind
            or not isinstance(metadata, dict)
        ):
            continue
        read = canonical_reference_read_for_receipt(
            ref,
            kind=kind,
            metadata=metadata,
        )
        if read is None:
            continue
        hydrated[ref] = {
            "ref": ref,
            "tool_name": read.tool_name,
            "stage_id": item.stage_id,
            "summary": item.summary,
            "operation_id": item.operation_id,
        }
    return list(hydrated.values())


def _validate_decision_context(
    decision: MissionAgentDecision,
    context: MissionLoopContext,
) -> None:
    """Reject invented quality refs while the provider can still self-correct."""
    inventory = _quality_reference_inventory(
        _unique_reference_items([*context.reference_items, *context.recent_items])
    )
    if decision.kind is MissionDecisionKind.TOOL:
        tool_name = str(decision.payload_json.get("tool_name") or "")
        arguments = decision.payload_json.get("arguments")
        if tool_name in _IMMUTABLE_READ_TOOL_IDS and isinstance(arguments, dict):
            prior_operation_id = _completed_immutable_read_operation(
                _unique_reference_items(
                    [*context.reference_items, *context.recent_items]
                ),
                tool_name=tool_name,
                arguments=arguments,
            )
            if prior_operation_id is not None:
                raise MissionAgentProtocolError(
                    f"{tool_name} already completed for these immutable arguments as "
                    f"operation_id={prior_operation_id}; reuse its existing tool_result"
                )
        if tool_name == "artifact.read_candidate" and isinstance(arguments, dict):
            candidate_ref = str(arguments.get("candidate_ref") or "")
            available = sorted(
                {
                    *(
                        str(item["ref"])
                        for item in inventory["candidates"]
                        if (
                            read := canonical_reference_read(
                                str(item.get("ref") or "")
                            )
                        )
                        is not None
                        and read.tool_name == "artifact.read_candidate"
                    ),
                    *_lineage_candidate_refs(context.mission),
                }
            )
            if candidate_ref not in available:
                raise MissionAgentProtocolError(
                    "artifact.read_candidate candidate_ref must copy an exact internal candidate ref from "
                    "quality_reference_inventory; received="
                    f"{candidate_ref!r}, available={available[:8]}"
                )
        return
    if decision.kind is not MissionDecisionKind.QUALITY:
        return
    stage_id = decision.stage_id or context.mission.active_stage_id
    available_candidates = {
        str(item["ref"])
        for item in inventory["candidates"]
        if item.get("stage_id") == stage_id
        and item.get("mission_id") == context.mission.mission_id
    }
    candidate_refs = {
        str(value)
        for value in decision.payload_json.get("candidate_refs") or ()
    }
    if not candidate_refs:
        raise MissionAgentProtocolError(
            "quality_candidate_refs must contain a current-stage ref from "
            "quality_reference_inventory"
        )
    unavailable = sorted(candidate_refs - available_candidates)
    if unavailable:
        available = sorted(available_candidates)
        raise MissionAgentProtocolError(
            "quality_candidate_refs must copy current-stage refs from "
            "quality_reference_inventory; unavailable="
            f"{unavailable[:8]}, available={available[:8]}"
        )

    assessment = decision.payload_json.get("assessment")
    if not isinstance(assessment, dict):
        return
    declared_evidence = {
        str(item.get("evidence_id") or "")
        for item in assessment.get("evidence") or ()
        if isinstance(item, dict) and str(item.get("evidence_id") or "")
    }
    available_evidence = {
        str(item["ref"]): item
        for item in inventory["evidence"]
    }
    unavailable_evidence = sorted(declared_evidence - set(available_evidence))
    if unavailable_evidence:
        available = sorted(available_evidence)
        raise MissionAgentProtocolError(
            "quality_evidence.evidence_id must copy refs from "
            "quality_reference_inventory; unavailable="
            f"{unavailable_evidence[:8]}, available={available[:8]}"
        )
    invalid_surfaces: list[str] = []
    invalid_claim_scopes: list[str] = []
    seen_evidence_surfaces: set[tuple[str, str]] = set()
    for raw in assessment.get("evidence") or ():
        if not isinstance(raw, dict):
            continue
        evidence_id = str(raw.get("evidence_id") or "")
        surface = str(raw.get("surface") or "")
        pair = (evidence_id, surface)
        if pair in seen_evidence_surfaces:
            raise MissionAgentProtocolError(
                "quality_evidence cannot repeat the same evidence_id and surface"
            )
        seen_evidence_surfaces.add(pair)
        authority = available_evidence.get(evidence_id)
        if authority is None:
            continue
        allowed_surfaces = {str(value) for value in authority.get("surfaces") or ()}
        if surface not in allowed_surfaces:
            invalid_surfaces.append(
                f"{evidence_id}:{surface} (allowed={sorted(allowed_surfaces)})"
            )
            continue
        if surface == "claim_evidence_alignment":
            claim_ids = {
                str(value) for value in raw.get("claim_ids") or () if str(value)
            }
            supported_claims = {
                str(value)
                for value in authority.get("supported_claim_refs") or ()
                if str(value)
            }
            if not claim_ids or not claim_ids.issubset(supported_claims):
                invalid_claim_scopes.append(
                    f"{evidence_id}:claims={sorted(claim_ids)} "
                    f"(supported={sorted(supported_claims)})"
                )
    if invalid_surfaces:
        raise MissionAgentProtocolError(
            "quality_evidence.surface must copy an exact surface from "
            f"quality_reference_inventory; invalid={invalid_surfaces[:8]}"
        )
    if invalid_claim_scopes:
        raise MissionAgentProtocolError(
            "claim_evidence_alignment requires non-empty claim_ids listed in the "
            "evidence inventory; invalid="
            f"{invalid_claim_scopes[:8]}"
        )
    allowed_support = candidate_refs | declared_evidence
    used_support = {
        str(ref)
        for criterion in assessment.get("criterion_assessments") or ()
        if isinstance(criterion, dict)
        for ref in criterion.get("supporting_refs") or ()
    }
    invalid_support = sorted(used_support - allowed_support)
    if invalid_support:
        raise MissionAgentProtocolError(
            "criterion supporting_refs must be quality_candidate_refs or declared "
            f"quality_evidence.evidence_id values; invalid={invalid_support[:8]}"
        )


def _lineage_candidate_refs(mission: MissionRunPayload) -> set[str]:
    raw_lineage = mission.snapshot_json.get("mission_lineage")
    upstream = raw_lineage.get("upstream_refs") if isinstance(raw_lineage, dict) else None
    candidates = {
        str(item.get("target_ref") or "")
        for item in (upstream if isinstance(upstream, list) else ())
        if isinstance(item, dict)
    }
    return {ref for ref in candidates if is_internal_candidate_reference(ref)}


def _completed_immutable_read_operation(
    items: list[MissionItemPayload],
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    for hydrated in _hydrated_reference_reads(items):
        ref = str(hydrated["ref"] or "")
        read = canonical_reference_read(ref)
        if (
            read is not None
            and read.tool_name == tool_name
            and read.arguments == arguments
        ):
            return str(hydrated["operation_id"] or f"receipt:{ref}")
    terminal_operation_ids = {
        str(item.operation_id)
        for item in items
        if item.item_type == "tool_result"
        and item.phase.value == "completed"
        and item.operation_id
    }
    for item in reversed(items):
        if (
            item.item_type != "tool_call"
            or not item.operation_id
            or item.operation_id not in terminal_operation_ids
        ):
            continue
        payload = item.payload_json
        if (
            str(payload.get("tool_name") or "") == tool_name
            and payload.get("arguments") == arguments
        ):
            return item.operation_id
    return None


def _stage_id_is_pinned(
    stages: dict[str, Any],
    stage_id: str,
) -> bool:
    try:
        contracts = tuple(StageAcceptanceContract.model_validate(candidate) for candidate in stages.values())
        return any(stage_id_matches_contract(contract, stage_id) for contract in contracts)
    except ValidationError as exc:
        raise RuntimeError("Pinned stage contract is malformed") from exc


def _validate_decision_scope(
    decision: MissionAgentDecision,
    runtime: dict[str, Any],
) -> None:
    stages = runtime["stage_contracts"]
    if decision.stage_id is not None and not _stage_id_is_pinned(stages, decision.stage_id):
        raise MissionAgentProtocolError(f"Select a stage pinned by MissionPolicy; received {decision.stage_id}")
    if decision.kind is MissionDecisionKind.TOOL:
        tool_name = str(decision.payload_json.get("tool_name") or "")
        allowed = runtime["tool_policy"].get("allowed_tool_ids") or []
        if tool_name not in allowed:
            raise MissionAgentProtocolError(f"Select an allowed Mission tool; {tool_name} is outside the pinned policy")
    if decision.kind is MissionDecisionKind.QUALITY:
        candidate_refs = decision.payload_json.get("candidate_refs")
        if not isinstance(candidate_refs, list) or not candidate_refs or any(
            not isinstance(ref, str) or not is_internal_candidate_reference(ref)
            for ref in candidate_refs
        ):
            raise MissionAgentProtocolError("Quality requires verified artifact-candidate or academic-visual refs")
    if decision.kind is MissionDecisionKind.SUBAGENT:
        input_scope = decision.payload_json.get("input_scope")
        if not isinstance(input_scope, dict):
            raise MissionAgentProtocolError("Subagent input_scope must be an object")
        jobs = input_scope.get("jobs", [])
        if jobs and not isinstance(jobs, list):
            raise MissionAgentProtocolError("Subagent jobs must be a list")
        allowed_tools = set(runtime["tool_policy"].get("allowed_tool_ids") or [])
        skill_snapshots = runtime["worker_skill_snapshots"]
        allowed_skills = set(skill_snapshots)
        for job in jobs:
            if not isinstance(job, dict):
                raise MissionAgentProtocolError("Each subagent job must be an object")
            selected_refs = job.get("selected_refs") or []
            if not isinstance(selected_refs, list) or any(
                not isinstance(ref, str) or canonical_reference_read(ref) is None
                for ref in selected_refs
            ):
                raise MissionAgentProtocolError(
                    "Subagent selected_refs must be exact receipt-backed refs with a canonical reader"
                )
            if len(selected_refs) != len(set(selected_refs)):
                raise MissionAgentProtocolError(
                    "Subagent selected_refs must contain unique refs"
                )
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
                raise MissionAgentProtocolError("Subagent jobs cannot provide runtime-owned skill configuration: " + ", ".join(supplied))
            skill_id = str(job.get("worker_skill_id") or "")
            if not skill_id or skill_id not in allowed_skills:
                raise MissionAgentProtocolError("Subagent job must select a pinned WorkerSkill")
            snapshot = skill_snapshots.get(skill_id)
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("contract"), dict):
                raise RuntimeError("Pinned WorkerSkill snapshot is malformed")
            if not set(snapshot.get("allowed_tool_ids") or ()).issubset(allowed_tools):
                raise RuntimeError("Pinned WorkerSkill exceeds the Mission tool policy")
            skill_tools = set(snapshot.get("allowed_tool_ids") or ())
            unreadable = []
            for ref in selected_refs:
                read = canonical_reference_read(ref)
                if read is None or read.tool_name not in skill_tools:
                    unreadable.append(
                        f"{ref} (requires {read.tool_name if read else 'no canonical reader'})"
                    )
            if unreadable:
                raise MissionAgentProtocolError(
                    f"WorkerSkill {skill_id} cannot hydrate selected_refs: "
                    + ", ".join(unreadable)
                )


def _model_usage_receipt(response: Any, *, model_id: str) -> ModelUsageReceipt:
    usage = ModelUsage.from_provider_metadata(getattr(response, "usage_metadata", None))
    if usage is None or usage.total_tokens <= 0:
        raise MissionAgentUsageError(
            "Mission provider response did not include non-zero usage"
        )
    response_id = getattr(response, "id", None)
    return ModelUsageReceipt(
        model_id=model_id,
        usage=usage,
        provider_response_id=str(response_id) if response_id else None,
    )


__all__ = [
    "WorkspaceMissionLoopAgent",
    "mission_decision_tool",
    "parse_mission_decision",
]

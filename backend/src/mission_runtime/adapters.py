"""Concrete MissionStore-backed adapters for runtime ports and effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from copy import deepcopy
from time import monotonic
from typing import Any, Literal, Protocol, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from src.agents.harness.stage_acceptance import (
    can_start_stage,
    evaluate_stage_acceptance,
)
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    StageAcceptanceResult,
    StageAssessmentInput,
    StageProgressState,
)
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionItemDraftPayload,
    MissionItemPhase,
    MissionLeaseHeartbeatPayload,
    MissionOperationClaimPayload,
    MissionOperationFinishPayload,
    MissionOperationKind,
    MissionOperationStatus,
    MissionRunPatchPayload,
    MissionRunPayload,
    MissionSemanticReferencePayload,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    MISSION_MODEL_MAX_OUTPUT_TOKENS,
    MISSION_MODEL_REQUEST_TIMEOUT_SECONDS,
    MissionPauseRequest,
    MissionPortOutcome,
    MissionPortOutcomeStatus,
    StageQualityOutcome,
    StageQualityRequest,
    StageQualityVerdict,
    SubagentExecutionRequest,
    ToolExecutionRequest,
)
from src.mission_runtime.ports import MissionStorePort
from src.mission_runtime.reference_authority import canonical_reference_read
from src.models import create_chat_model
from src.models.provider_schema import parse_json_object, strict_provider_schema
from src.sandbox.base import (
    MissionLeaseGuard,
    SandboxReceiptClaim,
    SandboxReceiptState,
    SandboxReceiptStore,
)
from src.sandbox.contracts import (
    SandboxMissionProvenance,
    SandboxOperationRequest,
    SandboxOperationResult,
)
from src.subagent_runtime import SubagentRuntime, subagent_job_fingerprint
from src.subagent_runtime.contracts import (
    SUBAGENT_MIN_RUNTIME_CONTEXT_BYTES,
    SUBAGENT_MIN_RUNTIME_TOOL_STEPS,
    SubagentAction,
    SubagentBatchResult,
    SubagentBudget,
    SubagentContextRead,
    SubagentJobResult,
    SubagentJobSpec,
    SubagentModelOutputError,
    SubagentStatus,
    SubagentStep,
    SubagentStopReason,
    SubagentToolRequest,
    SubagentToolResult,
    subagent_context_size_bytes,
)
from src.subagent_runtime.runtime import (
    SubagentLedgerPort,
    SubagentModelPort,
    SubagentToolPort,
)
from src.tools.orchestrator import (
    MalformedToolArgumentsError,
    OperationJournal,
    ResearchToolOutcome,
    StaleToolLeaseError,
    ToolCallerKind,
    ToolErrorType,
    ToolInvocationContext,
    ToolLeaseFence,
    ToolOperation,
    ToolOrchestrator,
    ToolOutcomeStatus,
    ToolPolicy,
    UnknownToolError,
    VerificationStatus,
)


def _is_conflict(exc: BaseException) -> bool:
    return isinstance(exc, DataServiceClientError) and exc.status_code == 409


async def _append_under_current_lease(
    store: MissionStorePort,
    *,
    mission_id: str,
    lease_owner: str,
    lease_epoch: int,
    items: list[MissionItemDraftPayload],
    patch: MissionRunPatchPayload | None = None,
) -> MissionRunPayload:
    """Append after reloading the scalar fence; retry only same-lease conflicts.

    A Mission slice may run several isolated subagents concurrently. Their ledger
    entries legitimately race on ``state_version`` while sharing the same lease,
    so bounded retries need enough room and a small yield for another writer to
    finish. Lease-owner or epoch changes still fail immediately.
    """

    for attempt in range(16):
        mission = await store.get(mission_id)
        if mission is None:
            raise StaleToolLeaseError("mission no longer exists")
        if mission.lease_owner != lease_owner or mission.lease_epoch != lease_epoch:
            raise StaleToolLeaseError("mission lease fence is no longer current")
        try:
            result = await store.append_items(
                mission_id,
                MissionAppendPayload(
                    expected_state_version=mission.state_version,
                    lease_owner=lease_owner,
                    lease_epoch=lease_epoch,
                    items=items,
                    patch=patch or MissionRunPatchPayload(),
                ),
            )
            return result.mission
        except Exception as exc:
            if not _is_conflict(exc):
                raise
            await asyncio.sleep(min(0.002 * (2**attempt), 0.05))
    raise StaleToolLeaseError("mission state changed repeatedly while appending an effect receipt")


def _operation_request_hash(kind: MissionOperationKind, operation_key: str) -> str:
    return hashlib.sha256(f"{kind.value}:{operation_key}".encode()).hexdigest()


class MissionLeaseFenceAdapter(ToolLeaseFence, MissionLeaseGuard):
    def __init__(self, store: MissionStorePort, *, lease_ttl_seconds: int = 240) -> None:
        self.store = store
        self.lease_ttl_seconds = lease_ttl_seconds

    async def assert_current(self, value: ToolOperation | SandboxMissionProvenance) -> None:
        for _attempt in range(5):
            mission = await self.store.get(value.mission_id)
            if mission is None or mission.lease_epoch != value.lease_epoch or mission.lease_owner is None:
                raise StaleToolLeaseError("mission lease fence is stale")
            try:
                await self.store.heartbeat_lease(
                    mission.mission_id,
                    MissionLeaseHeartbeatPayload(
                        worker_id=mission.lease_owner,
                        lease_epoch=mission.lease_epoch,
                        expected_state_version=mission.state_version,
                        ttl_seconds=self.lease_ttl_seconds,
                    ),
                )
                return
            except DataServiceClientError as exc:
                if not _is_conflict(exc):
                    raise
        raise StaleToolLeaseError("mission lease fence changed repeatedly")


class MissionItemOperationJournal(OperationJournal):
    """Atomic receipt SSOT with MissionItems retained only as semantic ledger."""

    def __init__(
        self,
        store: MissionStorePort,
        *,
        operation_ttl_seconds: int,
    ) -> None:
        self.store = store
        self.operation_ttl_seconds = operation_ttl_seconds

    async def load_terminal(self, operation: ToolOperation) -> ResearchToolOutcome | None:
        return await self.load_terminal_for_mission(operation.mission_id, operation.operation_key)

    async def load_terminal_for_mission(self, mission_id: str, operation_key: str) -> ResearchToolOutcome | None:
        receipt = await self.store.get_operation(mission_id, operation_key)
        if receipt is None or receipt.status is MissionOperationStatus.CLAIMED:
            return None
        if receipt.kind is not MissionOperationKind.TOOL:
            raise RuntimeError("operation key belongs to a non-tool receipt")
        outcome = receipt.receipt_json.get("outcome")
        if not isinstance(outcome, dict):
            raise RuntimeError("terminal tool receipt is unknown or unavailable")
        return ResearchToolOutcome.model_validate(outcome)

    async def claim_started(self, operation: ToolOperation) -> bool:
        result = await self.store.claim_operation(
            operation.mission_id,
            MissionOperationClaimPayload(
                operation_key=operation.operation_key,
                kind=MissionOperationKind.TOOL,
                request_hash=_operation_request_hash(MissionOperationKind.TOOL, operation.operation_key),
                claimant=operation.operation_id,
                lease_epoch=operation.lease_epoch,
                ttl_seconds=self.operation_ttl_seconds,
            ),
        )
        return result.acquired

    async def record_terminal(self, operation: ToolOperation, outcome: ResearchToolOutcome) -> bool:
        await self.store.finish_operation(
            operation.mission_id,
            MissionOperationFinishPayload(
                operation_key=operation.operation_key,
                kind=MissionOperationKind.TOOL,
                request_hash=_operation_request_hash(MissionOperationKind.TOOL, operation.operation_key),
                claimant=operation.operation_id,
                lease_epoch=operation.lease_epoch,
                stage_id=operation.stage_id,
                producer=outcome.producer,
                status=(MissionOperationStatus.FAILED if outcome.status is ToolOutcomeStatus.ERROR else MissionOperationStatus.SUCCEEDED),
                receipt_json={"outcome": outcome.model_dump(mode="json")},
                payload_ref=outcome.payload_ref,
                references=list(_tool_semantic_references(outcome)),
            ),
        )
        return True


class ToolPolicyResolver(Protocol):
    async def resolve(
        self,
        mission: MissionRunPayload,
        *,
        caller_kind: ToolCallerKind,
        allowed_tools: tuple[str, ...] | None = None,
    ) -> ToolPolicy: ...


class StageContractResolver(Protocol):
    async def resolve(self, mission: MissionRunPayload, stage_id: str) -> StageAcceptanceContract: ...


class StageAssessmentBuilder(Protocol):
    async def build(
        self,
        request: StageQualityRequest,
        contract: StageAcceptanceContract,
    ) -> StageAssessmentInput: ...


class StageAcceptanceAdapter:
    """The only MissionRuntime stage progression verdict adapter."""

    def __init__(
        self,
        *,
        contracts: StageContractResolver,
        assessments: StageAssessmentBuilder,
    ) -> None:
        self.contracts = contracts
        self.assessments = assessments

    async def can_start(
        self,
        mission: MissionRunPayload,
        stage_id: str,
    ) -> tuple[bool, tuple[str, ...]]:
        contract = await self.contracts.resolve(mission, stage_id)
        total_items = _stage_total_items(mission, contract)
        if (
            contract.instantiation.mode == "per_item"
            and total_items is None
        ):
            source_key = contract.instantiation.source_context_key or "items"
            return False, (f"item_count:{source_key}",)
        return can_start_stage(
            contract,
            _latest_stage_results(mission.snapshot_json),
            sequence_index=_sequence_index(stage_id),
            total_items=total_items,
        )

    async def evaluate(self, request: StageQualityRequest) -> StageQualityOutcome:
        contract = await self.contracts.resolve(request.mission, request.stage_id)
        can_start, missing = await self.can_start(request.mission, request.stage_id)
        if not can_start:
            return StageQualityOutcome(
                verdict=StageQualityVerdict.REVISE,
                summary="Stage prerequisites have not passed",
                payload_json={"missing_prerequisite_stage_ids": list(missing)},
            )
        assessment = await self.assessments.build(request, contract)
        previous = _stage_progress(request.mission.snapshot_json, request.stage_id)
        result = evaluate_stage_acceptance(
            contract,
            assessment,
            previous_state=previous,
            total_items=_stage_total_items(request.mission, contract),
        )
        payload = result.to_mission_item_payload()
        if result.result == "pass":
            verdict = StageQualityVerdict.PASS
            summary = "Stage acceptance contract passed"
            pause = None
        elif result.result == "revise":
            verdict = StageQualityVerdict.REVISE
            summary = "Stage needs another focused revision"
            pause = None
        elif result.result == "ask_user":
            verdict = StageQualityVerdict.ASK_USER
            summary = "Stage needs user input before it can continue"
            pause = MissionPauseRequest(
                request_id=f"quality:{request.operation_id}",
                reason="user_input",
                summary=summary,
                pending_request={
                    "stage_id": request.stage_id,
                    "blocking_user_inputs": list(result.blocking_user_inputs),
                },
            )
        else:
            verdict = StageQualityVerdict.STOP
            summary = "Stage stopped after its revision or no-progress limit"
            pause = None
        return StageQualityOutcome(
            verdict=verdict,
            summary=summary,
            payload_json=payload,
            pause_request=pause,
        )


class MissionToolOrchestratorAdapter:
    def __init__(
        self,
        *,
        orchestrator: ToolOrchestrator,
        policy_resolver: ToolPolicyResolver,
    ) -> None:
        self.orchestrator = orchestrator
        self.policy_resolver = policy_resolver

    async def execute(self, request: ToolExecutionRequest) -> MissionPortOutcome:
        try:
            policy = await self.policy_resolver.resolve(request.mission, caller_kind=ToolCallerKind.WORKSPACE_AGENT)
            outcome = await self.orchestrator.invoke(
                request.tool_name,
                request.arguments,
                context=ToolInvocationContext(
                    mission_id=request.mission.mission_id,
                    workspace_id=request.mission.workspace_id,
                    command_id=request.operation_id,
                    stage_id=request.stage_id or "mission",
                    caller_id="workspace_agent",
                    caller_kind=ToolCallerKind.WORKSPACE_AGENT,
                    lease_epoch=request.mission.lease_epoch,
                    model_id=request.mission.model_id,
                ),
                policy=policy,
            )
        except (UnknownToolError, MalformedToolArgumentsError) as exc:
            return MissionPortOutcome(
                status=MissionPortOutcomeStatus.FAILED,
                summary=str(exc),
                payload_json={"error_type": type(exc).__name__, "tool_name": request.tool_name},
            )
        return _mission_tool_outcome(outcome)


class MissionSubagentToolAdapter(SubagentToolPort):
    def __init__(self, *, store: MissionStorePort, orchestrator: ToolOrchestrator, policy_resolver: ToolPolicyResolver) -> None:
        self.store = store
        self.orchestrator = orchestrator
        self.policy_resolver = policy_resolver

    def input_schemas(self, tool_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        """Project canonical catalog schemas into the bounded worker context."""
        return {tool_id: self.orchestrator.catalog.require(tool_id).input_model.model_json_schema(mode="validation") for tool_id in tool_ids}

    async def execute(self, request: SubagentToolRequest) -> SubagentToolResult:
        mission = await self.store.get(request.mission_id)
        if mission is None:
            raise StaleToolLeaseError("mission no longer exists")
        policy = await self.policy_resolver.resolve(
            mission,
            caller_kind=ToolCallerKind.SUBAGENT,
            allowed_tools=(request.tool_name,),
        )
        try:
            outcome = await self.orchestrator.invoke(
                request.tool_name,
                request.arguments,
                context=ToolInvocationContext(
                    mission_id=request.mission_id,
                    workspace_id=request.workspace_id,
                    command_id=f"{request.operation_id}:{request.job_id}",
                    stage_id=request.stage_id or "mission",
                    caller_id=request.job_id,
                    caller_kind=ToolCallerKind.SUBAGENT,
                    lease_epoch=request.lease_epoch,
                    model_id=mission.model_id,
                ),
                policy=policy,
            )
        except (MalformedToolArgumentsError, UnknownToolError) as exc:
            return SubagentToolResult(
                status="failed",
                summary=str(exc),
                error_type=(ToolErrorType.MALFORMED_TOOL_ARGUMENTS.value if isinstance(exc, MalformedToolArgumentsError) else ToolErrorType.TOOL_UNAVAILABLE.value),
            )
        return SubagentToolResult(
            status=("failed" if outcome.status is ToolOutcomeStatus.ERROR else "completed"),
            summary=outcome.summary,
            payload_json=outcome.model_dump(mode="json"),
            payload_ref=outcome.payload_ref,
            evidence_refs=tuple(ref.ref_id for ref in outcome.evidence_refs),
            artifact_refs=tuple(ref.ref_id for ref in outcome.artifact_refs),
            recoverable=outcome.recoverable_by_model,
            error_type=outcome.error_type.value if outcome.error_type else None,
        )


class MissionSubagentLedger(SubagentLedgerPort):
    def __init__(self, store: MissionStorePort) -> None:
        self.store = store

    async def record_progress(
        self,
        job: SubagentJobSpec,
        *,
        phase: str,
        summary: str,
        payload_json: dict[str, object] | None = None,
    ) -> None:
        await _append_under_current_lease(
            self.store,
            mission_id=job.mission_id,
            lease_owner=job.lease_owner,
            lease_epoch=job.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="subagent_progress",
                    operation_id=job.operation_id,
                    phase=(MissionItemPhase.COMPLETED if phase == "terminal" else MissionItemPhase.PROGRESS),
                    stage_id=job.stage_id,
                    producer=job.job_id,
                    summary=summary,
                    payload_json={
                        "job_id": job.job_id,
                        "display_name": job.display_name,
                        "role_label": job.role_label,
                        "lifecycle_phase": phase,
                        **(payload_json or {}),
                    },
                )
            ],
        )


class LangChainSubagentModel(SubagentModelPort):
    """Strict structured-action model; tool execution remains outside LangChain."""

    async def next_action(
        self,
        job: SubagentJobSpec,
        steps: tuple[SubagentStep, ...],
        tool_results: tuple[SubagentToolResult, ...],
    ) -> SubagentAction:
        model = create_chat_model(
            job.model_id,
            reasoning_effort=job.reasoning_effort,
            request_timeout=MISSION_MODEL_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
            max_output_tokens=MISSION_MODEL_MAX_OUTPUT_TOKENS,
        )
        bound = model.bind_tools(
            _subagent_action_tools(job.output_schema, tool_results=tool_results),
            tool_choice="required",
            strict=True,
        )
        system = (
            "You are a bounded research worker inside Wenjin. Work only on the assigned task. "
            "Use only allowed tools. Never request room, memory, review, or mission writes. "
            "Construct tool arguments from tool_input_schemas exactly. selected_refs in context_reads are loaded "
            "by the runtime before your first turn; use their authoritative tool_results and do not read them again. "
            "If a selected sandbox artifact page reports truncated=true, continue with sandbox.read_artifact at "
            "the exact next_offset until the final page before completing an audit. "
            "When asked for an optional audit, inspect every selected artifact candidate through the hydrated "
            "artifact.read_candidate result before reporting findings. The audit informs repair; it never grants "
            "stage acceptance or creates a user review decision. "
            "A completed tool result's payload_json is the authoritative returned content. Never repeat the same "
            "tool with the same arguments after it completed; reuse that result and complete on the next turn once "
            "the exit criteria are met. "
            "Choose exactly one action frame: subagent_use_tool, subagent_complete, or subagent_stop. "
            "Use subagent_complete only when the exit criteria are met and populate its native result_json object "
            "to the pinned output schema exactly. Reference fields are enum-bound to exact receipts from this "
            "worker loop; select those values without copying or modifying them. Otherwise use a tool or stop "
            "with an explicit reason. When artifact_refs requires at least one item, use an allowed staging tool "
            "to create the complete deliverable before completing, then return its exact artifact ref. Never place "
            "a full deliverable in result_json as a substitute for a staged artifact. "
            "Do not reveal hidden reasoning. Your user-facing name is a short label, not an identity or authority claim."
        )
        payload = {
            "objective": job.objective,
            "task": job.task_summary,
            "role": job.role_label,
            "input_scope": job.input_scope,
            "mission_context_checkpoint": job.context_checkpoint,
            "selected_refs": job.selected_refs,
            "context_reads": [item.model_dump(mode="json") for item in job.context_reads],
            "prior_output_briefs": job.prior_output_briefs,
            "allowed_tools": job.allowed_tools,
            "tool_input_schemas": job.tool_input_schemas,
            "worker_skill": job.worker_skill,
            "output_schema": job.output_schema,
            "exit_criteria": job.exit_criteria,
            "steps": [item.model_dump(mode="json") for item in steps[-12:]],
            "tool_results": [item.model_dump(mode="json") for item in tool_results[-8:]],
            "allowed_result_refs": {
                "evidence_refs": list(
                    dict.fromkeys(
                        ref
                        for item in tool_results
                        for ref in item.evidence_refs
                    )
                ),
                "artifact_refs": list(
                    dict.fromkeys(
                        ref
                        for item in tool_results
                        for ref in item.artifact_refs
                    )
                ),
            },
        }
        result = await bound.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        try:
            return _parse_subagent_action(result)
        except ValueError as exc:
            raise SubagentModelOutputError(_subagent_output_diagnostic(exc)) from exc


def _selected_ref_context_reads(
    selected_refs: tuple[str, ...],
    allowed_tools: tuple[str, ...],
) -> tuple[SubagentContextRead, ...]:
    """Project every selected ref into deterministic, authorized context hydration."""

    projected: list[SubagentContextRead] = []
    unreadable: list[str] = []
    allowed = set(allowed_tools)
    for ref in selected_refs:
        read = canonical_reference_read(ref)
        if read is not None and read.tool_name in allowed:
            projected.append(
                SubagentContextRead(
                    ref=ref,
                    tool_name=read.tool_name,
                    arguments=read.arguments,
                )
            )
            continue
        unreadable.append(ref)
    if unreadable:
        raise ValueError("selected_refs are not readable by the chosen WorkerSkill tools: " + ", ".join(unreadable))
    return tuple(projected)


class _ProviderSubagentToolAction(BaseModel):
    """Strict provider wire shape for a canonical tool request."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4000)
    tool_name: str = Field(min_length=1, max_length=160)
    arguments_json: str
    partial_result_json: str

    def to_domain(self) -> SubagentAction:
        return SubagentAction(
            kind="tool",
            summary=self.summary,
            tool_name=self.tool_name,
            arguments=parse_json_object(self.arguments_json, field_name="arguments_json"),
            partial_result_json=parse_json_object(
                self.partial_result_json,
                field_name="partial_result_json",
            ),
        )


class _ProviderSubagentCompleteAction(BaseModel):
    """Provider wire shape whose result object is specialized per WorkerSkill."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4000)
    result_json: dict[str, Any]

    def to_domain(self) -> SubagentAction:
        return SubagentAction(
            kind="complete",
            summary=self.summary,
            result_json=self.result_json,
        )


class _ProviderSubagentStopAction(BaseModel):
    """Strict provider wire shape for an honest bounded stop."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4000)
    partial_result_json: str
    stop_reason: SubagentStopReason

    def to_domain(self) -> SubagentAction:
        return SubagentAction(
            kind="stop",
            summary=self.summary,
            partial_result_json=parse_json_object(
                self.partial_result_json,
                field_name="partial_result_json",
            ),
            stop_reason=self.stop_reason,
        )


def _subagent_action_tools(
    output_schema: dict[str, Any],
    *,
    tool_results: tuple[SubagentToolResult, ...] = (),
) -> list[dict[str, Any]]:
    complete_schema = _ProviderSubagentCompleteAction.model_json_schema()
    result_schema = deepcopy(output_schema)
    if not result_schema:
        result_schema = {"type": "object", "properties": {}}
    _bind_subagent_result_refs(
        result_schema,
        evidence_refs=tuple(
            dict.fromkeys(
                ref
                for item in tool_results
                for ref in item.evidence_refs
            )
        ),
        artifact_refs=tuple(
            dict.fromkeys(
                ref
                for item in tool_results
                for ref in item.artifact_refs
            )
        ),
    )
    complete_schema["properties"]["result_json"] = result_schema
    definitions = (
        (
            "subagent_use_tool",
            "Use one allowed canonical tool. Encode open JSON arguments as strings and use '{}' for an empty partial result.",
            _ProviderSubagentToolAction.model_json_schema(),
        ),
        (
            "subagent_complete",
            "Complete the assigned worker task with a result matching the pinned WorkerSkill output contract.",
            complete_schema,
        ),
        (
            "subagent_stop",
            "Stop honestly when the bounded task cannot be completed. Encode an open partial result as a JSON string.",
            _ProviderSubagentStopAction.model_json_schema(),
        ),
    )
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": strict_provider_schema(schema),
                "strict": True,
            },
        }
        for name, description, schema in definitions
    ]


def _bind_subagent_result_refs(
    schema: dict[str, Any],
    *,
    evidence_refs: tuple[str, ...],
    artifact_refs: tuple[str, ...],
) -> None:
    refs_by_field = {
        "evidence_refs": evidence_refs,
        "artifact_refs": artifact_refs,
    }

    def visit(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for field, refs in refs_by_field.items():
                    field_schema = properties.get(field)
                    if not isinstance(field_schema, dict):
                        continue
                    field_schema["items"] = {
                        "type": "string",
                        "enum": list(refs) if refs else [""],
                    }
                    if refs:
                        field_schema.pop("maxItems", None)
                    else:
                        field_schema["maxItems"] = 0
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)


def _parse_subagent_action(message: AIMessage) -> SubagentAction:
    calls = message.tool_calls
    if len(calls) != 1:
        raise ValueError("exactly_one_action_frame_required")
    name = str(calls[0].get("name") or "")
    arguments = calls[0].get("args")
    if not isinstance(arguments, dict):
        raise ValueError("action_arguments_must_be_an_object")
    if name == "subagent_use_tool":
        return _ProviderSubagentToolAction.model_validate(arguments).to_domain()
    if name == "subagent_complete":
        return _ProviderSubagentCompleteAction.model_validate(arguments).to_domain()
    if name == "subagent_stop":
        return _ProviderSubagentStopAction.model_validate(arguments).to_domain()
    raise ValueError("unknown_subagent_action_frame")


def _subagent_output_diagnostic(exc: ValueError) -> str:
    message = str(exc)
    if "result_json" in message:
        return "result_json must match the pinned output contract exactly"
    if "arguments_json" in message:
        return "arguments_json must be one valid JSON object"
    if "partial_result_json" in message:
        return "partial_result_json must be one valid JSON object, or '{}' when empty"
    if message in {
        "exactly_one_action_frame_required",
        "action_arguments_must_be_an_object",
        "unknown_subagent_action_frame",
    }:
        return message
    return "use exactly one required subagent action tool and satisfy every required field"


class MissionSubagentRuntimeAdapter:
    def __init__(
        self,
        *,
        store: MissionStorePort,
        model: SubagentModelPort,
        tools: MissionSubagentToolAdapter,
        max_concurrency: int = 4,
        max_jobs_per_batch: int = 8,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self.store = store
        self.tools = tools
        self.runtime = SubagentRuntime(
            model=model,
            tools=tools,
            ledger=MissionSubagentLedger(store),
            max_concurrency=max_concurrency,
            max_jobs_per_batch=max_jobs_per_batch,
            monotonic_clock=monotonic_clock,
        )

    async def run(self, request: SubagentExecutionRequest) -> MissionPortOutcome:
        jobs = _subagent_jobs(
            request,
            input_schema_resolver=self.tools.input_schemas,
        )
        recovered = await self._recovered_results(request, jobs)
        missing = tuple(job for job in jobs if job.job_id not in recovered)
        if missing:
            fresh = await self.runtime.run_batch(
                missing,
                deadline_monotonic=request.deadline_monotonic,
            )
            recovered.update({item.job_id: item for item in fresh.results})
        result = SubagentBatchResult(
            operation_id=request.operation_id,
            results=tuple(recovered[job.job_id] for job in jobs),
        )
        return _subagent_port_outcome(result)

    async def _recovered_results(
        self,
        request: SubagentExecutionRequest,
        jobs: tuple[SubagentJobSpec, ...],
    ) -> dict[str, SubagentJobResult]:
        items = await self.store.list_items(
            request.mission.mission_id,
            item_type="subagent_progress",
            operation_id=request.operation_id,
            limit=100,
        )
        expected = {job.job_id: job for job in jobs}
        recovered: dict[str, SubagentJobResult] = {}
        for item in items:
            payload = item.payload_json
            if payload.get("lifecycle_phase") != "terminal":
                continue
            job_id = str(payload.get("job_id") or "")
            job = expected.get(job_id)
            raw_result = payload.get("result")
            if job is None or not isinstance(raw_result, dict):
                continue
            if payload.get("job_fingerprint") != subagent_job_fingerprint(job):
                raise RuntimeError("durable subagent terminal result has a divergent semantic request")
            result = SubagentJobResult.model_validate(raw_result)
            if result.result_sha256 != payload.get("result_sha256"):
                raise RuntimeError("durable subagent terminal result hash does not match")
            recovered[job_id] = result
        return recovered


class MissionSandboxReceiptStore(SandboxReceiptStore):
    """Atomic operation receipt store used by production SandboxRuntime."""

    def __init__(self, store: MissionStorePort) -> None:
        self.store = store

    async def claim(self, request: SandboxOperationRequest, *, sandbox_job_id: str) -> SandboxReceiptClaim:
        result = await self.store.claim_operation(
            request.provenance.mission_id,
            MissionOperationClaimPayload(
                operation_key=request.operation_key,
                kind=MissionOperationKind.SANDBOX,
                request_hash=_operation_request_hash(MissionOperationKind.SANDBOX, request.operation_key),
                claimant=sandbox_job_id,
                lease_epoch=request.provenance.lease_epoch,
                ttl_seconds=request.limits.wall_time_seconds + 30,
            ),
        )
        receipt = result.receipt
        if receipt.status is not MissionOperationStatus.CLAIMED:
            existing = self._sandbox_result(receipt.receipt_json)
            if existing is None:
                return SandboxReceiptClaim(
                    state=SandboxReceiptState.CLAIMED,
                    acquired=False,
                    claimed_at=receipt.claimed_at,
                )
            return SandboxReceiptClaim(
                state=SandboxReceiptState.TERMINAL,
                acquired=False,
                existing_result=existing,
            )
        if not result.acquired:
            return SandboxReceiptClaim(
                state=SandboxReceiptState.CLAIMED,
                acquired=False,
                claimed_at=receipt.claimed_at,
            )
        return SandboxReceiptClaim(
            state=SandboxReceiptState.CLAIMED,
            acquired=True,
            claimed_at=receipt.claimed_at,
        )

    async def finalize(self, result: SandboxOperationResult) -> None:
        receipt = await self.store.get_operation(result.provenance.mission_id, result.operation_key)
        if receipt is None:
            raise RuntimeError("sandbox operation was not atomically claimed")
        await self.store.finish_operation(
            result.provenance.mission_id,
            MissionOperationFinishPayload(
                operation_key=result.operation_key,
                kind=MissionOperationKind.SANDBOX,
                request_hash=_operation_request_hash(MissionOperationKind.SANDBOX, result.operation_key),
                claimant=receipt.claimant,
                lease_epoch=result.provenance.lease_epoch,
                producer=result.provenance.subagent_id or "workspace_agent",
                status=(MissionOperationStatus.SUCCEEDED if result.status.value == "succeeded" else MissionOperationStatus.FAILED),
                receipt_json={"result": result.model_dump(mode="json")},
            ),
        )

    async def get(
        self,
        mission_id: str,
        operation_key: str,
    ) -> SandboxOperationResult | None:
        return await self._get_for_mission(mission_id, operation_key)

    async def _get_for_mission(self, mission_id: str, operation_key: str) -> SandboxOperationResult | None:
        receipt = await self.store.get_operation(mission_id, operation_key)
        return self._sandbox_result(receipt.receipt_json) if receipt is not None else None

    @staticmethod
    def _sandbox_result(receipt_json: dict[str, Any]) -> SandboxOperationResult | None:
        value = receipt_json.get("result")
        return SandboxOperationResult.model_validate(value) if isinstance(value, dict) else None

    async def inspect(
        self,
        mission_id: str,
        operation_key: str,
    ) -> SandboxReceiptClaim | None:
        receipt = await self.store.get_operation(mission_id, operation_key)
        if receipt is None:
            return None
        terminal = self._sandbox_result(receipt.receipt_json)
        if terminal is not None:
            return SandboxReceiptClaim(
                state=SandboxReceiptState.TERMINAL,
                acquired=False,
                existing_result=terminal,
            )
        return SandboxReceiptClaim(
            state=SandboxReceiptState.CLAIMED,
            acquired=False,
            claimed_at=receipt.claimed_at,
        )


def _subagent_jobs(
    request: SubagentExecutionRequest,
    *,
    input_schema_resolver: Callable[[tuple[str, ...]], dict[str, dict[str, Any]]],
) -> tuple[SubagentJobSpec, ...]:
    raw_jobs = request.input_scope.get("jobs")
    entries = raw_jobs if isinstance(raw_jobs, list) and raw_jobs else [request.input_scope]
    jobs: list[SubagentJobSpec] = []
    lease_owner = request.mission.lease_owner
    if lease_owner is None:
        raise StaleToolLeaseError("subagent requires a current parent lease")
    skill_snapshots = request.mission.runtime_context_json.get("worker_skill_snapshots")
    if not isinstance(skill_snapshots, dict):
        raise ValueError("subagent requires pinned WorkerSkill snapshots")
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError("subagent jobs must be objects")
        task = str(raw.get("task_summary") or request.task_summary).strip()
        role = str(raw.get("role_label") or "研究协作者").strip()
        display = str(raw.get("display_name") or "").strip()
        if not display:
            raise ValueError("main agent must provide a display_name for every subagent job")
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
        supplied = sorted(forbidden.intersection(raw))
        if supplied:
            raise ValueError("subagent job cannot override pinned WorkerSkill configuration: " + ", ".join(supplied))
        skill_id = str(raw.get("worker_skill_id") or "").strip()
        snapshot = skill_snapshots.get(skill_id)
        if not skill_id or not isinstance(snapshot, dict):
            raise ValueError("subagent job must select one pinned worker_skill_id")
        skill_contract = snapshot.get("contract")
        if not isinstance(skill_contract, dict) or str(skill_contract.get("id") or "") != skill_id:
            raise ValueError("pinned WorkerSkill contract is invalid")
        allowed_tools = tuple(str(item) for item in snapshot.get("allowed_tool_ids") or ())
        mission_tool_policy = request.mission.runtime_context_json.get("tool_policy")
        if not isinstance(mission_tool_policy, dict):
            raise ValueError("subagent requires a pinned Mission tool policy")
        mission_tools = set(mission_tool_policy.get("allowed_tool_ids", ()))
        if not set(allowed_tools).issubset(mission_tools):
            raise ValueError("pinned WorkerSkill tools exceed the Mission tool policy")
        digest = hashlib.sha256(f"{request.operation_id}:{index}:{task}".encode()).hexdigest()[:20]
        selected_refs = tuple(str(item) for item in raw.get("selected_refs", ()))
        job_values = {
            "job_id": f"sj_{digest}",
            "operation_id": request.operation_id,
            "mission_id": request.mission.mission_id,
            "workspace_id": request.mission.workspace_id,
            "model_id": request.mission.model_id,
            "reasoning_effort": request.mission.reasoning_effort,
            "lease_owner": lease_owner,
            "lease_epoch": request.mission.lease_epoch,
            "stage_id": request.stage_id,
            "display_name": display,
            "role_label": role,
            "task_summary": task,
            "objective": request.mission.objective,
            "input_scope": {
                key: value
                for key, value in raw.items()
                if key
                not in {
                    "jobs",
                    "budget",
                    "display_name",
                    "role_label",
                    "allowed_tools",
                    "worker_skill",
                    "worker_skill_id",
                    "output_schema",
                    "exit_criteria",
                    "selected_refs",
                    "model_id",
                }
            },
            "context_checkpoint_ref": request.frozen_context.context_checkpoint_ref,
            "context_checkpoint": dict(request.frozen_context.context_checkpoint),
            "selected_refs": selected_refs,
            "context_reads": tuple(
                item.model_dump(mode="json")
                for item in _selected_ref_context_reads(
                    selected_refs,
                    allowed_tools,
                )
            ),
            "prior_output_briefs": request.frozen_context.prior_output_briefs,
            "allowed_tools": allowed_tools,
            "tool_input_schemas": input_schema_resolver(allowed_tools),
            "worker_skill": dict(skill_contract),
            "output_schema": dict(skill_contract.get("output_contract") or {}),
            "exit_criteria": tuple(str(item) for item in skill_contract.get("quality_focus") or ()),
            "depth": 1,
        }
        budget_raw = dict(raw.get("budget")) if isinstance(raw.get("budget"), dict) else {}
        budget_raw["max_tool_steps"] = max(
            SUBAGENT_MIN_RUNTIME_TOOL_STEPS,
            int(budget_raw.get("max_tool_steps") or 0),
            len(job_values["context_reads"]),
        )
        budget_raw["max_context_bytes"] = max(
            SUBAGENT_MIN_RUNTIME_CONTEXT_BYTES,
            int(budget_raw.get("max_context_bytes") or 0),
            subagent_context_size_bytes(job_values),
        )
        jobs.append(
            SubagentJobSpec(
                **job_values,
                budget=SubagentBudget.model_validate(budget_raw),
            )
        )
    return tuple(jobs)


def _latest_stage_results(snapshot: dict[str, Any]) -> dict[str, StageAcceptanceResult]:
    raw = snapshot.get("stage_acceptance")
    if not isinstance(raw, dict):
        return {}
    results: dict[str, StageAcceptanceResult] = {}
    for stage_id, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            results[str(stage_id)] = StageAcceptanceResult.model_validate(value)
        except ValueError:
            continue
    return results


def _stage_progress(snapshot: dict[str, Any], stage_id: str) -> StageProgressState:
    result = _latest_stage_results(snapshot).get(stage_id)
    return result.progress_state if result is not None else StageProgressState()


def _sequence_index(stage_id: str) -> int | None:
    match = re.search(r"(?:^|[._-])(\d+)(?:[._-]|$)", stage_id)
    return int(match.group(1)) if match else None


def _stage_total_items(
    mission: MissionRunPayload,
    contract: StageAcceptanceContract,
) -> int | None:
    source_keys: set[str] = set()
    if contract.instantiation.source_context_key:
        source_keys.add(contract.instantiation.source_context_key)
    if contract.all_item_prerequisite_templates:
        raw_contracts = mission.runtime_context_json.get("stage_contracts")
        if not isinstance(raw_contracts, dict):
            raise ValueError("all-item prerequisites require pinned stage contracts")
        for template in contract.all_item_prerequisite_templates:
            matching_keys = {
                str(instantiation.get("source_context_key"))
                for raw_contract in raw_contracts.values()
                if isinstance(raw_contract, dict)
                and isinstance((instantiation := raw_contract.get("instantiation")), dict)
                and instantiation.get("mode") == "per_item"
                and instantiation.get("instance_id_template") == template
                and instantiation.get("source_context_key")
            }
            if len(matching_keys) != 1:
                raise ValueError(
                    f"all-item prerequisite template {template} must resolve to one item-count source"
                )
            source_keys.update(matching_keys)
    if len(source_keys) > 1:
        raise ValueError("stage prerequisite families use different item-count sources")
    source_key = next(iter(source_keys), None)
    if not source_key:
        return None
    raw_counts = mission.snapshot_json.get("stage_item_counts")
    if not isinstance(raw_counts, dict):
        return None
    value = raw_counts.get(source_key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 100 else None


def _mission_tool_outcome(outcome: ResearchToolOutcome) -> MissionPortOutcome:
    return MissionPortOutcome(
        status=(MissionPortOutcomeStatus.FAILED if outcome.status is ToolOutcomeStatus.ERROR else MissionPortOutcomeStatus.COMPLETED),
        summary=outcome.summary or "Tool operation completed",
        payload_json={"research_tool_outcome": outcome.model_dump(mode="json")},
        payload_ref=outcome.payload_ref,
        risk_level=(cast(Literal["low", "medium", "high"], outcome.risk_level) if outcome.risk_level in {"low", "medium", "high"} else None),
    )


def _tool_semantic_references(
    outcome: ResearchToolOutcome,
) -> tuple[MissionSemanticReferencePayload, ...]:
    verified = outcome.verification_status in {
        VerificationStatus.PROVIDER_RECEIPT,
        VerificationStatus.VERIFIED,
    }
    references: list[MissionSemanticReferencePayload] = []
    seen: set[tuple[str, str]] = set()

    def add(reference: MissionSemanticReferencePayload) -> None:
        key = (reference.category, reference.reference_id)
        if key not in seen:
            seen.add(key)
            references.append(reference)

    for source in outcome.source_refs:
        add(
            MissionSemanticReferencePayload(
                category="evidence",
                reference_id=source.source_id,
                reference_kind="web_source",
                title=source.title,
                uri=source.canonical_url,
                source_type="web_page",
                verified=source.verification_status
                in {
                    VerificationStatus.PROVIDER_RECEIPT,
                    VerificationStatus.VERIFIED,
                },
                metadata={
                    "publisher": source.publisher,
                    "authors": list(source.authors),
                    "observed_at": source.observed_at.isoformat(),
                    "content_hash": source.content_hash,
                    "supported_claim_refs": list(source.supported_claim_refs),
                    "verification_status": source.verification_status.value,
                },
            )
        )
    for ref in outcome.evidence_refs:
        if ref.kind in {
            "evidence_gap",
            "mission_review_candidate",
            "provider_search_receipt",
        }:
            continue
        add(
            MissionSemanticReferencePayload(
                category="evidence",
                reference_id=ref.ref_id,
                reference_kind=ref.kind,
                title=ref.title,
                uri=ref.uri,
                source_type=_evidence_source_type(ref.kind),
                verified=verified,
                metadata=_durable_reference_metadata(ref.metadata),
            )
        )
    for ref in outcome.artifact_refs:
        add(
            MissionSemanticReferencePayload(
                category="artifact",
                reference_id=ref.ref_id,
                reference_kind=ref.kind,
                title=ref.title,
                uri=ref.uri,
                verified=verified,
                metadata=_durable_reference_metadata(ref.metadata),
            )
        )
    return tuple(references)


_TRANSIENT_REFERENCE_METADATA_KEYS = frozenset(
    {
        "content",
        "content_chunks",
        "preview",
        "preview_body_chunks",
        "sandbox_artifacts",
        "verified_inline",
    }
)


def _durable_reference_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Remove invocation-only payloads from durable semantic projections."""

    def compact(node: Any) -> Any:
        if isinstance(node, dict):
            return {str(key): compact(item) for key, item in node.items() if str(key) not in _TRANSIENT_REFERENCE_METADATA_KEYS}
        if isinstance(node, list | tuple):
            return [compact(item) for item in node]
        return node

    return cast(dict[str, Any], compact(value))


def _evidence_source_type(reference_kind: str) -> Literal["paper", "web_page", "dataset", "upload"]:
    normalized = reference_kind.lower()
    if "dataset" in normalized or "sandbox" in normalized:
        return "dataset"
    if "web" in normalized or "search" in normalized:
        return "web_page"
    if "paper" in normalized or "publication" in normalized:
        return "paper"
    return "upload"


def _subagent_port_outcome(batch: SubagentBatchResult) -> MissionPortOutcome:
    failed = [item for item in batch.results if item.status is SubagentStatus.FAILED]
    useful = [item for item in batch.results if item.status is SubagentStatus.COMPLETED or item.partial_result_available]
    status = MissionPortOutcomeStatus.COMPLETED if useful else MissionPortOutcomeStatus.FAILED
    summary = f"{len(useful)} of {len(batch.results)} subagent jobs produced usable results"
    return MissionPortOutcome(
        status=status,
        summary=summary,
        payload_json={
            "jobs": [item.model_dump(mode="json") for item in batch.results],
            "failed_job_ids": [item.job_id for item in failed],
        },
        snapshot_patch={
            "subagent_summary": {
                "active": 0,
                "latest": [
                    {
                        "job_id": item.job_id,
                        "display_name": item.display_name,
                        "role_label": item.role_label,
                        "status": item.status.value,
                        "stop_reason": item.stop_reason.value,
                        "result_brief": item.result_brief,
                    }
                    for item in batch.results
                ],
            }
        },
    )


__all__ = [
    "LangChainSubagentModel",
    "MissionItemOperationJournal",
    "MissionLeaseFenceAdapter",
    "MissionSandboxReceiptStore",
    "MissionSubagentRuntimeAdapter",
    "MissionToolOrchestratorAdapter",
    "StageAcceptanceAdapter",
    "StageAssessmentBuilder",
    "StageContractResolver",
    "ToolPolicyResolver",
]

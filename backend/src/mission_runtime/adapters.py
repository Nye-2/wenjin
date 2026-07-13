"""Concrete MissionStore-backed adapters for runtime ports and effects."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
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
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
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
    SubagentAction,
    SubagentBatchResult,
    SubagentBudget,
    SubagentJobResult,
    SubagentJobSpec,
    SubagentStatus,
    SubagentStep,
    SubagentStopReason,
    SubagentToolRequest,
    SubagentToolResult,
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
    """Append after reloading the scalar fence; retry only same-lease conflicts."""

    for _attempt in range(3):
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
    raise StaleToolLeaseError("mission state changed repeatedly while appending an effect receipt")


def _operation_request_hash(kind: MissionOperationKind, operation_key: str) -> str:
    return hashlib.sha256(f"{kind.value}:{operation_key}".encode()).hexdigest()


class MissionLeaseFenceAdapter(ToolLeaseFence, MissionLeaseGuard):
    def __init__(self, store: MissionStorePort, *, lease_ttl_seconds: int = 240) -> None:
        self.store = store
        self.lease_ttl_seconds = lease_ttl_seconds

    async def assert_current(self, value: ToolOperation | SandboxMissionProvenance) -> None:
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
        except DataServiceClientError as exc:
            if _is_conflict(exc):
                raise StaleToolLeaseError("mission lease fence is stale") from exc
            raise


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
                request_hash=_operation_request_hash(
                    MissionOperationKind.TOOL, operation.operation_key
                ),
                claimant=operation.operation_id,
                lease_epoch=operation.lease_epoch,
                ttl_seconds=self.operation_ttl_seconds,
            ),
        )
        if not result.acquired:
            return False
        await _append_under_current_lease(
            self.store,
            mission_id=operation.mission_id,
            lease_owner=await _lease_owner(self.store, operation),
            lease_epoch=operation.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="tool_operation_started",
                    operation_id=operation.operation_id,
                    phase=MissionItemPhase.STARTED,
                    stage_id=operation.stage_id,
                    producer="tool_orchestrator",
                    summary=f"Tool operation started: {operation.tool_id}",
                    payload_json={
                        "operation_key": operation.operation_key,
                        "tool_id": operation.tool_id,
                        "caller_id": operation.caller_id,
                        "caller_kind": operation.caller_kind.value,
                    },
                )
            ],
        )
        return True

    async def record_terminal(self, operation: ToolOperation, outcome: ResearchToolOutcome) -> bool:
        finished = await self.store.finish_operation(
            operation.mission_id,
            MissionOperationFinishPayload(
                operation_key=operation.operation_key,
                kind=MissionOperationKind.TOOL,
                request_hash=_operation_request_hash(
                    MissionOperationKind.TOOL, operation.operation_key
                ),
                claimant=operation.operation_id,
                lease_epoch=operation.lease_epoch,
                status=(
                    MissionOperationStatus.FAILED
                    if outcome.status is ToolOutcomeStatus.ERROR
                    else MissionOperationStatus.SUCCEEDED
                ),
                receipt_json={"outcome": outcome.model_dump(mode="json")},
                payload_ref=outcome.payload_ref,
            ),
        )
        if not finished.finalized:
            return True
        await _append_under_current_lease(
            self.store,
            mission_id=operation.mission_id,
            lease_owner=await _lease_owner(self.store, operation),
            lease_epoch=operation.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="tool_operation_terminal",
                    operation_id=operation.operation_id,
                    phase=(MissionItemPhase.FAILED if outcome.status is ToolOutcomeStatus.ERROR else MissionItemPhase.COMPLETED),
                    stage_id=operation.stage_id,
                    producer="tool_orchestrator",
                    summary=outcome.summary,
                    payload_json={
                        "operation_key": operation.operation_key,
                        "outcome": outcome.model_dump(mode="json"),
                    },
                    payload_ref=outcome.payload_ref,
                )
            ],
        )
        return True


async def _lease_owner(store: MissionStorePort, operation: ToolOperation) -> str:
    mission = await store.get(operation.mission_id)
    if mission is None or mission.lease_owner is None or mission.lease_epoch != operation.lease_epoch:
        raise StaleToolLeaseError("mission lease fence is stale")
    return mission.lease_owner


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
        return can_start_stage(
            contract,
            _latest_stage_results(mission.snapshot_json),
            sequence_index=_sequence_index(stage_id),
            total_items=_stage_total_items(mission, contract),
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
        result = evaluate_stage_acceptance(contract, assessment, previous_state=previous)
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
        return {
            tool_id: self.orchestrator.catalog.require(tool_id).input_model.model_json_schema(
                mode="validation"
            )
            for tool_id in tool_ids
        }

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
            reasoning_effort="xhigh",
            max_retries=0,
        )
        bound = model.bind_tools(
            [_subagent_action_tool()],
            tool_choice="subagent_step",
            strict=True,
        )
        system = (
            "You are a bounded research worker inside Wenjin. Work only on the assigned task. "
            "Use only allowed tools. Never request room, memory, review, or mission writes. "
            "Construct tool arguments from tool_input_schemas exactly; selected_refs are values, not argument names. "
            "When acting as a reviewer, read every selected Mission review candidate with "
            "mission.read_review_candidate before returning a verdict. "
            "A completed tool result's payload_json is the authoritative returned content. Never repeat the same "
            "tool with the same arguments after it completed; reuse that result and complete on the next turn once "
            "the exit criteria are met. "
            "Return complete only when the exit criteria are met; otherwise use a tool or stop with an explicit reason. "
            "Do not reveal hidden reasoning. Your user-facing name is a short label, not an identity or authority claim."
        )
        payload = {
            "objective": job.objective,
            "task": job.task_summary,
            "role": job.role_label,
            "input_scope": job.input_scope,
            "mission_context_checkpoint": job.context_checkpoint,
            "selected_refs": job.selected_refs,
            "prior_output_briefs": job.prior_output_briefs,
            "allowed_tools": job.allowed_tools,
            "tool_input_schemas": job.tool_input_schemas,
            "worker_skill": job.worker_skill,
            "output_schema": job.output_schema,
            "exit_criteria": job.exit_criteria,
            "steps": [item.model_dump(mode="json") for item in steps[-12:]],
            "tool_results": [item.model_dump(mode="json") for item in tool_results[-8:]],
        }
        result = await bound.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=json.dumps(payload, ensure_ascii=False))]
        )
        return _parse_subagent_action(result)


class _ProviderSubagentAction(BaseModel):
    """Strict provider wire shape for a bounded subagent turn."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "complete", "stop"]
    summary: str = Field(min_length=1, max_length=4000)
    tool_name: str | None
    arguments_json: str
    result_json: str
    partial_result_json: str
    stop_reason: SubagentStopReason | None

    def to_domain(self) -> SubagentAction:
        return SubagentAction(
            kind=self.kind,
            summary=self.summary,
            tool_name=self.tool_name,
            arguments=parse_json_object(self.arguments_json, field_name="arguments_json"),
            result_json=parse_json_object(self.result_json, field_name="result_json"),
            partial_result_json=parse_json_object(
                self.partial_result_json,
                field_name="partial_result_json",
            ),
            stop_reason=self.stop_reason,
        )


def _subagent_action_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "subagent_step",
            "description": (
                "Choose the next bounded worker action. JSON object fields are encoded as JSON strings; "
                "use '{}' when empty and null for irrelevant nullable fields."
            ),
            "parameters": strict_provider_schema(_ProviderSubagentAction.model_json_schema()),
            "strict": True,
        },
    }


def _parse_subagent_action(message: AIMessage) -> SubagentAction:
    calls = message.tool_calls
    if len(calls) != 1 or str(calls[0].get("name") or "") != "subagent_step":
        raise ValueError("Subagent provider requires exactly one subagent_step frame")
    arguments = calls[0].get("args")
    if not isinstance(arguments, dict):
        raise ValueError("Subagent provider arguments must be an object")
    return _ProviderSubagentAction.model_validate(arguments).to_domain()


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
                raise RuntimeError(
                    "durable subagent terminal result has a divergent semantic request"
                )
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
                request_hash=_operation_request_hash(
                    MissionOperationKind.SANDBOX, request.operation_key
                ),
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
        mission = await self.store.get(request.provenance.mission_id)
        if mission is None or mission.lease_owner is None:
            raise StaleToolLeaseError("sandbox mission lease is unavailable")
        await _append_under_current_lease(
            self.store,
            mission_id=mission.mission_id,
            lease_owner=mission.lease_owner,
            lease_epoch=request.provenance.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="sandbox_operation_started",
                    operation_id=request.operation_key,
                    phase=MissionItemPhase.STARTED,
                    producer=request.provenance.subagent_id or "workspace_agent",
                    summary=f"Sandbox operation started: {request.operation_input.kind.value}",
                    payload_json={"operation_key": request.operation_key, "sandbox_job_id": sandbox_job_id},
                )
            ],
        )
        return SandboxReceiptClaim(
            state=SandboxReceiptState.CLAIMED,
            acquired=True,
            claimed_at=receipt.claimed_at,
        )

    async def finalize(self, result: SandboxOperationResult) -> None:
        receipt = await self.store.get_operation(
            result.provenance.mission_id, result.operation_key
        )
        if receipt is None:
            raise RuntimeError("sandbox operation was not atomically claimed")
        finished = await self.store.finish_operation(
            result.provenance.mission_id,
            MissionOperationFinishPayload(
                operation_key=result.operation_key,
                kind=MissionOperationKind.SANDBOX,
                request_hash=_operation_request_hash(
                    MissionOperationKind.SANDBOX, result.operation_key
                ),
                claimant=receipt.claimant,
                lease_epoch=result.provenance.lease_epoch,
                status=(
                    MissionOperationStatus.SUCCEEDED
                    if result.status.value == "succeeded"
                    else MissionOperationStatus.FAILED
                ),
                receipt_json={"result": result.model_dump(mode="json")},
            ),
        )
        if not finished.finalized:
            return
        mission = await self.store.get(result.provenance.mission_id)
        if mission is None or mission.lease_owner is None:
            raise StaleToolLeaseError("sandbox mission lease is unavailable")
        await _append_under_current_lease(
            self.store,
            mission_id=mission.mission_id,
            lease_owner=mission.lease_owner,
            lease_epoch=result.provenance.lease_epoch,
            items=[
                MissionItemDraftPayload(
                    item_type="sandbox_operation_terminal",
                    operation_id=result.operation_key,
                    phase=(MissionItemPhase.COMPLETED if result.status.value == "succeeded" else MissionItemPhase.FAILED),
                    producer=result.provenance.subagent_id or "workspace_agent",
                    summary=f"Sandbox operation {result.status.value}",
                    payload_json={"operation_key": result.operation_key, "result": result.model_dump(mode="json")},
                )
            ],
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
            raise ValueError(
                "subagent job cannot override pinned WorkerSkill configuration: "
                + ", ".join(supplied)
            )
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
        budget_raw = dict(raw.get("budget")) if isinstance(raw.get("budget"), dict) else {}
        budget_raw["max_context_bytes"] = max(
            SUBAGENT_MIN_RUNTIME_CONTEXT_BYTES,
            int(budget_raw.get("max_context_bytes") or 0),
        )
        jobs.append(
            SubagentJobSpec(
                job_id=f"sj_{digest}",
                operation_id=request.operation_id,
                mission_id=request.mission.mission_id,
                workspace_id=request.mission.workspace_id,
                model_id=request.mission.model_id,
                lease_owner=lease_owner,
                lease_epoch=request.mission.lease_epoch,
                stage_id=request.stage_id,
                display_name=display,
                role_label=role,
                task_summary=task,
                objective=request.mission.objective,
                input_scope={
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
                context_checkpoint_ref=request.frozen_context.context_checkpoint_ref,
                context_checkpoint=dict(request.frozen_context.context_checkpoint),
                selected_refs=tuple(str(item) for item in raw.get("selected_refs", ())),
                prior_output_briefs=request.frozen_context.prior_output_briefs,
                allowed_tools=allowed_tools,
                tool_input_schemas=input_schema_resolver(allowed_tools),
                worker_skill=dict(skill_contract),
                output_schema=dict(skill_contract.get("output_contract") or {}),
                exit_criteria=tuple(
                    str(item) for item in skill_contract.get("quality_focus") or ()
                ),
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
    source_key = contract.instantiation.source_context_key
    if not source_key:
        return None
    value = mission.runtime_context_json.get(source_key)
    if not isinstance(value, list):
        value = mission.snapshot_json.get(source_key)
    if not isinstance(value, list):
        intake = mission.snapshot_json.get("intake")
        value = intake.get(source_key) if isinstance(intake, dict) else None
    return len(value) if isinstance(value, list) else None


def _mission_tool_outcome(outcome: ResearchToolOutcome) -> MissionPortOutcome:
    return MissionPortOutcome(
        status=(MissionPortOutcomeStatus.FAILED if outcome.status is ToolOutcomeStatus.ERROR else MissionPortOutcomeStatus.COMPLETED),
        summary=outcome.summary or "Tool operation completed",
        payload_json={"research_tool_outcome": outcome.model_dump(mode="json")},
        payload_ref=outcome.payload_ref,
        risk_level=(cast(Literal["low", "medium", "high"], outcome.risk_level) if outcome.risk_level in {"low", "medium", "high"} else None),
        evidence_count_delta=len(outcome.evidence_refs),
        artifact_count_delta=len(outcome.artifact_refs),
    )


def _subagent_port_outcome(batch: SubagentBatchResult) -> MissionPortOutcome:
    failed = [item for item in batch.results if item.status is SubagentStatus.FAILED]
    evidence = {ref for item in batch.results for ref in item.evidence_refs}
    artifacts = {ref for item in batch.results for ref in item.artifact_refs}
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
        evidence_count_delta=len(evidence),
        artifact_count_delta=len(artifacts),
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

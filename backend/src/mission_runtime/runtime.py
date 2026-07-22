"""Lease-fenced, bounded driver for one durable MissionRun."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Awaitable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import Any, TypeVar

from src.agents.harness.stage_acceptance import resolve_stage_instance
from src.contracts.mission_budget import (
    MissionResourceUsage,
    execution_budget_from_runtime_context,
    resource_delta_for_item,
    resource_usage_from_snapshot,
    snapshot_with_resource_usage,
    unavailable_budget_dimensions,
)
from src.contracts.mission_input import merge_mission_input_manifests
from src.contracts.model_usage import (
    ModelCallStartedPayload,
    ModelCallState,
    ModelCallTerminalOutcome,
    ModelCallTerminalPayload,
    ModelUsageReceipt,
)
from src.contracts.prism_context import PrismContextRef
from src.contracts.reasoning import ReasoningEffort
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    stage_id_matches_contract,
    stage_instance_index,
)
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionApplyCommandsPayload,
    MissionCreatePayload,
    MissionDispatchClaimPayload,
    MissionDispatchReleasePayload,
    MissionItemDraftPayload,
    MissionItemPayload,
    MissionItemPhase,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionModelCallStatePayload,
    MissionResumePayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewStatus,
    MissionRiskLevel,
    MissionRunPatchPayload,
    MissionRunPayload,
    MissionStatus,
    MissionUserCommandPayload,
    validate_mission_snapshot,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    MISSION_DISPATCH_TTL_SECONDS,
    MISSION_MODEL_COMPLETION_MARGIN_SECONDS,
    MISSION_SUBAGENT_CAPACITY_RETRY_SECONDS,
    SUBAGENT_MODEL_REQUEST_TIMEOUT_SECONDS,
    MissionAgentDecision,
    MissionAgentProtocolError,
    MissionAgentResponseError,
    MissionAgentUsageError,
    MissionDecisionKind,
    MissionLoopContext,
    MissionPauseRequest,
    MissionPortOutcome,
    MissionPortOutcomeStatus,
    MissionSliceLimits,
    MissionSliceOutcome,
    MissionSliceTelemetry,
    MissionStartReceipt,
    MissionStartRequest,
    ReviewCandidateRequest,
    StageQualityRequest,
    StageQualityVerdict,
    SubagentExecutionRequest,
    SubagentFrozenContext,
    ToolExecutionRequest,
)
from src.mission_runtime.events import publish_after_commit
from src.mission_runtime.ports import (
    MissionAgentPort,
    MissionClockPort,
    MissionEventPublisherPort,
    MissionStartContextPort,
    MissionStorePort,
    MissionWakeupPublisherPort,
    ReviewCandidatePort,
    StageQualityPort,
    SubagentRuntimePort,
    SystemMissionClock,
    ToolOrchestratorPort,
)
from src.models.provider_errors import is_transient_model_error
from src.observability.prometheus import track_mission_dispatch

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_PENDING_COMMAND_REF_LIMIT = 20
_RECENT_ITEM_LIMIT = 24
_AGENT_REFERENCE_ITEM_LIMIT = 300

ResultT = TypeVar("ResultT")


class MissionStartRejectionCode(StrEnum):
    """Stable reasons why a Mission was rejected before persistence."""

    INVALID_START_STATE = "invalid_start_state"
    CONTINUATION_PARENT_NOT_FOUND = "continuation_parent_not_found"
    CONTINUATION_PARENT_NOT_TERMINAL = "continuation_parent_not_terminal"
    CONTINUATION_IDENTITY_MISMATCH = "continuation_identity_mismatch"
    CONTINUATION_POLICY_CHANGED = "continuation_policy_changed"


class MissionStartRejectedError(RuntimeError):
    """Raised when Mission creation fails a deterministic preflight check."""

    def __init__(self, message: str, *, code: MissionStartRejectionCode) -> None:
        super().__init__(message)
        self.code = code


class MissionResumeRequestMismatchError(RuntimeError):
    """Raised when input answers a different durable pause request."""


class MissionLeaseLostError(RuntimeError):
    """Raised when a running slice observes that its durable lease is no longer current."""


@dataclass(slots=True)
class _SliceState:
    run: MissionRunPayload
    worker_id: str
    started_monotonic: float
    deadline_monotonic: float
    last_heartbeat_monotonic: float
    model_turns: int = 0
    tool_steps: int = 0


def _status_value(run: MissionRunPayload) -> str:
    return run.status.value


def _is_conflict(exc: BaseException) -> bool:
    return isinstance(exc, DataServiceClientError) and exc.status_code == 409


def _risk(value: str | None) -> MissionRiskLevel | None:
    return MissionRiskLevel(value) if value in {"low", "medium", "high"} else None


def _pinned_stage_contracts(
    run: MissionRunPayload,
) -> dict[str, StageAcceptanceContract]:
    raw = run.runtime_context_json.get("stage_contracts")
    if not isinstance(raw, dict):
        return {}
    contracts: dict[str, StageAcceptanceContract] = {}
    for value in raw.values():
        if not isinstance(value, dict):
            continue
        contract = StageAcceptanceContract.model_validate(value)
        contracts[contract.stage_id] = contract
    return contracts


def _stage_item_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    raw = snapshot.get("stage_item_counts")
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(key, str) and not isinstance(value, bool) and isinstance(value, int) and 1 <= value <= 100}


class MissionRuntime:
    """Own mission lifecycle discipline; injected ports own domain intelligence."""

    def __init__(
        self,
        *,
        store: MissionStorePort,
        agent: MissionAgentPort,
        start_context: MissionStartContextPort,
        tools: ToolOrchestratorPort,
        subagents: SubagentRuntimePort,
        quality: StageQualityPort,
        review_candidates: ReviewCandidatePort,
        events: MissionEventPublisherPort,
        wakeups: MissionWakeupPublisherPort,
        limits: MissionSliceLimits | None = None,
        clock: MissionClockPort | None = None,
    ) -> None:
        self.store = store
        self.agent = agent
        self.start_context = start_context
        self.tools = tools
        self.subagents = subagents
        self.quality = quality
        self.review_candidates = review_candidates
        self.events = events
        self.wakeups = wakeups
        self.limits = limits or MissionSliceLimits()
        self.clock = clock or SystemMissionClock()

    async def start(self, request: MissionStartRequest) -> MissionStartReceipt:
        request = await self.start_context.pin(request)
        snapshot = dict(request.snapshot_json)
        if any(
            key in snapshot
            for key in (
                "stage_acceptance",
                "stage_item_counts",
                "mission_lineage",
                "resource_usage",
            )
        ):
            raise MissionStartRejectedError(
                "Mission start cannot provide server-owned acceptance, lineage, or resource state",
                code=MissionStartRejectionCode.INVALID_START_STATE,
            )
        execution_budget_from_runtime_context(request.runtime_context_json)
        snapshot = snapshot_with_resource_usage(snapshot, MissionResourceUsage())
        if request.continuation is not None and request.parent_mission_id is None:
            raise MissionStartRejectedError(
                "Mission continuation feedback requires a parent MissionRun",
                code=MissionStartRejectionCode.INVALID_START_STATE,
            )
        if request.parent_mission_id is not None:
            snapshot.update(
                await self._validated_parent_continuation(
                    request,
                    parent_mission_id=request.parent_mission_id,
                )
            )
        created = await self.store.admit(
            MissionCreatePayload(
                parent_mission_id=request.parent_mission_id,
                workspace_id=request.workspace_id,
                thread_id=request.thread_id,
                user_id=request.user_id,
                workspace_type=request.workspace_type,
                mission_policy_id=request.mission_policy_id,
                title=request.title,
                objective=request.objective,
                review_mode=request.review_mode,
                model_id=request.model_id,
                reasoning_effort=ReasoningEffort(request.reasoning_effort),
                snapshot_json=validate_mission_snapshot(snapshot),
                runtime_context_json=request.runtime_context_json,
                mission_idempotency_key=request.mission_idempotency_key,
            )
        )
        await publish_after_commit(
            self.events,
            self.clock,
            created.mission,
            created=created.created,
        )
        wakeup_published = False
        if created.created and created.mission.status is not MissionStatus.WAITING:
            wakeup_published = await self._publish_wakeup(created.mission.mission_id)
        return MissionStartReceipt(
            mission_id=created.mission.mission_id,
            status=created.mission.status.value,
            title=created.mission.title,
            created=created.created,
            wakeup_published=wakeup_published,
        )

    async def _validated_parent_continuation(
        self,
        request: MissionStartRequest,
        *,
        parent_mission_id: str,
    ) -> dict[str, Any]:
        parent = await self.store.get(parent_mission_id)
        if parent is None:
            raise MissionStartRejectedError(
                "Parent MissionRun was not found",
                code=MissionStartRejectionCode.CONTINUATION_PARENT_NOT_FOUND,
            )
        if parent.status.value not in _TERMINAL_STATUSES:
            raise MissionStartRejectedError(
                "Parent MissionRun must be terminal before starting a continuation",
                code=MissionStartRejectionCode.CONTINUATION_PARENT_NOT_TERMINAL,
            )
        identity_matches = (
            parent.workspace_id == request.workspace_id
            and parent.thread_id == request.thread_id
            and parent.user_id == request.user_id
            and parent.workspace_type == request.workspace_type
            and parent.mission_policy_id == request.mission_policy_id
        )
        if not identity_matches:
            raise MissionStartRejectedError(
                "Parent continuation must keep workspace, thread, user, workspace type, and MissionPolicy",
                code=MissionStartRejectionCode.CONTINUATION_IDENTITY_MISMATCH,
            )
        parent_policy_hash = str(parent.runtime_context_json.get("policy_content_hash") or "")
        child_policy_hash = str(request.runtime_context_json.get("policy_content_hash") or "")
        if not parent_policy_hash or parent_policy_hash != child_policy_hash:
            raise MissionStartRejectedError(
                "Parent continuation requires the same pinned MissionPolicy content hash",
                code=MissionStartRejectionCode.CONTINUATION_POLICY_CHANGED,
            )

        passed = self._passed_stage_acceptance(parent)
        invalidated_stage_ids: set[str] = set()
        if request.continuation is not None:
            invalidated_stage_ids = self._stage_invalidation_closure(
                parent,
                passed_stage_ids=set(passed),
                reset_stage_ids=set(request.continuation.reset_stage_ids),
            )
            passed = {stage_id: result for stage_id, result in passed.items() if stage_id not in invalidated_stage_ids}
        upstream_refs = await self._continuation_upstream_refs(
            parent.mission_id,
            passed,
        )
        continuation_snapshot: dict[str, Any] = {
            "stage_acceptance": passed,
            "mission_inputs": merge_mission_input_manifests(
                parent.snapshot_json.get("mission_inputs"),
                request.snapshot_json.get("mission_inputs"),
                workspace_id=request.workspace_id,
                thread_id=request.thread_id,
            ),
            "mission_lineage": {
                "source_mission_id": parent.mission_id,
                "source_state_version": parent.state_version,
                "source_last_item_seq": parent.last_item_seq,
                "source_status": parent.status.value,
                "policy_content_hash": parent_policy_hash,
                "inherited_stage_ids": sorted(passed),
                **(
                    {
                        "continuation_reason": request.continuation.reason,
                        "source_review_item_ids": list(request.continuation.review_item_ids),
                        "reset_stage_ids": list(request.continuation.reset_stage_ids),
                        "invalidated_stage_ids": sorted(invalidated_stage_ids),
                        "rationale": request.continuation.rationale,
                    }
                    if request.continuation is not None
                    else {}
                ),
                "upstream_refs": upstream_refs,
            },
        }
        inherited_item_counts = self._inheritable_stage_item_counts(
            parent,
            passed_stage_ids=set(passed),
            invalidated_stage_ids=invalidated_stage_ids,
        )
        if inherited_item_counts:
            continuation_snapshot["stage_item_counts"] = inherited_item_counts
        return continuation_snapshot

    @staticmethod
    def _passed_stage_acceptance(
        run: MissionRunPayload,
    ) -> dict[str, dict[str, Any]]:
        raw_acceptance = run.snapshot_json.get("stage_acceptance")
        return {str(stage_id): deepcopy(result) for stage_id, result in (raw_acceptance.items() if isinstance(raw_acceptance, dict) else ()) if isinstance(result, dict) and result.get("result") == "pass"}

    @staticmethod
    def _stage_invalidation_closure(
        parent: MissionRunPayload,
        *,
        passed_stage_ids: set[str],
        reset_stage_ids: set[str],
    ) -> set[str]:
        if not reset_stage_ids or not reset_stage_ids <= passed_stage_ids:
            raise MissionStartRejectedError(
                "Continuation reset stages must reference passed parent stages",
                code=MissionStartRejectionCode.INVALID_START_STATE,
            )
        raw_contracts = parent.runtime_context_json.get("stage_contracts")
        if not isinstance(raw_contracts, dict):
            raise MissionStartRejectedError(
                "Parent MissionRun has no pinned stage contracts",
                code=MissionStartRejectionCode.INVALID_START_STATE,
            )
        contracts = [StageAcceptanceContract.model_validate(value) for value in raw_contracts.values() if isinstance(value, dict)]
        counts = _stage_item_counts(parent.snapshot_json)

        prerequisites: dict[str, set[str]] = {}
        for stage_id in passed_stage_ids:
            contract = next(
                (candidate for candidate in contracts if stage_id_matches_contract(candidate, stage_id)),
                None,
            )
            if contract is None:
                raise MissionStartRejectedError(
                    f"Parent stage contract is unavailable: {stage_id}",
                    code=MissionStartRejectionCode.INVALID_START_STATE,
                )
            sequence_index = (
                stage_instance_index(
                    contract.instantiation.instance_id_template,
                    stage_id,
                )
                if contract.instantiation.mode == "per_item"
                else None
            )
            source_key = str(contract.item_count_source_key() or "")
            total_items = counts.get(source_key)
            instance = resolve_stage_instance(
                contract,
                sequence_index=sequence_index,
                total_items=total_items,
            )
            prerequisites[stage_id] = set(instance.prerequisite_stage_ids)

        invalidated = set(reset_stage_ids)
        changed = True
        while changed:
            changed = False
            for stage_id, required in prerequisites.items():
                if stage_id not in invalidated and required.intersection(invalidated):
                    invalidated.add(stage_id)
                    changed = True
        return invalidated

    @staticmethod
    def _inheritable_stage_item_counts(
        run: MissionRunPayload,
        *,
        passed_stage_ids: set[str],
        invalidated_stage_ids: set[str],
    ) -> dict[str, int]:
        """Keep dynamic counts only while their accepted source stages remain valid."""

        item_counts = _stage_item_counts(run.snapshot_json)
        if not item_counts:
            return {}
        contracts = _pinned_stage_contracts(run)
        retained: dict[str, int] = {}
        for source_key, item_count in item_counts.items():
            source_stage_ids = MissionRuntime._item_count_source_stage_ids(
                contracts,
                source_key,
            )
            if source_stage_ids and source_stage_ids <= passed_stage_ids and source_stage_ids.isdisjoint(invalidated_stage_ids):
                retained[source_key] = item_count
        return retained

    @staticmethod
    def _item_count_source_stage_ids(
        contracts: dict[str, StageAcceptanceContract],
        source_key: str,
    ) -> set[str]:
        return {
            prerequisite
            for contract in contracts.values()
            if contract.item_count_source_key() == source_key
            for prerequisite in contract.prerequisite_stage_ids
            if prerequisite in contracts and contracts[prerequisite].instantiation.mode == "single"
        }

    async def _continuation_upstream_refs(
        self,
        parent_mission_id: str,
        passed: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        review_items = await self.store.list_review_items(parent_mission_id)
        by_id = {item.review_item_id: item for item in review_items}
        committed_by_output: dict[str, MissionReviewItemPayload] = {}
        for item in review_items:
            if item.status is not MissionReviewStatus.COMMITTED or not item.target_ref:
                continue
            current = committed_by_output.get(item.output_key)
            if current is None or item.updated_at > current.updated_at:
                committed_by_output[item.output_key] = item

        inherited: list[dict[str, str]] = []
        seen_targets: set[str] = set()
        canonical_target_kinds = {
            "asset:": "workspace_asset",
            "prism-file:": "workspace_document",
            "sandbox-artifact:": "sandbox_artifact",
            "artifact-candidate:": "internal_candidate",
            "mission-input:": "mission_input",
        }
        for stage_id in sorted(passed):
            receipt = passed[stage_id]
            for ref_kind in ("artifact_refs", "evidence_refs"):
                for raw_ref in receipt.get(ref_kind) or ():
                    source_ref = str(raw_ref).strip()
                    if not source_ref:
                        continue
                    target_kind = next(
                        (kind for prefix, kind in canonical_target_kinds.items() if source_ref.startswith(prefix)),
                        "",
                    )
                    target_ref = source_ref if target_kind else None
                    output_key = ""
                    review_item = by_id.get(source_ref)
                    if review_item is not None:
                        committed: MissionReviewItemPayload | None = (
                            review_item
                            if review_item.status is MissionReviewStatus.COMMITTED
                            else committed_by_output.get(review_item.output_key)
                        )
                        if committed is not None:
                            target_ref = committed.target_ref
                            output_key = committed.output_key
                            target_kind = committed.target_kind
                    if not target_ref or target_ref in seen_targets:
                        continue
                    seen_targets.add(target_ref)
                    inherited.append(
                        {
                            "stage_id": stage_id,
                            "source_ref": source_ref,
                            "target_ref": target_ref,
                            "target_kind": target_kind,
                            "output_key": output_key,
                        }
                    )
        parent = await self.store.get(parent_mission_id)
        raw_lineage = parent.snapshot_json.get("mission_lineage") if parent is not None else None
        lineage_refs = raw_lineage.get("upstream_refs") if isinstance(raw_lineage, dict) else None
        for raw in lineage_refs if isinstance(lineage_refs, list) else ():
            if not isinstance(raw, dict):
                continue
            stage_id = str(raw.get("stage_id") or "").strip()
            target_ref = str(raw.get("target_ref") or "").strip()
            if stage_id not in passed or not any(target_ref.startswith(prefix) for prefix in canonical_target_kinds) or target_ref in seen_targets:
                continue
            seen_targets.add(target_ref)
            inherited.append(
                {
                    "stage_id": stage_id,
                    "source_ref": str(raw.get("source_ref") or target_ref),
                    "target_ref": target_ref,
                    "target_kind": str(raw.get("target_kind") or ""),
                    "output_key": str(raw.get("output_key") or ""),
                }
            )
        return inherited

    async def resume(
        self,
        mission_id: str,
        *,
        request_id: str,
        input_json: dict[str, Any],
        producer: str = "workspace_agent",
    ) -> MissionRunPayload:
        current = await self.store.get(mission_id)
        if current is None:
            raise MissionResumeRequestMismatchError("MissionRun was not found")
        if current.status == MissionStatus.WAITING:
            pending_request = current.snapshot_json.get("pending_request")
            expected_request_id = str(pending_request.get("request_id") or "") if isinstance(pending_request, dict) else ""
            if not expected_request_id or expected_request_id != request_id:
                raise MissionResumeRequestMismatchError("Resume request_id does not match the pending mission request")
        result = await self.store.resume(
            mission_id,
            MissionResumePayload(
                request_id=request_id,
                input_json=input_json,
                producer=producer,
            ),
        )
        await publish_after_commit(self.events, self.clock, result.mission)
        await self._publish_wakeup(mission_id, command_hint=request_id)
        return await self.store.get(mission_id) or result.mission

    async def cancel(
        self,
        mission_id: str,
        *,
        request_id: str,
        reason: str | None = None,
        producer: str = "workspace_agent",
    ) -> MissionRunPayload:
        current = await self.store.get(mission_id)
        if current is None:
            raise LookupError("MissionRun was not found")
        if _status_value(current) in _TERMINAL_STATUSES:
            return current
        result = await self.store.append_command(
            mission_id,
            MissionUserCommandPayload(
                command_id=request_id,
                command_type="cancel",
                summary=reason or "Mission cancellation requested",
                producer=producer,
                payload_json={"reason": reason},
            ),
        )
        await publish_after_commit(self.events, self.clock, result.mission)
        await self._publish_wakeup(mission_id, command_hint=request_id)
        return await self.store.get(mission_id) or result.mission

    async def run_slice(
        self,
        mission_id: str,
        *,
        worker_id: str,
        dispatch_owner: str | None = None,
        dispatch_epoch: int | None = None,
        command_hint: str | None = None,
    ) -> MissionSliceTelemetry:
        initial = await self.store.get(mission_id)
        if initial is None:
            return self._telemetry_missing(mission_id, command_hint=command_hint)
        if _status_value(initial) in _TERMINAL_STATUSES:
            return self._telemetry(
                initial,
                MissionSliceOutcome.TERMINAL,
                "mission_already_terminal",
                command_hint=command_hint,
            )
        waiting_without_command = (
            _status_value(initial) == "waiting"
            and initial.last_command_seq <= initial.last_applied_command_seq
        )
        if (
            waiting_without_command
            and dispatch_owner is None
            and dispatch_epoch is None
            and initial.dispatch_owner is None
        ):
            return self._telemetry(
                initial,
                MissionSliceOutcome.WAITING,
                "mission_waiting_for_input",
                command_hint=command_hint,
            )

        if dispatch_owner is None and dispatch_epoch is None and (
            initial.dispatch_owner is None
            or initial.dispatch_expires_at is None
            or not _expires_after(initial.dispatch_expires_at, self.clock.now())
        ):
            local_dispatch_owner = f"mission-inline-dispatch:{uuid.uuid4().hex}"
            try:
                initial = await self.store.claim_dispatch(
                    mission_id,
                    MissionDispatchClaimPayload(
                        worker_id=local_dispatch_owner,
                        expected_state_version=initial.state_version,
                        ttl_seconds=MISSION_DISPATCH_TTL_SECONDS,
                    ),
                )
            except Exception as exc:
                if not _is_conflict(exc):
                    raise
            else:
                dispatch_owner = local_dispatch_owner
                dispatch_epoch = initial.dispatch_epoch

        effective_dispatch_owner = dispatch_owner or initial.dispatch_owner
        effective_dispatch_epoch = (
            dispatch_epoch if dispatch_epoch is not None else initial.dispatch_epoch
        )
        if (
            not effective_dispatch_owner
            or effective_dispatch_epoch < 1
            or initial.dispatch_owner != effective_dispatch_owner
            or initial.dispatch_epoch != effective_dispatch_epoch
        ):
            return self._telemetry(
                initial,
                MissionSliceOutcome.YIELDED,
                "stale_delivery",
                command_hint=command_hint,
            )
        if (
            initial.dispatch_expires_at is None
            or not _expires_after(initial.dispatch_expires_at, self.clock.now())
        ):
            return self._telemetry(
                initial,
                MissionSliceOutcome.YIELDED,
                "delivery_expired",
                command_hint=command_hint,
            )

        if waiting_without_command:
            try:
                await self.store.release_dispatch(
                    mission_id,
                    MissionDispatchReleasePayload(
                        worker_id=effective_dispatch_owner,
                        dispatch_epoch=effective_dispatch_epoch,
                    ),
                )
            except Exception as exc:
                if not _is_conflict(exc):
                    raise
            else:
                track_mission_dispatch("waiting_delivery_released")
            latest = await self.store.get(mission_id) or initial
            return self._telemetry(
                latest,
                MissionSliceOutcome.WAITING,
                "mission_waiting_for_input",
                command_hint=command_hint,
            )

        try:
            claimed = await self.store.claim_lease(
                mission_id,
                MissionLeaseClaimPayload(
                    worker_id=worker_id,
                    dispatch_owner=effective_dispatch_owner,
                    dispatch_epoch=effective_dispatch_epoch,
                    expected_state_version=initial.state_version,
                    ttl_seconds=self.limits.lease_ttl_seconds,
                ),
            )
        except Exception as exc:
            if not _is_conflict(exc):
                raise
            try:
                await self.store.release_dispatch(
                    mission_id,
                    MissionDispatchReleasePayload(
                        worker_id=effective_dispatch_owner,
                        dispatch_epoch=effective_dispatch_epoch,
                    ),
                )
            except Exception as release_exc:
                if not _is_conflict(release_exc):
                    logger.warning(
                        "Mission dispatch release failed after lease conflict mission=%s",
                        mission_id,
                        exc_info=True,
                    )
            else:
                track_mission_dispatch("lease_claim_released")
            latest = await self.store.get(mission_id) or initial
            return self._telemetry(
                latest,
                MissionSliceOutcome.YIELDED,
                "lease_not_acquired",
                command_hint=command_hint,
            )

        started = self.clock.monotonic()
        state = _SliceState(
            run=claimed,
            worker_id=worker_id,
            started_monotonic=started,
            deadline_monotonic=started + self.limits.wall_time_seconds,
            last_heartbeat_monotonic=started,
        )
        await publish_after_commit(self.events, self.clock, state.run)

        while True:
            try:
                return await self._drive_claimed(state, command_hint=command_hint)
            except Exception as exc:
                if isinstance(exc, MissionLeaseLostError):
                    latest = await self.store.get(mission_id) or state.run
                    state.run = latest
                    return self._telemetry(
                        latest,
                        MissionSliceOutcome.YIELDED,
                        "lease_fence_lost",
                        state=state,
                        command_hint=command_hint,
                    )
                if not _is_conflict(exc):
                    raise
                latest = await self.store.get(mission_id) or state.run
                lease_is_current = latest.lease_owner == state.worker_id and latest.lease_epoch == state.run.lease_epoch and _expires_after(latest.lease_expires_at, self.clock.now())
                if _status_value(latest) not in _TERMINAL_STATUSES and lease_is_current:
                    # A durable command may legitimately advance state_version
                    # while this driver is inside a model/tool call. Discard the
                    # stale in-memory decision and restart at a safe boundary.
                    state.run = latest
                    continue
                if _status_value(latest) in _TERMINAL_STATUSES:
                    return self._telemetry(
                        latest,
                        MissionSliceOutcome.TERMINAL,
                        "mission_became_terminal_during_slice",
                        state=state,
                        command_hint=command_hint,
                    )
                if _status_value(latest) == "waiting":
                    return self._telemetry(
                        latest,
                        MissionSliceOutcome.WAITING,
                        "mission_paused_during_slice",
                        state=state,
                        command_hint=command_hint,
                    )
                return self._telemetry(
                    latest,
                    MissionSliceOutcome.YIELDED,
                    "lease_fence_lost",
                    state=state,
                    command_hint=command_hint,
                )

    async def _drive_claimed(
        self,
        state: _SliceState,
        *,
        command_hint: str | None,
    ) -> MissionSliceTelemetry:
        if await self._reconcile_model_call_ledger(state):
            return self._telemetry(
                state.run,
                MissionSliceOutcome.TERMINAL,
                "model_usage_reconciliation_required",
                state=state,
                command_hint=command_hint,
            )
        if _status_value(state.run) == "created":
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type="status_update",
                        phase=MissionItemPhase.COMPLETED,
                        producer="mission_runtime",
                        summary="Mission planning started",
                        payload_json={"status": "planning"},
                    )
                ],
                snapshot=self._merge_snapshot(
                    state.run.snapshot_json,
                    {"next_actions": ["plan_or_replan"]},
                ),
                patch=MissionRunPatchPayload(status=MissionStatus.PLANNING),
            )
        if _status_value(state.run) == "planning":
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type="status_update",
                        phase=MissionItemPhase.COMPLETED,
                        producer="mission_runtime",
                        summary="Mission drive loop started",
                        payload_json={"status": "running"},
                    )
                ],
                patch=MissionRunPatchPayload(status=MissionStatus.RUNNING),
            )

        raw_protocol_repair = state.run.snapshot_json.get("protocol_repair")
        protocol_retry_count = (
            int(raw_protocol_repair.get("attempt") or 0)
            if isinstance(raw_protocol_repair, dict)
            else 0
        )
        protocol_feedback = (
            str(raw_protocol_repair.get("feedback") or "")[:1000] or None
            if isinstance(raw_protocol_repair, dict)
            else None
        )
        while True:
            if await self._reconcile_model_call_ledger(state):
                return self._telemetry(
                    state.run,
                    MissionSliceOutcome.TERMINAL,
                    "model_usage_reconciliation_required",
                    state=state,
                    command_hint=command_hint,
                )
            command_result = await self._apply_commands_at_boundary(state)
            if command_result is not None:
                return self._telemetry(
                    state.run,
                    command_result,
                    "durable_command_applied",
                    state=state,
                    command_hint=command_hint,
                )
            if state.run.last_applied_command_seq < state.run.last_command_seq:
                continue

            if _status_value(state.run) == "planning":
                await self._append(
                    state,
                    items=[
                        MissionItemDraftPayload(
                            item_type="status_update",
                            phase=MissionItemPhase.COMPLETED,
                            producer="mission_runtime",
                            summary="Mission replanning boundary completed",
                            payload_json={"status": "running"},
                        )
                    ],
                    patch=MissionRunPatchPayload(status=MissionStatus.RUNNING),
                )

            await self._heartbeat_if_due(state)

            if self._inflight_operation_lacks_time(state):
                return await self._checkpoint_and_yield(
                    state,
                    reason="inflight_operation_deferred",
                    command_hint=command_hint,
                )

            if self._slice_budget_exhausted(state):
                return await self._checkpoint_and_yield(
                    state,
                    reason="slice_budget_exhausted",
                    command_hint=command_hint,
                )

            recovered, recovery_outcome = await self._recover_inflight_operation(state)
            if recovery_outcome is not None:
                if recovery_outcome is MissionSliceOutcome.YIELDED:
                    return await self._checkpoint_and_yield(
                        state,
                        reason="subagent_quantum_yielded",
                        command_hint=command_hint,
                    )
                return self._telemetry(
                    state.run,
                    recovery_outcome,
                    "inflight_operation_recovered",
                    state=state,
                    command_hint=command_hint,
                )
            if recovered:
                continue

            context = await self._build_loop_context(
                state,
                protocol_feedback=protocol_feedback,
            )
            unavailable = self._unavailable_resource_dimensions(
                state.run,
                model_calls=1,
            )
            if unavailable:
                await self._fail_resource_budget(state, unavailable)
                return self._telemetry(
                    state.run,
                    MissionSliceOutcome.TERMINAL,
                    "resource_budget_exhausted",
                    state=state,
                    command_hint=command_hint,
                )
            if self._slice_budget_exhausted(state):
                continue

            model_turn = state.model_turns + 1
            model_attempt = protocol_retry_count + 1
            model_call_id = f"model-call:workspace:{state.run.lease_epoch}:{state.run.last_item_seq + 1}"
            await self._persist_workspace_model_call_started(
                state,
                model_call_id=model_call_id,
                model_turn=model_turn,
                model_attempt=model_attempt,
            )
            state.model_turns += 1
            try:
                decision = await self._invoke_with_deadline(
                    self.agent.decide(context),
                    state,
                )
                usage_receipt = self._require_model_usage_receipt(
                    decision.usage_receipt,
                    model_id=state.run.model_id,
                )
            except asyncio.CancelledError as exc:
                try:
                    await asyncio.shield(
                        self._persist_workspace_model_terminal(
                            state,
                            model_call_id=model_call_id,
                            model_turn=model_turn,
                            model_attempt=model_attempt,
                            outcome=ModelCallTerminalOutcome.UNRESOLVED,
                            error_type=type(exc).__name__,
                            detail=(
                                "Workspace model call was cancelled before usage "
                                "could be confirmed"
                            ),
                        )
                    )
                finally:
                    raise
            except MissionLeaseLostError:
                # The new lease owner will reconcile the open model-call record.
                # This worker must not attempt any further fenced ledger write.
                raise
            except Exception as exc:
                error_receipt = (
                    exc.usage_receipt
                    if isinstance(exc, MissionAgentResponseError)
                    else None
                )
                if error_receipt is not None:
                    try:
                        error_receipt = self._require_model_usage_receipt(
                            error_receipt,
                            model_id=state.run.model_id,
                        )
                        await self._persist_workspace_model_usage(
                            state,
                            model_call_id=model_call_id,
                            model_turn=model_turn,
                            model_attempt=model_attempt,
                            usage_receipt=error_receipt,
                        )
                    except MissionAgentUsageError as usage_exc:
                        exc = usage_exc
                        error_receipt = None
                if error_receipt is None:
                    if isinstance(exc, MissionAgentResponseError):
                        exc = MissionAgentUsageError(
                            "Mission response error did not carry a usage receipt"
                        )
                    terminal_outcome = self._nonreceipt_model_call_outcome(exc)
                    await self._persist_workspace_model_terminal(
                        state,
                        model_call_id=model_call_id,
                        model_turn=model_turn,
                        model_attempt=model_attempt,
                        outcome=terminal_outcome,
                        error_type=type(exc).__name__,
                        detail=str(exc)[:1000] or type(exc).__name__,
                    )
                    if terminal_outcome is ModelCallTerminalOutcome.UNRESOLVED:
                        await self._fail_model_call_reconciliation(state)
                        return self._telemetry(
                            state.run,
                            MissionSliceOutcome.TERMINAL,
                            "model_usage_reconciliation_required",
                            state=state,
                            command_hint=command_hint,
                        )
                if (
                    isinstance(exc, MissionAgentProtocolError)
                    and protocol_retry_count
                    < self.limits.max_protocol_retries_per_step
                ):
                    protocol_retry_count += 1
                    protocol_feedback = str(exc)[:1000]
                    await self._append(
                        state,
                        items=[],
                        snapshot=self._merge_snapshot(
                            state.run.snapshot_json,
                            {
                                "protocol_repair": {
                                    "attempt": protocol_retry_count,
                                    "feedback": protocol_feedback,
                                },
                                "next_actions": ["repair_structured_decision"],
                            },
                        ),
                    )
                    if self._slice_budget_exhausted(state):
                        return await self._checkpoint_and_yield(
                            state,
                            reason="agent_protocol_repair_deferred",
                            command_hint=command_hint,
                        )
                    continue
                if (
                    isinstance(exc, MissionAgentProtocolError)
                    and "protocol_repair" in state.run.snapshot_json
                ):
                    await self._append(
                        state,
                        items=[],
                        snapshot=self._merge_snapshot(
                            state.run.snapshot_json,
                            {"protocol_repair": None},
                        ),
                    )
                transient_failure = is_transient_model_error(exc)
                terminal = await self._record_loop_failure(state, exc)
                if terminal:
                    return self._telemetry(
                        state.run,
                        MissionSliceOutcome.TERMINAL,
                        "repeated_agent_failure",
                        state=state,
                        command_hint=command_hint,
                    )
                return await self._checkpoint_and_yield(
                    state,
                    reason="agent_step_failed",
                    command_hint=command_hint,
                    retry_delay_seconds=(_transient_retry_delay_seconds(state.run) if transient_failure else 0),
                )

            await self._persist_workspace_model_usage(
                state,
                model_call_id=model_call_id,
                model_turn=model_turn,
                model_attempt=model_attempt,
                usage_receipt=usage_receipt,
            )
            protocol_retry_count = 0
            protocol_feedback = None
            if "protocol_repair" in state.run.snapshot_json:
                await self._append(
                    state,
                    items=[],
                    snapshot=self._merge_snapshot(
                        state.run.snapshot_json,
                        {"protocol_repair": None},
                    ),
                )
            last_applied_command_seq = state.run.last_applied_command_seq
            command_result = await self._apply_commands_at_boundary(state)
            if command_result is not None:
                return self._telemetry(
                    state.run,
                    command_result,
                    "durable_command_applied",
                    state=state,
                    command_hint=command_hint,
                )
            if state.run.last_applied_command_seq > last_applied_command_seq:
                continue
            outcome = await self._handle_decision(state, decision)
            if outcome is not None:
                if outcome is MissionSliceOutcome.YIELDED:
                    return await self._checkpoint_and_yield(
                        state,
                        reason="subagent_quantum_yielded",
                        command_hint=command_hint,
                    )
                return self._telemetry(
                    state.run,
                    outcome,
                    f"decision_{decision.kind.value}",
                    state=state,
                    command_hint=command_hint,
                )

    async def _apply_commands_at_boundary(
        self,
        state: _SliceState,
    ) -> MissionSliceOutcome | None:
        commands = await self._load_unapplied_commands(state.run)
        if not commands:
            return None

        refs = [
            {
                "seq": command.seq,
                "operation_id": command.operation_id,
                "command_type": str(command.payload_json.get("command_type") or "steer"),
                "summary": (command.summary or "")[:300] or None,
            }
            for command in commands[-_PENDING_COMMAND_REF_LIMIT:]
        ]
        snapshot_patch: dict[str, Any] = {
            "pending_command_refs": refs,
            "next_actions": ["replan_from_durable_commands"],
        }
        incoming_inputs: list[dict[str, Any]] = []
        for command in commands:
            raw_inputs = command.payload_json.get("mission_inputs")
            if isinstance(raw_inputs, list):
                incoming_inputs.extend(
                    value for value in raw_inputs if isinstance(value, dict)
                )
        if incoming_inputs:
            snapshot_patch["mission_inputs"] = merge_mission_input_manifests(
                state.run.snapshot_json.get("mission_inputs"),
                incoming_inputs,
                workspace_id=state.run.workspace_id,
                thread_id=state.run.thread_id,
            )
        invalid_command_seqs: set[int] = set()
        latest_prism_ref: PrismContextRef | None = None
        for command in commands:
            raw_prism_ref = command.payload_json.get("prism_context_ref")
            if raw_prism_ref is None:
                continue
            try:
                prism_ref = PrismContextRef.model_validate(raw_prism_ref)
                if prism_ref.workspace_id != state.run.workspace_id:
                    raise ValueError(
                        "Prism context does not belong to the Mission workspace"
                    )
            except ValueError:
                invalid_command_seqs.add(command.seq)
                continue
            latest_prism_ref = prism_ref
        if latest_prism_ref is not None:
            snapshot_patch["prism_context_ref"] = latest_prism_ref.model_dump(
                mode="json"
            )
        items = [
            MissionItemDraftPayload(
                item_type="status_update",
                operation_id=command.operation_id,
                phase=(
                    MissionItemPhase.FAILED
                    if command.seq in invalid_command_seqs
                    else MissionItemPhase.COMPLETED
                ),
                producer="mission_runtime",
                summary=(
                    "Durable Mission command rejected an invalid Prism context"
                    if command.seq in invalid_command_seqs
                    else command.summary or "Durable mission input applied"
                ),
                payload_json={
                    "command_seq": command.seq,
                    "command_type": str(command.payload_json.get("command_type") or "steer"),
                    **(
                        {"error_code": "invalid_prism_context"}
                        if command.seq in invalid_command_seqs
                        else {}
                    ),
                },
            )
            for command in commands
        ]

        command_types = {str(command.payload_json.get("command_type") or "steer") for command in commands}
        review_modes = [str(command.payload_json.get("review_mode") or "") for command in commands if command.payload_json.get("command_type") == "set_review_mode"]
        review_feedback_commands = [command for command in commands if command.payload_json.get("command_type") == "review_feedback"]
        has_more_commands = commands[-1].seq < state.run.last_command_seq
        raw_pending_control = state.run.snapshot_json.get("pending_command_control")
        pending_control = (
            dict(raw_pending_control)
            if isinstance(raw_pending_control, dict)
            else {}
        )
        pending_control_type = str(pending_control.get("command_type") or "")
        pause_commands = [
            command
            for command in commands
            if command.payload_json.get("command_type") == "pause"
        ]
        if "cancel" in command_types or pending_control_type == "cancel":
            pending_control = {"command_type": "cancel"}
        elif pause_commands:
            pending_control = {
                "command_type": "pause",
                "operation_id": pause_commands[-1].operation_id,
            }
        elif pending_control_type != "pause":
            pending_control = {}
        snapshot_patch["pending_command_control"] = (
            pending_control if has_more_commands and pending_control else None
        )
        reset_stage_ids = tuple(dict.fromkeys(stage_id for command in review_feedback_commands for stage_id in self._review_feedback_reset_stage_ids(command)))
        invalidated_stage_ids: set[str] = set()
        if reset_stage_ids:
            passed = self._passed_stage_acceptance(state.run)
            invalidated_stage_ids = self._stage_invalidation_closure(
                state.run,
                passed_stage_ids=set(passed),
                reset_stage_ids=set(reset_stage_ids),
            )
            retained = {stage_id: result for stage_id, result in passed.items() if stage_id not in invalidated_stage_ids}
            retained_item_counts = self._inheritable_stage_item_counts(
                state.run,
                passed_stage_ids=set(retained),
                invalidated_stage_ids=invalidated_stage_ids,
            )
            snapshot_patch["stage_acceptance"] = retained
            snapshot_patch["stage_item_counts"] = retained_item_counts or None
        target_status: MissionStatus | None = None
        result: MissionSliceOutcome | None = None
        if not has_more_commands and pending_control.get("command_type") == "cancel":
            target_status = MissionStatus.CANCELLED
            result = MissionSliceOutcome.TERMINAL
            snapshot_patch["failure_reason"] = "cancelled_by_user"
            snapshot_patch["inflight_operation"] = None
            cancelled_inflight = self._cancelled_inflight_item(state.run)
            if (
                cancelled_inflight is not None
                and cancelled_inflight.operation_id is not None
                and not await self._operation_has_terminal(
                    mission_id=state.run.mission_id,
                    operation_id=cancelled_inflight.operation_id,
                    item_types=(cancelled_inflight.item_type,),
                )
            ):
                items.append(cancelled_inflight)
            items.append(
                MissionItemDraftPayload(
                    item_type="status_update",
                    phase=MissionItemPhase.CANCELLED,
                    producer="mission_runtime",
                    summary="Mission cancelled by durable command",
                    payload_json={},
                )
            )
        elif not has_more_commands and pending_control.get("command_type") == "pause":
            target_status = MissionStatus.WAITING
            result = MissionSliceOutcome.WAITING
            snapshot_patch["waiting_reason"] = "user_input"
            snapshot_patch["pending_request"] = {
                "request_id": str(pending_control.get("operation_id") or ""),
                "type": "user_pause",
                "summary": "任务已暂停；在对话中说明继续或补充要求后，问津会从当前进度恢复。",
            }
            items.append(
                MissionItemDraftPayload(
                    item_type="pause_request",
                    operation_id=str(pending_control.get("operation_id") or ""),
                    phase=MissionItemPhase.COMPLETED,
                    producer="mission_runtime",
                    summary="Mission paused by user",
                    payload_json={"reason": "user_input"},
                )
            )
        elif _status_value(state.run) == "running":
            target_status = MissionStatus.PLANNING
        elif (
            _status_value(state.run) == "waiting"
            and command_types - {"set_review_mode"}
        ):
            target_status = MissionStatus.PLANNING
        elif _status_value(state.run) == "waiting" and not has_more_commands:
            target_status = MissionStatus.WAITING
            result = MissionSliceOutcome.WAITING

        if target_status is MissionStatus.PLANNING:
            snapshot_patch["waiting_reason"] = None
            snapshot_patch["pending_request"] = None

        scalar_patch: dict[str, Any] = {
            "status": target_status,
            **({"review_mode": review_modes[-1]} if review_modes else {}),
        }
        if target_status is MissionStatus.CANCELLED:
            scalar_patch["active_subagent_count_delta"] = (
                -state.run.active_subagent_count
            )
        if target_status is MissionStatus.PLANNING and reset_stage_ids:
            scalar_patch["active_stage_id"] = reset_stage_ids[0]

        result_payload = await self.store.apply_commands(
            state.run.mission_id,
            MissionApplyCommandsPayload(
                expected_state_version=state.run.state_version,
                lease_owner=state.worker_id,
                lease_epoch=state.run.lease_epoch,
                through_command_seq=commands[-1].seq,
                items=items,
                snapshot_json=self._merge_snapshot(
                    state.run.snapshot_json,
                    snapshot_patch,
                ),
                patch=MissionRunPatchPayload(**scalar_patch),
            ),
        )
        state.run = result_payload.mission
        await publish_after_commit(self.events, self.clock, state.run)
        return result

    async def _load_unapplied_commands(
        self,
        run: MissionRunPayload,
    ) -> list[MissionItemPayload]:
        """Load one bounded command page; the driver drains later pages first."""

        through_seq = run.last_command_seq
        after_seq = run.last_applied_command_seq
        page = await self.store.list_items(
            run.mission_id,
            after_seq=after_seq,
            limit=90,
            item_type="command_received",
        )
        commands = [item for item in page if item.seq <= through_seq]
        if through_seq > run.last_applied_command_seq and not commands:
            raise RuntimeError(
                "durable Mission command cursor could not load its next page"
            )
        return commands

    @staticmethod
    def _review_feedback_reset_stage_ids(
        command: MissionItemPayload,
    ) -> tuple[str, ...]:
        raw = command.payload_json.get("reset_stage_ids")
        if not isinstance(raw, list) or not raw:
            raise ValueError("review_feedback requires reset_stage_ids")
        normalized = tuple(str(stage_id).strip() for stage_id in raw if isinstance(stage_id, str) and str(stage_id).strip())
        if len(normalized) != len(raw) or len(normalized) != len(set(normalized)):
            raise ValueError("review_feedback reset_stage_ids must be unique stage ids")
        return normalized

    async def _handle_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        if decision.kind == MissionDecisionKind.CONTINUE:
            if "item_counts" in decision.payload_json:
                await self._record_invalid_decision(
                    state,
                    decision,
                    "plan item_counts are not valid; declare quality_item_counts atomically with the passing understanding-stage quality decision",
                )
                return None
            snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
            projected_run = state.run.model_copy(update={"snapshot_json": snapshot})
            if not await self._ensure_stage_start_allowed(
                state,
                decision,
                mission=projected_run,
            ):
                return None
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type="plan",
                        operation_id=decision.decision_id,
                        phase=MissionItemPhase.PROGRESS,
                        stage_id=decision.stage_id,
                        producer="workspace_agent",
                        summary=decision.summary,
                        payload_json=decision.payload_json,
                    )
                ],
                snapshot=snapshot,
                patch=MissionRunPatchPayload(
                    status=MissionStatus.RUNNING,
                    active_stage_id=decision.stage_id,
                ),
            )
            return None

        if decision.kind == MissionDecisionKind.PAUSE:
            assert decision.pause_request is not None
            if state.run.pending_review_count > 0 and self._is_terminal_review_pause(decision.pause_request) and not self._missing_required_stage_acceptance(state.run) and not await self._unexposed_terminal_candidates(state.run):
                return await self._complete_under_fence(
                    state,
                    decision,
                    review_pending=True,
                )
            await self._pause_under_fence(state, decision.pause_request)
            return MissionSliceOutcome.WAITING

        if decision.kind == MissionDecisionKind.COMPLETE:
            return await self._complete_under_fence(state, decision)

        if decision.kind == MissionDecisionKind.FAIL:
            snapshot = self._decision_snapshot(
                state.run.snapshot_json,
                decision,
                extra={"failure_reason": str(decision.payload_json.get("failure_reason") or "repeated_failure")},
            )
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type="error",
                        operation_id=decision.decision_id,
                        phase=MissionItemPhase.FAILED,
                        producer="workspace_agent",
                        summary=decision.summary,
                        payload_json=decision.payload_json,
                    )
                ],
                snapshot=snapshot,
                patch=MissionRunPatchPayload(status=MissionStatus.FAILED),
            )
            return MissionSliceOutcome.TERMINAL

        assert decision.operation_id is not None
        if decision.kind is not MissionDecisionKind.QUALITY and not await self._ensure_stage_start_allowed(
            state,
            decision,
        ):
            return None
        if await self._operation_has_terminal(
            state.run.mission_id,
            decision.operation_id,
            item_types=self._decision_terminal_item_types(decision.kind),
        ):
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type="status_update",
                        operation_id=decision.operation_id,
                        phase=MissionItemPhase.COMPLETED,
                        producer="mission_runtime",
                        summary="Previously completed operation reused",
                        payload_json={"decision_id": decision.decision_id},
                    )
                ],
                snapshot=self._decision_snapshot(state.run.snapshot_json, decision),
                patch=self._stage_patch(decision.stage_id),
            )
            return None

        if decision.kind == MissionDecisionKind.TOOL:
            unavailable = self._unavailable_resource_dimensions(
                state.run,
                tool_operations=1,
            )
            if unavailable:
                return await self._fail_resource_budget(state, unavailable)
        if decision.kind == MissionDecisionKind.SUBAGENT:
            input_scope = decision.payload_json.get("input_scope")
            delta = resource_delta_for_item(
                item_type="subagent_spawned",
                payload_json={
                    "input_scope": input_scope if isinstance(input_scope, dict) else {}
                },
            )
            unavailable = self._unavailable_resource_dimensions(
                state.run,
                model_calls=delta.subagent_jobs,
                subagent_jobs=delta.subagent_jobs,
            )
            if unavailable:
                return await self._fail_resource_budget(state, unavailable)

        if decision.kind in {
            MissionDecisionKind.TOOL,
            MissionDecisionKind.SUBAGENT,
            MissionDecisionKind.QUALITY,
            MissionDecisionKind.REVIEW,
        }:
            state.tool_steps += 1

        if decision.kind == MissionDecisionKind.TOOL:
            return await self._run_tool_decision(state, decision)
        if decision.kind == MissionDecisionKind.SUBAGENT:
            return await self._run_subagent_decision(state, decision)
        if decision.kind == MissionDecisionKind.QUALITY:
            return await self._run_quality_decision(state, decision)
        if decision.kind == MissionDecisionKind.REVIEW:
            return await self._run_review_decision(state, decision)
        raise ValueError(f"Unsupported mission decision kind: {decision.kind}")

    async def _run_tool_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        tool_name = str(decision.payload_json.get("tool_name") or "").strip()
        arguments = decision.payload_json.get("arguments")
        if not tool_name or not isinstance(arguments, dict):
            await self._record_invalid_decision(state, decision, "tool_name and arguments are required")
            return None
        try:
            required_budget_seconds = await self._invoke_with_deadline(
                self.tools.required_budget_seconds(
                    state.run,
                    tool_name,
                ),
                state,
            )
            required_budget_seconds = float(required_budget_seconds)
            if (
                not isfinite(required_budget_seconds)
                or required_budget_seconds < 0
            ):
                raise ValueError("tool required budget must be finite and non-negative")
        except MissionLeaseLostError:
            raise
        except Exception:
            # Unknown/malformed tools still flow through the typed orchestrator
            # failure path. A policy lookup outage uses the conservative full
            # slice budget and is retried from the durable in-flight receipt.
            required_budget_seconds = self.limits.wall_time_seconds
        await self._begin_operation(
            state,
            decision,
            kind="tool",
            item_type="tool_call",
            payload_json={
                "tool_name": tool_name,
                "arguments": arguments,
                "required_budget_seconds": required_budget_seconds,
            },
        )
        if self._slice_time_below_operation_reserve(
            state,
            kind="tool",
            required_budget_seconds=required_budget_seconds,
        ):
            return None
        return await self._execute_tool_operation(
            state,
            operation_id=decision.operation_id or "",
            tool_name=tool_name,
            arguments=arguments,
            stage_id=decision.stage_id,
        )

    async def _run_subagent_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        task_summary = str(decision.payload_json.get("task_summary") or "").strip()
        input_scope = decision.payload_json.get("input_scope") or {}
        if not task_summary or not isinstance(input_scope, dict):
            await self._record_invalid_decision(state, decision, "task_summary and input_scope are required")
            return None
        recent_items = await self._recent_items(state.run)
        frozen_context = SubagentFrozenContext(
            context_checkpoint_ref=state.run.context_checkpoint_ref,
            context_checkpoint=dict(state.run.snapshot_json.get("context_checkpoint_summary") or {}),
            prior_output_briefs=tuple(str(item.summary)[:1000] for item in recent_items[-8:] if item.summary),
        )
        await self._begin_operation(
            state,
            decision,
            kind="subagent",
            item_type="subagent_spawned",
            payload_json={
                "task_summary": task_summary,
                "input_scope": input_scope,
                "frozen_context": frozen_context.model_dump(mode="json"),
            },
        )
        if self._slice_time_below_operation_reserve(state, kind="subagent"):
            return None
        return await self._execute_subagent_operation(
            state,
            operation_id=decision.operation_id or "",
            task_summary=task_summary,
            input_scope=input_scope,
            stage_id=decision.stage_id,
            frozen_context=frozen_context,
        )

    async def _run_quality_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        stage_id = decision.stage_id or state.run.active_stage_id
        candidate_refs = decision.payload_json.get("candidate_refs") or []
        assessment = decision.payload_json.get("assessment") or {}
        if not stage_id or not isinstance(candidate_refs, list) or not isinstance(assessment, dict):
            await self._record_invalid_decision(
                state,
                decision,
                "quality check requires stage_id, candidate_refs, and assessment",
            )
            return None
        recent_items = await self._recent_items(state.run, limit=100)
        prior_stage_result = (state.run.snapshot_json.get("stage_acceptance") or {}).get(stage_id)
        if isinstance(prior_stage_result, dict) and prior_stage_result.get("result") == "revise" and not self._has_stage_progress_since_last_quality(recent_items, stage_id=stage_id):
            next_action = str(prior_stage_result.get("next_action") or "revise_current_stage")
            await self._record_invalid_decision(
                state,
                decision,
                f"quality check cannot repeat before stage progress; complete next_action={next_action}",
            )
            return None
        reference_items = await self._reference_items(state.run.mission_id)
        try:
            outcome = await self._invoke_with_deadline(
                self.quality.evaluate(
                    StageQualityRequest(
                        mission=state.run,
                        operation_id=decision.operation_id or "",
                        stage_id=stage_id,
                        candidate_refs=[str(item) for item in candidate_refs],
                        assessment_json=assessment,
                        recent_items=recent_items,
                        reference_items=reference_items,
                        deadline_monotonic=state.deadline_monotonic,
                    )
                ),
                state,
            )
        except MissionLeaseLostError:
            raise
        except Exception as exc:
            terminal = await self._record_operation_failure(
                state,
                decision=decision,
                kind="quality",
                item_type="quality_check",
                producer="stage_quality",
                summary="Stage quality evaluation did not complete",
                exc=exc,
            )
            return MissionSliceOutcome.TERMINAL if terminal else None
        snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
        stage_acceptance = dict(snapshot.get("stage_acceptance") or {})
        stage_acceptance[stage_id] = dict(outcome.payload_json)
        snapshot_patch: dict[str, Any] = {"stage_acceptance": stage_acceptance}
        if outcome.verdict == StageQualityVerdict.PASS:
            raw_item_counts = decision.payload_json.get("item_counts") or {}
            if not isinstance(raw_item_counts, dict):
                await self._record_invalid_decision(
                    state,
                    decision,
                    "quality item_counts must be an object",
                )
                return None
            required_sources = self._item_count_sources_unlocked_by_stage(
                state.run,
                stage_id=stage_id,
                projected_stage_results=stage_acceptance,
            )
            declared_sources = {str(key) for key in raw_item_counts}
            missing_sources = sorted(required_sources - declared_sources)
            unexpected_sources = sorted(declared_sources - required_sources)
            if missing_sources or unexpected_sources:
                details = []
                if missing_sources:
                    details.append("missing=" + ",".join(missing_sources))
                if unexpected_sources:
                    details.append("not_unlocked_by_stage=" + ",".join(unexpected_sources))
                await self._record_invalid_decision(
                    state,
                    decision,
                    f"quality_item_counts must exactly match dynamic workloads unlocked by {stage_id}: {'; '.join(details)}",
                )
                return None
            if raw_item_counts:
                try:
                    snapshot_patch["stage_item_counts"] = self._pin_stage_item_counts(
                        state.run,
                        raw_item_counts,
                        projected_stage_results=stage_acceptance,
                    )
                except ValueError as exc:
                    await self._record_invalid_decision(state, decision, str(exc))
                    return None
        snapshot = self._merge_snapshot(
            snapshot,
            snapshot_patch,
        )
        items = [
            MissionItemDraftPayload(
                item_type="quality_check",
                operation_id=decision.operation_id,
                phase=MissionItemPhase.COMPLETED,
                stage_id=stage_id,
                producer="stage_quality",
                summary=outcome.summary,
                payload_json={"verdict": outcome.verdict.value, **outcome.payload_json},
            )
        ]
        patch = self._stage_patch(stage_id)
        result: MissionSliceOutcome | None = None
        if outcome.verdict == StageQualityVerdict.ASK_USER:
            assert outcome.pause_request is not None
            pause_request = self._scoped_pause_request(state.run, outcome.pause_request)
            snapshot = self._pause_snapshot(snapshot, pause_request)
            items.append(self._pause_item(pause_request))
            patch = self._stage_patch(stage_id, status=MissionStatus.WAITING)
            result = MissionSliceOutcome.WAITING
        elif outcome.verdict == StageQualityVerdict.STOP:
            snapshot = self._merge_snapshot(snapshot, {"failure_reason": "repeated_failure"})
            patch = self._stage_patch(stage_id, status=MissionStatus.FAILED)
            result = MissionSliceOutcome.TERMINAL
        elif outcome.verdict == StageQualityVerdict.REVISE:
            snapshot = self._merge_snapshot(snapshot, {"next_actions": ["revise_current_stage"]})
        else:
            snapshot = self._merge_snapshot(snapshot, {"next_actions": ["advance_stage"]})
        await self._append(state, items=items, snapshot=snapshot, patch=patch)
        return result

    @staticmethod
    def _has_stage_progress_since_last_quality(
        recent_items: list[MissionItemPayload],
        *,
        stage_id: str,
    ) -> bool:
        quality_items = [item for item in recent_items if item.item_type == "quality_check" and item.stage_id == stage_id]
        if not quality_items:
            return True
        last_quality = max(quality_items, key=lambda item: item.seq)
        previous_refs = {str(ref) for ref in last_quality.payload_json.get("artifact_refs") or () if isinstance(ref, str) and ref.strip()}
        return any(
            item.seq > last_quality.seq
            and item.stage_id == stage_id
            and item.item_type == "artifact"
            and item.phase == MissionItemPhase.COMPLETED
            and item.payload_json.get("verified") is True
            and bool(str(item.payload_json.get("reference_id") or "").strip())
            and str(item.payload_json.get("reference_id") or "") not in previous_refs
            for item in recent_items
        )

    async def _run_review_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        stage_id = decision.stage_id or state.run.active_stage_id
        stage_results = state.run.snapshot_json.get("stage_acceptance")
        stage_result = stage_results.get(stage_id) if stage_id and isinstance(stage_results, dict) else None
        if not isinstance(stage_result, dict) or stage_result.get("result") != "pass":
            await self._record_invalid_decision(
                state,
                decision,
                "review can only expose an internal candidate after its stage acceptance passed",
            )
            return None
        accepted_candidate_refs = [str(ref) for ref in stage_result.get("artifact_refs") or () if isinstance(ref, str) and ref.strip()]
        if not accepted_candidate_refs:
            await self._record_invalid_decision(
                state,
                decision,
                "passed stage acceptance has no verified candidate refs",
            )
            return None
        try:
            batch = await self._invoke_with_deadline(
                self.review_candidates.build_candidates(
                    ReviewCandidateRequest(
                        mission=state.run,
                        operation_id=decision.operation_id or "",
                        stage_id=stage_id,
                        candidate_json=decision.payload_json,
                        accepted_candidate_refs=accepted_candidate_refs,
                        reference_items=await self._reference_items(state.run.mission_id),
                        deadline_monotonic=state.deadline_monotonic,
                    )
                ),
                state,
            )
        except MissionLeaseLostError:
            raise
        except Exception as exc:
            terminal = await self._record_operation_failure(
                state,
                decision=decision,
                kind="review",
                item_type="error",
                producer="review_candidate",
                summary="Review candidate generation did not complete",
                exc=exc,
            )
            return MissionSliceOutcome.TERMINAL if terminal else None
        snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
        result = await self.store.create_review_items(
            state.run.mission_id,
            MissionReviewItemsCreatePayload(
                expected_state_version=state.run.state_version,
                lease_owner=state.worker_id,
                lease_epoch=state.run.lease_epoch,
                review_items=batch.items,
                items=[
                    MissionItemDraftPayload(
                        item_type="status_update",
                        operation_id=decision.operation_id,
                        phase=MissionItemPhase.COMPLETED,
                        producer="review_candidate",
                        summary=batch.summary,
                        payload_json={
                            "review_item_ids": [item.review_item_id for item in batch.items],
                        },
                    )
                ],
                snapshot_json=snapshot,
                patch=self._stage_patch(stage_id),
            ),
        )
        state.run = result.mission
        await publish_after_commit(self.events, self.clock, state.run)
        return None

    async def _ensure_stage_start_allowed(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
        *,
        mission: MissionRunPayload | None = None,
    ) -> bool:
        guarded_mission = mission or state.run
        stage_id = decision.stage_id or state.run.active_stage_id
        if not stage_id:
            if not state.run.runtime_context_json.get("stage_contracts"):
                return True
            await self._record_invalid_decision(
                state,
                decision,
                f"{decision.kind.value} requires a pinned stage_id",
            )
            return False
        try:
            allowed, missing = await self.quality.can_start(
                guarded_mission,
                stage_id,
            )
        except Exception as exc:
            await self._record_invalid_decision(
                state,
                decision,
                f"stage guard could not resolve {stage_id}: {type(exc).__name__}",
            )
            return False
        if allowed:
            return True
        await self._record_invalid_decision(
            state,
            decision,
            "stage prerequisites have not passed: " + ", ".join(missing),
        )
        return False

    async def _begin_operation(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
        *,
        kind: str,
        item_type: str,
        payload_json: dict[str, Any],
    ) -> None:
        operation_id = decision.operation_id or ""
        call_item_seq = state.run.last_item_seq + 1
        snapshot = self._decision_snapshot(
            state.run.snapshot_json,
            decision,
            extra={
                "inflight_operation": {
                    "operation_id": operation_id,
                    "kind": kind,
                    "call_item_seq": call_item_seq,
                    **(
                        {"active_seconds": 0.0, "quantum_count": 0}
                        if kind == "subagent"
                        else {}
                    ),
                    **(
                        {
                            "required_budget_seconds": payload_json.get(
                                "required_budget_seconds"
                            )
                        }
                        if payload_json.get("required_budget_seconds") is not None
                        else {}
                    ),
                }
            },
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type=item_type,
                    operation_id=operation_id,
                    phase=MissionItemPhase.STARTED,
                    stage_id=decision.stage_id,
                    producer="workspace_agent",
                    summary=decision.summary,
                    risk_level=_risk(decision.risk_level),
                    payload_json=payload_json,
                )
            ],
            snapshot=snapshot,
            patch=self._stage_patch(
                decision.stage_id,
                active_subagent_count_delta=1 if kind == "subagent" else 0,
            ),
        )

    async def _recover_inflight_operation(
        self,
        state: _SliceState,
    ) -> tuple[bool, MissionSliceOutcome | None]:
        inflight = state.run.snapshot_json.get("inflight_operation")
        if not isinstance(inflight, dict):
            return False, None
        if state.tool_steps >= self.limits.max_tool_steps:
            return False, None
        operation_id = str(inflight.get("operation_id") or "")
        kind = str(inflight.get("kind") or "")
        item_seq = int(inflight.get("call_item_seq") or 0)
        call_item = await self._load_item(state.run.mission_id, item_seq)
        if call_item is None or call_item.operation_id != operation_id:
            await self._clear_invalid_inflight(state, operation_id)
            return True, None
        state.tool_steps += 1
        if kind == "tool":
            tool_name = str(call_item.payload_json.get("tool_name") or "")
            arguments = call_item.payload_json.get("arguments") or {}
            if not tool_name or not isinstance(arguments, dict):
                await self._clear_invalid_inflight(state, operation_id)
                return True, None
            outcome = await self._execute_tool_operation(
                state,
                operation_id=operation_id,
                tool_name=tool_name,
                arguments=arguments,
                stage_id=call_item.stage_id,
            )
            return True, outcome
        if kind == "subagent":
            task_summary = str(call_item.payload_json.get("task_summary") or "")
            input_scope = call_item.payload_json.get("input_scope") or {}
            raw_frozen_context = call_item.payload_json.get("frozen_context")
            if not task_summary or not isinstance(input_scope, dict) or not isinstance(raw_frozen_context, dict):
                await self._clear_invalid_inflight(state, operation_id)
                return True, None
            try:
                frozen_context = SubagentFrozenContext.model_validate(raw_frozen_context)
            except ValueError:
                await self._clear_invalid_inflight(state, operation_id)
                return True, None
            outcome = await self._execute_subagent_operation(
                state,
                operation_id=operation_id,
                task_summary=task_summary,
                input_scope=input_scope,
                stage_id=call_item.stage_id,
                frozen_context=frozen_context,
            )
            return True, outcome
        await self._clear_invalid_inflight(state, operation_id)
        return True, None

    async def _execute_tool_operation(
        self,
        state: _SliceState,
        *,
        operation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        stage_id: str | None,
    ) -> MissionSliceOutcome | None:
        recent_items = await self._recent_items(state.run)
        try:
            outcome = await self._invoke_with_deadline(
                self.tools.execute(
                    ToolExecutionRequest(
                        mission=state.run,
                        operation_id=operation_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        stage_id=stage_id,
                        recent_items=recent_items,
                        deadline_monotonic=state.deadline_monotonic,
                    )
                ),
                state,
            )
        except MissionLeaseLostError:
            raise
        except Exception as exc:
            outcome = self._failed_port_outcome("Tool operation did not complete", exc)
        return await self._finish_port_operation(
            state,
            operation_id=operation_id,
            kind="tool",
            item_type="tool_result",
            stage_id=stage_id,
            producer="tool_orchestrator",
            outcome=outcome,
        )

    async def _execute_subagent_operation(
        self,
        state: _SliceState,
        *,
        operation_id: str,
        task_summary: str,
        input_scope: dict[str, Any],
        stage_id: str | None,
        frozen_context: SubagentFrozenContext,
    ) -> MissionSliceOutcome | None:
        inflight = state.run.snapshot_json.get("inflight_operation")
        inflight_snapshot = dict(inflight) if isinstance(inflight, dict) else {}
        try:
            active_seconds = max(
                0.0,
                float(inflight_snapshot.get("active_seconds") or 0.0),
            )
        except (TypeError, ValueError):
            active_seconds = 0.0
        remaining_active_seconds = (
            self.limits.subagent_operation_time_seconds - active_seconds
        )
        if remaining_active_seconds <= 0:
            return await self._finish_port_operation(
                state,
                operation_id=operation_id,
                kind="subagent",
                item_type="subagent_completed",
                stage_id=stage_id,
                producer="subagent_runtime",
                outcome=MissionPortOutcome(
                    status=MissionPortOutcomeStatus.FAILED,
                    summary="Subagent active execution budget was exhausted",
                    payload_json={
                        "active_seconds": active_seconds,
                        "budget_seconds": self.limits.subagent_operation_time_seconds,
                    },
                ),
            )
        quantum_started = self.clock.monotonic()
        quantum_deadline = min(
            state.deadline_monotonic,
            quantum_started + remaining_active_seconds,
        )
        request = SubagentExecutionRequest(
            mission=state.run,
            operation_id=operation_id,
            task_summary=task_summary,
            input_scope=input_scope,
            stage_id=stage_id,
            frozen_context=frozen_context,
            deadline_monotonic=quantum_deadline,
        )
        try:
            outcome = await self._invoke_with_deadline(
                self.subagents.run(request),
                state,
            )
        except MissionLeaseLostError:
            raise
        except Exception as exc:
            adopted = await self.subagents.adopt_terminal(request)
            if adopted is not None:
                outcome = adopted
            else:
                if await self._reconcile_model_call_ledger(state):
                    return MissionSliceOutcome.TERMINAL
                outcome = self._failed_port_outcome(
                    "Subagent did not complete",
                    exc,
                )
        if await self._reconcile_model_call_ledger(state):
            return MissionSliceOutcome.TERMINAL
        elapsed = max(0.0, self.clock.monotonic() - quantum_started)
        if outcome.status is MissionPortOutcomeStatus.YIELDED:
            current_inflight = state.run.snapshot_json.get("inflight_operation")
            if not isinstance(current_inflight, dict):
                return None
            updated_inflight = dict(current_inflight)
            updated_active_seconds = min(
                self.limits.subagent_operation_time_seconds,
                active_seconds + elapsed,
            )
            updated_inflight["active_seconds"] = updated_active_seconds
            updated_inflight["quantum_count"] = (
                int(updated_inflight.get("quantum_count") or 0) + 1
            )
            pending_reasons = outcome.payload_json.get("pending_reasons")
            if isinstance(pending_reasons, dict):
                updated_inflight["pending_reasons"] = dict(pending_reasons)
            active_budget_cannot_admit_model = (
                self.limits.subagent_operation_time_seconds
                - updated_active_seconds
                < SUBAGENT_MODEL_REQUEST_TIMEOUT_SECONDS
                + MISSION_MODEL_COMPLETION_MARGIN_SECONDS
            )
            deadline_only = (
                isinstance(pending_reasons, dict)
                and bool(pending_reasons)
                and set(pending_reasons.values()) == {"deadline_reached"}
            )
            if deadline_only and active_budget_cannot_admit_model:
                return await self._finish_port_operation(
                    state,
                    operation_id=operation_id,
                    kind="subagent",
                    item_type="subagent_completed",
                    stage_id=stage_id,
                    producer="subagent_runtime",
                    outcome=MissionPortOutcome(
                        status=MissionPortOutcomeStatus.FAILED,
                        summary="Subagent active execution budget cannot admit another model turn",
                        payload_json={
                            **outcome.payload_json,
                            "active_seconds": updated_active_seconds,
                            "budget_seconds": self.limits.subagent_operation_time_seconds,
                        },
                    ),
                )
            await self._append(
                state,
                items=[],
                snapshot=self._merge_snapshot(
                    state.run.snapshot_json,
                    {"inflight_operation": updated_inflight},
                ),
            )
            return MissionSliceOutcome.YIELDED
        if outcome.status is MissionPortOutcomeStatus.FAILED:
            adopted = await self.subagents.adopt_terminal(request)
            if adopted is not None:
                outcome = adopted
        return await self._finish_port_operation(
            state,
            operation_id=operation_id,
            kind="subagent",
            item_type="subagent_completed",
            stage_id=stage_id,
            producer="subagent_runtime",
            outcome=outcome,
        )

    async def _finish_port_operation(
        self,
        state: _SliceState,
        *,
        operation_id: str,
        kind: str,
        item_type: str,
        stage_id: str | None,
        producer: str,
        outcome: MissionPortOutcome,
    ) -> MissionSliceOutcome | None:
        latest = await self.store.get(state.run.mission_id)
        if latest is not None and latest.lease_owner == state.worker_id and latest.lease_epoch == state.run.lease_epoch and _status_value(latest) == _status_value(state.run):
            state.run = latest
        if outcome.status == MissionPortOutcomeStatus.WAITING:
            assert outcome.pause_request is not None
            pause_request = self._scoped_pause_request(state.run, outcome.pause_request)
            snapshot = self._pause_snapshot(
                self._merge_snapshot(state.run.snapshot_json, outcome.snapshot_patch),
                pause_request,
            )
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type=item_type,
                        operation_id=operation_id,
                        phase=MissionItemPhase.PROGRESS,
                        stage_id=stage_id,
                        producer=producer,
                        summary=outcome.summary,
                        risk_level=_risk(outcome.risk_level),
                        payload_json=outcome.payload_json,
                        payload_ref=outcome.payload_ref,
                    ),
                    self._pause_item(pause_request),
                ],
                snapshot=snapshot,
                patch=MissionRunPatchPayload(
                    status=MissionStatus.WAITING,
                    active_subagent_count_delta=-1 if kind == "subagent" else 0,
                ),
            )
            return MissionSliceOutcome.WAITING

        phase = MissionItemPhase.COMPLETED if outcome.status == MissionPortOutcomeStatus.COMPLETED else MissionItemPhase.FAILED
        snapshot = self._merge_snapshot(state.run.snapshot_json, outcome.snapshot_patch)
        snapshot.pop("inflight_operation", None)
        failure_budget_exhausted = False
        failure_count = 0
        if outcome.status == MissionPortOutcomeStatus.FAILED:
            stage_key = stage_id or "__mission__"
            raw_guard = snapshot.get("operation_failure_guard")
            guard = dict(raw_guard) if isinstance(raw_guard, dict) else {}
            raw_stage_guard = guard.get(stage_key)
            stage_guard = dict(raw_stage_guard) if isinstance(raw_stage_guard, dict) else {}
            failure_count = int(stage_guard.get("failure_count") or 0) + 1
            guard[stage_key] = {
                "failure_count": failure_count,
                "last_operation_id": operation_id,
                "last_operation_kind": kind,
                "last_summary": outcome.summary[:500],
            }
            failure_budget_exhausted = failure_count >= self.limits.max_operation_failures_per_stage
            snapshot = self._merge_snapshot(
                snapshot,
                {
                    "degraded_reason": "tool_partial",
                    "operation_failure_guard": guard,
                    "last_error": {
                        "operation_id": operation_id,
                        "summary": outcome.summary[:500],
                    },
                    "next_actions": None if failure_budget_exhausted else ["replan_after_operation_failure"],
                    "failure_reason": "stage_execution_failure_budget_exhausted" if failure_budget_exhausted else None,
                },
            )
        items = [
            MissionItemDraftPayload(
                item_type=item_type,
                operation_id=operation_id,
                phase=phase,
                stage_id=stage_id,
                producer=producer,
                summary=outcome.summary,
                risk_level=_risk(outcome.risk_level),
                payload_json=outcome.payload_json,
                payload_ref=outcome.payload_ref,
            ),
        ]
        if failure_budget_exhausted:
            items.append(
                MissionItemDraftPayload(
                    item_type="error",
                    operation_id=operation_id,
                    phase=MissionItemPhase.FAILED,
                    stage_id=stage_id,
                    producer="mission_runtime",
                    summary="当前阶段多次执行失败，任务已停止并保留已有成果。",
                    payload_json={
                        "failure_count": failure_count,
                        "failure_limit": self.limits.max_operation_failures_per_stage,
                        "recoverable": False,
                    },
                )
            )
        await self._append(
            state,
            items=items,
            snapshot=snapshot,
            patch=MissionRunPatchPayload(
                status=MissionStatus.FAILED if failure_budget_exhausted else None,
                active_subagent_count_delta=-1 if kind == "subagent" else 0,
            ),
        )
        return MissionSliceOutcome.TERMINAL if failure_budget_exhausted else None

    async def _pause_under_fence(
        self,
        state: _SliceState,
        request: MissionPauseRequest,
    ) -> None:
        request = self._scoped_pause_request(state.run, request)
        await self._append(
            state,
            items=[self._pause_item(request)],
            snapshot=self._pause_snapshot(state.run.snapshot_json, request),
            patch=MissionRunPatchPayload(status=MissionStatus.WAITING),
        )

    async def _record_operation_failure(
        self,
        state: _SliceState,
        *,
        decision: MissionAgentDecision,
        kind: str,
        item_type: str,
        producer: str,
        summary: str,
        exc: BaseException,
    ) -> bool:
        operation_id = decision.operation_id or decision.decision_id
        snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
        stage_key = decision.stage_id or state.run.active_stage_id or "__mission__"
        raw_guard = snapshot.get("operation_failure_guard")
        guard = dict(raw_guard) if isinstance(raw_guard, dict) else {}
        raw_stage_guard = guard.get(stage_key)
        stage_guard = (
            dict(raw_stage_guard) if isinstance(raw_stage_guard, dict) else {}
        )
        failure_count = int(stage_guard.get("failure_count") or 0) + 1
        guard[stage_key] = {
            "failure_count": failure_count,
            "last_operation_id": operation_id,
            "last_operation_kind": kind,
            "last_summary": summary[:500],
        }
        failure_budget_exhausted = (
            failure_count >= self.limits.max_operation_failures_per_stage
        )
        snapshot = self._merge_snapshot(
            snapshot,
            {
                "degraded_reason": "tool_partial",
                "operation_failure_guard": guard,
                "last_error": {
                    "operation_id": operation_id,
                    "error_type": type(exc).__name__,
                    "detail": str(exc)[:500],
                },
                "next_actions": (
                    None
                    if failure_budget_exhausted
                    else ["replan_after_operation_failure"]
                ),
                "failure_reason": (
                    "stage_execution_failure_budget_exhausted"
                    if failure_budget_exhausted
                    else None
                ),
            },
        )
        items = [
            MissionItemDraftPayload(
                item_type=item_type,
                operation_id=operation_id,
                phase=MissionItemPhase.FAILED,
                stage_id=decision.stage_id,
                producer=producer,
                summary=summary,
                payload_json={
                    "error_type": type(exc).__name__,
                    "detail": str(exc)[:500],
                },
            )
        ]
        if failure_budget_exhausted:
            items.append(
                MissionItemDraftPayload(
                    item_type="error",
                    operation_id=operation_id,
                    phase=MissionItemPhase.FAILED,
                    stage_id=decision.stage_id,
                    producer="mission_runtime",
                    summary="当前阶段多次执行失败，任务已停止并保留已有成果。",
                    payload_json={
                        "failure_count": failure_count,
                        "failure_limit": self.limits.max_operation_failures_per_stage,
                        "recoverable": False,
                    },
                )
            )
        await self._append(
            state,
            items=items,
            snapshot=snapshot,
            patch=self._stage_patch(
                decision.stage_id,
                status=(
                    MissionStatus.FAILED if failure_budget_exhausted else None
                ),
            ),
        )
        return failure_budget_exhausted

    async def _record_invalid_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
        detail: str,
    ) -> None:
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="error",
                    operation_id=decision.decision_id,
                    phase=MissionItemPhase.FAILED,
                    producer="mission_runtime",
                    summary="Agent decision did not satisfy the runtime contract",
                    payload_json={"kind": decision.kind.value, "detail": detail},
                )
            ],
            snapshot=self._merge_snapshot(
                state.run.snapshot_json,
                {
                    "last_error": {"kind": "invalid_agent_decision", "detail": detail},
                    "next_actions": ["repair_structured_decision"],
                },
            ),
        )

    async def _complete_under_fence(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
        *,
        review_pending: bool = False,
    ) -> MissionSliceOutcome | None:
        missing_stages = self._missing_required_stage_acceptance(state.run)
        if missing_stages:
            await self._record_invalid_decision(
                state,
                decision,
                "completion requires passed StageAcceptance results: " + ", ".join(missing_stages),
            )
            return None
        unexposed_candidates = await self._unexposed_terminal_candidates(state.run)
        if unexposed_candidates:
            await self._record_invalid_decision(
                state,
                decision,
                "completion requires user-reviewable terminal outputs for the selected target: " + ", ".join(unexposed_candidates),
            )
            return None
        summary = "最终成果已准备好，等待你的确认" if review_pending else decision.summary
        snapshot_extra = None
        if review_pending:
            snapshot_extra = {
                "last_agent_decision": {
                    "decision_id": decision.decision_id,
                    "kind": MissionDecisionKind.COMPLETE.value,
                    "summary": summary,
                }
            }
        snapshot = self._decision_snapshot(
            state.run.snapshot_json,
            decision,
            extra=snapshot_extra,
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="status_update",
                    operation_id=decision.decision_id,
                    phase=MissionItemPhase.COMPLETED,
                    producer=("mission_runtime" if review_pending else "workspace_agent"),
                    summary=summary,
                    payload_json=({"review_pending": True} if review_pending else decision.payload_json),
                )
            ],
            snapshot=snapshot,
            patch=MissionRunPatchPayload(status=MissionStatus.COMPLETED),
        )
        return MissionSliceOutcome.COMPLETED

    @staticmethod
    def _is_terminal_review_pause(request: MissionPauseRequest) -> bool:
        if request.reason == "review":
            return True
        return request.reason == "approval" and bool(str(request.pending_request.get("review_item_id") or "").strip())

    @staticmethod
    def _missing_required_stage_acceptance(run: MissionRunPayload) -> list[str]:
        raw_required = run.runtime_context_json.get("required_stage_ids")
        if not isinstance(raw_required, list):
            raw_required = run.snapshot_json.get("required_stage_ids")
        if not isinstance(raw_required, list) or not raw_required:
            return []
        acceptance = run.snapshot_json.get("stage_acceptance")
        results = acceptance if isinstance(acceptance, dict) else {}
        contracts = _pinned_stage_contracts(run)
        item_counts = _stage_item_counts(run.snapshot_json)
        missing: list[str] = []
        for raw_stage_id in raw_required:
            contract_stage_id = str(raw_stage_id).strip()
            contract = contracts.get(contract_stage_id)
            if not contract_stage_id:
                missing.append("<blank-stage-id>")
                continue
            if contract is None or contract.instantiation.mode == "single":
                result = results.get(contract_stage_id)
                if not isinstance(result, dict) or result.get("result") != "pass":
                    missing.append(contract_stage_id)
                continue
            source_key = str(contract.instantiation.source_context_key or "")
            item_count = item_counts.get(source_key)
            if item_count is None:
                missing.append(f"{contract_stage_id}[item_count:{source_key}]")
                continue
            for index in range(1, item_count + 1):
                stage_id = resolve_stage_instance(
                    contract,
                    sequence_index=index,
                    total_items=item_count,
                ).stage_id
                result = results.get(stage_id)
                if not isinstance(result, dict) or result.get("result") != "pass":
                    missing.append(stage_id)
        return missing

    async def _unexposed_terminal_candidates(
        self,
        run: MissionRunPayload,
    ) -> list[str]:
        raw_output_kinds = run.runtime_context_json.get("terminal_output_kinds")
        terminal_output_kinds = {str(value) for value in raw_output_kinds or () if isinstance(value, str) and value.strip()}
        if not terminal_output_kinds:
            return []
        acceptance = run.snapshot_json.get("stage_acceptance")
        stage_results = acceptance if isinstance(acceptance, dict) else {}
        accepted_refs = {str(ref) for result in stage_results.values() if isinstance(result, dict) and result.get("result") == "pass" for ref in result.get("artifact_refs") or () if isinstance(ref, str) and ref.strip()}
        reference_items = await self._reference_items(
            run.mission_id,
            maximum=1000,
        )
        candidate_kinds: dict[str, str] = {}
        for item in reference_items:
            if item.item_type != "artifact" or item.payload_json.get("verified") is not True:
                continue
            candidate_ref = str(item.payload_json.get("reference_id") or "")
            metadata = item.payload_json.get("metadata")
            artifact_kind = str(metadata.get("artifact_kind") or "") if isinstance(metadata, dict) else ""
            if candidate_ref in accepted_refs and artifact_kind:
                candidate_kinds[candidate_ref] = artifact_kind
        required_refs = {ref for ref, artifact_kind in candidate_kinds.items() if artifact_kind in terminal_output_kinds}
        present_kinds = {candidate_kinds[ref] for ref in required_refs}
        missing_kinds = sorted(terminal_output_kinds - present_kinds)
        review_items = await self.store.list_review_items(run.mission_id)
        exposed_refs = {str(item.preview_json.get("candidate_ref") or "") for item in review_items if item.status.value in {"pending", "accepted", "committed"}}
        return [
            *(f"<terminal-output:{kind}>" for kind in missing_kinds),
            *sorted(required_refs - exposed_refs),
        ]

    @staticmethod
    def _item_count_sources_unlocked_by_stage(
        run: MissionRunPayload,
        *,
        stage_id: str,
        projected_stage_results: dict[str, Any],
    ) -> set[str]:
        existing_counts = _stage_item_counts(run.snapshot_json)
        contracts = _pinned_stage_contracts(run)
        unlocked: set[str] = set()
        source_keys = {str(contract.instantiation.source_context_key) for contract in contracts.values() if contract.instantiation.mode == "per_item" and contract.instantiation.source_context_key}
        for source_key in source_keys:
            if source_key in existing_counts:
                continue
            prerequisite_ids = MissionRuntime._item_count_source_stage_ids(
                contracts,
                source_key,
            )
            if stage_id not in prerequisite_ids:
                continue
            if all(isinstance(projected_stage_results.get(prerequisite), dict) and projected_stage_results[prerequisite].get("result") == "pass" for prerequisite in prerequisite_ids):
                unlocked.add(source_key)
        return unlocked

    @staticmethod
    def _pin_stage_item_counts(
        run: MissionRunPayload,
        raw_counts: dict[str, Any],
        *,
        projected_stage_results: dict[str, Any],
    ) -> dict[str, int]:
        if not isinstance(raw_counts, dict) or not raw_counts:
            raise ValueError("quality item_counts must be a non-empty object")
        contracts = _pinned_stage_contracts(run)
        contracts_by_source: dict[str, list[StageAcceptanceContract]] = {}
        for contract in contracts.values():
            source_key = contract.instantiation.source_context_key
            if contract.instantiation.mode == "per_item" and source_key:
                contracts_by_source.setdefault(source_key, []).append(contract)
        next_counts = _stage_item_counts(run.snapshot_json)
        for raw_key, raw_value in raw_counts.items():
            source_key = str(raw_key).strip()
            related = contracts_by_source.get(source_key)
            if not related:
                raise ValueError(f"item_counts contains unknown stage source: {source_key or '<blank>'}")
            if isinstance(raw_value, bool) or not isinstance(raw_value, int) or not 1 <= raw_value <= 100:
                raise ValueError(f"item_counts.{source_key} must be an integer from 1 to 100")
            existing = next_counts.get(source_key)
            if existing is not None and existing != raw_value:
                raise ValueError(f"item_counts.{source_key} is immutable after it is pinned")
            observed_instance = any(stage_id_matches_contract(contract, stage_id) for contract in related for stage_id in projected_stage_results)
            if existing is None and observed_instance:
                raise ValueError(f"item_counts.{source_key} must be pinned before per-item work begins")
            prerequisite_ids = MissionRuntime._item_count_source_stage_ids(
                contracts,
                source_key,
            )
            missing_prerequisites = sorted(stage_id for stage_id in prerequisite_ids if not isinstance(projected_stage_results.get(stage_id), dict) or projected_stage_results[stage_id].get("result") != "pass")
            if missing_prerequisites:
                raise ValueError(f"item_counts.{source_key} requires passed stages: " + ", ".join(missing_prerequisites))
            next_counts[source_key] = raw_value
        return next_counts

    async def _record_loop_failure(
        self,
        state: _SliceState,
        exc: BaseException,
    ) -> bool:
        guard = state.run.snapshot_json.get("loop_guard")
        current_guard = guard if isinstance(guard, dict) else {}
        transient = is_transient_model_error(exc)
        protocol_failure = isinstance(exc, MissionAgentProtocolError)
        failures = int(current_guard.get("consecutive_failures") or 0) + (0 if transient else 1)
        transient_failures = int(current_guard.get("transient_failures") or 0) + (1 if transient else 0)
        terminal = transient_failures >= self.limits.max_transient_failures if transient else failures >= self.limits.max_consecutive_failures
        snapshot = self._merge_snapshot(
            state.run.snapshot_json,
            {
                "loop_guard": {
                    "consecutive_failures": failures,
                    "transient_failures": transient_failures,
                },
                "last_error": {
                    "kind": ("transient_model_failure" if transient else "agent_protocol_failure" if protocol_failure else "agent_step_failure"),
                    "error_type": type(exc).__name__,
                    "detail": str(exc)[:500],
                },
                "next_actions": ([] if terminal else ["retry_agent_step_after_backoff" if transient else "repair_structured_decision" if protocol_failure else "retry_agent_step"]),
            },
        )
        if terminal:
            snapshot = self._merge_snapshot(
                snapshot,
                {"failure_reason": ("model_service_unavailable" if transient else "repeated_failure")},
            )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="error",
                    phase=MissionItemPhase.FAILED,
                    producer="mission_runtime",
                    summary=(
                        "Model service remained unavailable; Mission stopped with its partial work preserved"
                        if transient and terminal
                        else "Model service was temporarily unavailable; Mission will retry"
                        if transient
                        else "Mission action needs schema repair; Mission will retry"
                        if protocol_failure
                        else "Mission agent step did not complete"
                    ),
                    payload_json={
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:500],
                        "attempt": transient_failures if transient else failures,
                        "recoverable": not terminal,
                    },
                )
            ],
            snapshot=snapshot,
            patch=MissionRunPatchPayload(status=MissionStatus.FAILED if terminal else None),
        )
        return terminal

    async def _checkpoint_and_yield(
        self,
        state: _SliceState,
        *,
        reason: str,
        command_hint: str | None,
        retry_delay_seconds: int = 0,
    ) -> MissionSliceTelemetry:
        if (
            retry_delay_seconds == 0
            and reason == "subagent_quantum_yielded"
        ):
            inflight = state.run.snapshot_json.get("inflight_operation")
            pending_reasons = (
                inflight.get("pending_reasons")
                if isinstance(inflight, dict)
                else None
            )
            if (
                isinstance(pending_reasons, dict)
                and "capacity_saturated" in pending_reasons.values()
            ):
                retry_delay_seconds = MISSION_SUBAGENT_CAPACITY_RETRY_SECONDS
        checkpoint_seq = state.run.last_item_seq + 1
        checkpoint_ref = f"mission-item://{state.run.mission_id}/{checkpoint_seq}"
        recent_items = await self._recent_items(state.run, limit=100)
        checkpoint_summary = self._compile_context_checkpoint(
            state.run,
            recent_items,
            reason=reason,
        )
        snapshot = self._merge_snapshot(
            state.run.snapshot_json,
            {
                "context_checkpoint_summary": checkpoint_summary,
            },
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="context_checkpoint",
                    phase=MissionItemPhase.COMPLETED,
                    producer="mission_runtime",
                    summary="Mission checkpoint saved at a safe boundary",
                    payload_json=checkpoint_summary,
                )
            ],
            snapshot=snapshot,
            patch=MissionRunPatchPayload(context_checkpoint_ref=checkpoint_ref),
        )
        state.run = await self.store.release_lease(
            state.run.mission_id,
            MissionLeaseReleasePayload(
                worker_id=state.worker_id,
                lease_epoch=state.run.lease_epoch,
                expected_state_version=state.run.state_version,
                next_wakeup_at=self.clock.now() + timedelta(seconds=retry_delay_seconds),
            ),
        )
        await publish_after_commit(self.events, self.clock, state.run)
        continuation = await self._publish_wakeup(
            state.run.mission_id,
            command_hint=command_hint,
            delay_seconds=retry_delay_seconds,
        )
        return self._telemetry(
            state.run,
            MissionSliceOutcome.YIELDED,
            reason,
            state=state,
            continuation_published=continuation,
            command_hint=command_hint,
        )

    @staticmethod
    def _compile_context_checkpoint(
        run: MissionRunPayload,
        recent_items: list[MissionItemPayload],
        *,
        reason: str,
    ) -> dict[str, Any]:
        stage_acceptance = run.snapshot_json.get("stage_acceptance")
        stage_results: list[dict[str, Any]] = []
        if isinstance(stage_acceptance, dict):
            for stage_id, raw in stage_acceptance.items():
                if not isinstance(raw, dict):
                    continue
                stage_results.append(
                    {
                        "stage_id": str(stage_id),
                        "result": str(raw.get("result") or "unknown"),
                        "missing_criteria": [str(item) for item in raw.get("missing_criteria") or ()][:20],
                        "next_action": raw.get("next_action"),
                    }
                )
        evidence_refs: list[str] = []
        artifact_refs: list[str] = []
        recent_decisions: list[dict[str, Any]] = []
        failure_history: list[dict[str, Any]] = []
        for item in recent_items:
            _collect_ref_values(item.payload_json, "evidence_refs", evidence_refs)
            _collect_ref_values(item.payload_json, "artifact_refs", artifact_refs)
            if item.item_type in {"plan", "quality_check", "pause_request"}:
                recent_decisions.append(
                    {
                        "seq": item.seq,
                        "type": item.item_type,
                        "stage_id": item.stage_id,
                        "summary": (item.summary or "")[:500],
                    }
                )
            if item.phase.value == "failed" or item.item_type == "error":
                failure_history.append(
                    {
                        "seq": item.seq,
                        "operation_id": item.operation_id,
                        "summary": (item.summary or "")[:500],
                    }
                )
        pending_request = run.snapshot_json.get("pending_request")
        return {
            "version": 2,
            "ledger_through_seq": run.last_item_seq,
            "reason": reason,
            "objective": run.objective[:4000],
            "active_stage_id": run.active_stage_id,
            "stage_results": stage_results[-50:],
            "evidence_refs": list(dict.fromkeys(evidence_refs))[-100:],
            "artifact_refs": list(dict.fromkeys(artifact_refs))[-100:],
            "recent_decisions": recent_decisions[-12:],
            "failure_history": failure_history[-12:],
            "pending_request": dict(pending_request) if isinstance(pending_request, dict) else None,
            "next_actions": [str(item) for item in run.snapshot_json.get("next_actions") or ()][:10],
        }

    async def _append(
        self,
        state: _SliceState,
        *,
        items: list[MissionItemDraftPayload],
        snapshot: dict[str, Any] | None = None,
        patch: MissionRunPatchPayload | None = None,
    ) -> None:
        result = await self.store.append_items(
            state.run.mission_id,
            MissionAppendPayload(
                expected_state_version=state.run.state_version,
                lease_owner=state.worker_id,
                lease_epoch=state.run.lease_epoch,
                items=items,
                snapshot_json=validate_mission_snapshot(snapshot) if snapshot is not None else None,
                patch=patch or MissionRunPatchPayload(),
            ),
        )
        state.run = result.mission
        await publish_after_commit(self.events, self.clock, state.run)

    @staticmethod
    def _require_model_usage_receipt(
        receipt: ModelUsageReceipt | None,
        *,
        model_id: str,
    ) -> ModelUsageReceipt:
        if (
            receipt is None
            or receipt.model_id != model_id
            or receipt.usage.total_tokens <= 0
        ):
            raise MissionAgentUsageError(
                "Mission provider response requires a matching non-zero usage receipt"
            )
        return receipt

    @staticmethod
    def _nonreceipt_model_call_outcome(
        exc: BaseException,
    ) -> ModelCallTerminalOutcome:
        if getattr(exc, "usage_not_incurred", False) is not True:
            return ModelCallTerminalOutcome.UNRESOLVED
        raw_outcome = str(
            getattr(exc, "model_call_terminal_outcome", "failed")
        )
        if raw_outcome == ModelCallTerminalOutcome.CANCELLED.value:
            return ModelCallTerminalOutcome.CANCELLED
        return ModelCallTerminalOutcome.FAILED

    @staticmethod
    def _model_ledger_item_matches(
        item: MissionItemPayload,
        draft: MissionItemDraftPayload,
    ) -> bool:
        return (
            item.item_type == draft.item_type
            and item.operation_id == draft.operation_id
            and item.phase == draft.phase
            and item.stage_id == draft.stage_id
            and item.producer == draft.producer
            and item.summary == draft.summary
            and item.risk_level == draft.risk_level
            and item.payload_json == draft.payload_json
            and item.payload_ref == draft.payload_ref
        )

    async def _persist_workspace_model_call_started(
        self,
        state: _SliceState,
        *,
        model_call_id: str,
        model_turn: int,
        model_attempt: int,
    ) -> None:
        await self._persist_model_ledger_item(
            state,
            MissionItemDraftPayload(
                item_type="model_call_started",
                operation_id=model_call_id,
                phase=MissionItemPhase.STARTED,
                stage_id=state.run.active_stage_id,
                producer="workspace_agent",
                summary="Workspace Agent model call started",
                payload_json={
                    "model_call_id": model_call_id,
                    "model_id": state.run.model_id,
                    "turn": model_turn,
                    "attempt": model_attempt,
                },
            ),
        )

    async def _persist_model_ledger_item(
        self,
        state: _SliceState,
        draft: MissionItemDraftPayload,
    ) -> None:
        async def adopt_existing() -> bool:
            existing = await self.store.list_items(
                state.run.mission_id,
                item_type=draft.item_type,
                operation_id=draft.operation_id,
                limit=2,
            )
            if not existing:
                return False
            if len(existing) != 1 or not self._model_ledger_item_matches(
                existing[0],
                draft,
            ):
                raise RuntimeError(
                    "model_call_id has a divergent durable ledger item"
                )
            latest = await self.store.get(state.run.mission_id)
            if latest is not None:
                state.run = latest
            return True

        for _attempt in range(16):
            try:
                await self._append(state, items=[draft])
                return
            except Exception as exc:
                if await adopt_existing():
                    return
                if not _is_conflict(exc):
                    raise
                latest = await self.store.get(state.run.mission_id)
                if (
                    latest is None
                    or latest.lease_owner != state.worker_id
                    or latest.lease_epoch != state.run.lease_epoch
                    or latest.lease_expires_at is None
                    or not _expires_after(latest.lease_expires_at, self.clock.now())
                ):
                    raise
                state.run = latest
                await asyncio.sleep(0)
        raise RuntimeError(
            "Mission state changed repeatedly while recording model ledger item"
        )

    async def _persist_workspace_model_usage(
        self,
        state: _SliceState,
        *,
        model_call_id: str,
        model_turn: int,
        model_attempt: int,
        usage_receipt: ModelUsageReceipt,
    ) -> None:
        usage_receipt = self._require_model_usage_receipt(
            usage_receipt,
            model_id=state.run.model_id,
        )
        draft = MissionItemDraftPayload(
            item_type="usage_receipt",
            operation_id=model_call_id,
            phase=MissionItemPhase.COMPLETED,
            stage_id=state.run.active_stage_id,
            producer="workspace_agent",
            summary="Workspace Agent model usage recorded",
            payload_json={
                **usage_receipt.model_dump(mode="json"),
                "model_call_id": model_call_id,
                "turn": model_turn,
                "attempt": model_attempt,
            },
        )
        await self._persist_model_ledger_item(state, draft)

    async def _persist_workspace_model_terminal(
        self,
        state: _SliceState,
        *,
        model_call_id: str,
        model_turn: int,
        model_attempt: int,
        outcome: ModelCallTerminalOutcome,
        error_type: str | None,
        detail: str,
    ) -> None:
        payload = ModelCallTerminalPayload(
            model_call_id=model_call_id,
            model_id=state.run.model_id,
            turn=model_turn,
            attempt=model_attempt,
            outcome=outcome,
            error_type=error_type,
            detail=detail,
        )
        await self._persist_model_ledger_item(
            state,
            MissionItemDraftPayload(
                item_type="model_call_terminal",
                operation_id=model_call_id,
                phase=(
                    MissionItemPhase.CANCELLED
                    if outcome is ModelCallTerminalOutcome.CANCELLED
                    else MissionItemPhase.FAILED
                ),
                stage_id=state.run.active_stage_id,
                producer="workspace_agent",
                summary=f"Workspace Agent model call {outcome.value}",
                payload_json=payload.model_dump(mode="json"),
            ),
        )

    @staticmethod
    def _recovered_model_call_terminal(
        model_call: MissionModelCallStatePayload,
    ) -> MissionItemDraftPayload:
        started = model_call.started
        payload = ModelCallStartedPayload.model_validate(started.payload_json)
        terminal = ModelCallTerminalPayload(
            **payload.model_dump(mode="python"),
            outcome=ModelCallTerminalOutcome.UNRESOLVED,
            error_type="ModelCallRecoveryUnresolved",
            detail=(
                "Mission recovery found a started provider call without a durable "
                "terminal outcome; usage could not be confirmed"
            ),
        )
        return MissionItemDraftPayload(
            item_type="model_call_terminal",
            operation_id=started.operation_id,
            phase=MissionItemPhase.FAILED,
            stage_id=started.stage_id,
            producer=started.producer,
            summary="Recovered model call requires usage reconciliation",
            payload_json=terminal.model_dump(mode="json"),
        )

    async def _reconcile_model_call_ledger(
        self,
        state: _SliceState,
    ) -> bool:
        model_calls = await self.store.list_model_call_states(
            state.run.mission_id
        )
        open_calls = [
            model_call
            for model_call in model_calls
            if model_call.state is ModelCallState.OPEN
        ]
        for model_call in open_calls:
            await self._persist_model_ledger_item(
                state,
                self._recovered_model_call_terminal(model_call),
            )
        if open_calls:
            model_calls = await self.store.list_model_call_states(
                state.run.mission_id
            )
        if not any(
            model_call.state is ModelCallState.UNRESOLVED
            for model_call in model_calls
        ):
            return False
        await self._fail_model_call_reconciliation(state)
        return True

    async def _heartbeat_if_due(self, state: _SliceState) -> None:
        now = self.clock.monotonic()
        if now - state.last_heartbeat_monotonic < self.limits.heartbeat_interval_seconds:
            return
        await self._heartbeat_current_lease(state, now_monotonic=now)

    async def _heartbeat_current_lease(
        self,
        state: _SliceState,
        *,
        now_monotonic: float | None = None,
    ) -> None:
        latest = await self.store.get(state.run.mission_id)
        if (
            latest is None
            or latest.lease_owner != state.worker_id
            or latest.lease_epoch != state.run.lease_epoch
            or latest.lease_expires_at is None
            or not _expires_after(latest.lease_expires_at, self.clock.now())
        ):
            raise MissionLeaseLostError(
                "Mission lease changed while an operation was running"
            )
        try:
            heartbeat = await self.store.heartbeat_lease(
                latest.mission_id,
                MissionLeaseHeartbeatPayload(
                    worker_id=state.worker_id,
                    lease_epoch=latest.lease_epoch,
                    expected_state_version=latest.state_version,
                    ttl_seconds=self.limits.lease_ttl_seconds,
                ),
            )
        except Exception as exc:
            if _is_conflict(exc):
                current = await self.store.get(state.run.mission_id)
                if (
                    current is None
                    or current.lease_owner != state.worker_id
                    or current.lease_epoch != state.run.lease_epoch
                    or current.lease_expires_at is None
                    or not _expires_after(current.lease_expires_at, self.clock.now())
                ):
                    raise MissionLeaseLostError(
                        "Mission lease changed while its heartbeat was being committed"
                    ) from exc
            raise
        if (
            heartbeat.lease_owner != state.worker_id
            or heartbeat.lease_epoch != latest.lease_epoch
        ):
            raise MissionLeaseLostError(
                "Mission heartbeat returned a different lease fence"
            )
        state.run = heartbeat
        state.last_heartbeat_monotonic = (
            now_monotonic
            if now_monotonic is not None
            else self.clock.monotonic()
        )
        # Long operations persist semantic progress outside this driver. A
        # heartbeat is the bounded invalidation cadence that makes those facts
        # visible without coupling their transaction to transient SSE delivery.
        await publish_after_commit(self.events, self.clock, state.run)

    async def _build_loop_context(
        self,
        state: _SliceState,
        *,
        protocol_feedback: str | None = None,
    ) -> MissionLoopContext:
        recent = await self._recent_items(state.run)
        references = await self._reference_items(
            state.run.mission_id,
            maximum=_AGENT_REFERENCE_ITEM_LIMIT,
        )
        pending_refs = state.run.snapshot_json.get("pending_command_refs")
        pending_seqs = {int(item.get("seq") or 0) for item in pending_refs if isinstance(item, dict)} if isinstance(pending_refs, list) else set()
        pending = [item for item in recent if item.seq in pending_seqs]
        return MissionLoopContext(
            mission=state.run,
            pending_commands=pending,
            recent_items=recent,
            reference_items=references,
            model_turns_used=state.model_turns,
            tool_steps_used=state.tool_steps,
            deadline_monotonic=state.deadline_monotonic,
            protocol_feedback=protocol_feedback,
        )

    async def _recent_items(
        self,
        run: MissionRunPayload,
        *,
        limit: int = _RECENT_ITEM_LIMIT,
    ) -> list[MissionItemPayload]:
        bounded_limit = min(max(limit, 1), 100)
        after_seq = max(0, run.last_item_seq - bounded_limit)
        return await self.store.list_items(
            run.mission_id,
            after_seq=after_seq,
            limit=bounded_limit,
        )

    async def _reference_items(
        self,
        mission_id: str,
        *,
        maximum: int = 1000,
    ) -> list[MissionItemPayload]:
        lineage_ids: list[str] = []
        visited: set[str] = set()
        current = await self.store.get(mission_id)
        workspace_id = current.workspace_id if current is not None else None
        while current is not None and len(lineage_ids) < 32:
            current_id = current.mission_id
            if current_id in visited or current.workspace_id != workspace_id:
                break
            visited.add(current_id)
            lineage_ids.append(current_id)
            parent_id = current.parent_mission_id
            current = await self.store.get(parent_id) if parent_id else None

        references: list[MissionItemPayload] = []
        for lineage_mission_id in lineage_ids:
            for item_type in ("evidence", "artifact", "output"):
                after_seq = 0
                while True:
                    page = await self.store.list_items(
                        lineage_mission_id,
                        after_seq=after_seq,
                        limit=100,
                        item_type=item_type,
                    )
                    references.extend(page)
                    if len(page) < 100:
                        break
                    after_seq = page[-1].seq
        references.sort(key=lambda item: (item.created_at, item.mission_id, item.seq))
        return references[-maximum:]

    async def _load_item(self, mission_id: str, seq: int) -> MissionItemPayload | None:
        if seq <= 0:
            return None
        items = await self.store.list_items(mission_id, after_seq=seq - 1, limit=1)
        if not items or items[0].seq != seq:
            return None
        return items[0]

    async def _clear_invalid_inflight(
        self,
        state: _SliceState,
        operation_id: str,
    ) -> None:
        snapshot = dict(state.run.snapshot_json)
        snapshot.pop("inflight_operation", None)
        snapshot = self._merge_snapshot(
            snapshot,
            {
                "last_error": {
                    "kind": "invalid_inflight_reference",
                    "operation_id": operation_id,
                },
                "next_actions": ["replan_after_invalid_receipt"],
            },
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="error",
                    operation_id=operation_id or None,
                    phase=MissionItemPhase.FAILED,
                    producer="mission_runtime",
                    summary="In-flight operation reference could not be restored",
                    payload_json={},
                )
            ],
            snapshot=snapshot,
        )

    async def _invoke_with_deadline(
        self,
        awaitable: Awaitable[ResultT],
        state: _SliceState,
    ) -> ResultT:
        remaining = state.deadline_monotonic - self.clock.monotonic()
        if remaining <= 0:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise TimeoutError("MissionDriveSlice deadline reached")
        task = asyncio.ensure_future(awaitable)
        try:
            while True:
                remaining = state.deadline_monotonic - self.clock.monotonic()
                if remaining <= 0:
                    raise TimeoutError("MissionDriveSlice deadline reached")
                wait_seconds = min(
                    remaining,
                    self.limits.heartbeat_interval_seconds,
                )
                done, _pending = await asyncio.wait(
                    {task},
                    timeout=wait_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if task in done:
                    return task.result()
                try:
                    await self._heartbeat_current_lease(state)
                except MissionLeaseLostError:
                    raise
                except Exception:
                    logger.warning(
                        "Mission heartbeat failed during operation mission=%s",
                        state.run.mission_id,
                        exc_info=True,
                    )
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                try:
                    latest = await self.store.get(state.run.mission_id)
                    if (
                        latest is not None
                        and latest.lease_owner == state.worker_id
                        and latest.lease_epoch == state.run.lease_epoch
                    ):
                        state.run = latest
                except Exception:
                    logger.warning(
                        "Mission state refresh failed after operation mission=%s",
                        state.run.mission_id,
                        exc_info=True,
                    )

    async def _publish_wakeup(
        self,
        mission_id: str,
        *,
        command_hint: str | None = None,
        delay_seconds: int = 0,
    ) -> bool:
        current = await self.store.get(mission_id)
        if current is None or _status_value(current) in _TERMINAL_STATUSES:
            track_mission_dispatch("not_runnable")
            return False
        dispatch_owner = f"mission-dispatch:{uuid.uuid4().hex}"
        try:
            claimed = await self.store.claim_dispatch(
                mission_id,
                MissionDispatchClaimPayload(
                    worker_id=dispatch_owner,
                    expected_state_version=current.state_version,
                    ttl_seconds=MISSION_DISPATCH_TTL_SECONDS + delay_seconds,
                    not_before_at=(
                        self.clock.now() + timedelta(seconds=delay_seconds)
                        if delay_seconds > 0
                        else None
                    ),
                ),
            )
        except Exception as exc:
            if _is_conflict(exc):
                track_mission_dispatch("already_scheduled")
                return False
            track_mission_dispatch("claim_failed")
            logger.warning(
                "Mission dispatch claim failed for %s; reconciler will recover it",
                mission_id,
                exc_info=True,
            )
            return False
        track_mission_dispatch("claimed")
        enqueued_at = self.clock.now()
        try:
            await self.wakeups.publish(
                mission_id,
                dispatch_owner=dispatch_owner,
                dispatch_epoch=claimed.dispatch_epoch,
                enqueued_at=enqueued_at,
                command_hint=command_hint,
                delay_seconds=delay_seconds,
            )
        except Exception:
            track_mission_dispatch("publish_failed")
            logger.warning(
                "Mission wakeup publish failed for %s; reconciler will recover it",
                mission_id,
                exc_info=True,
            )
            try:
                await self.store.release_dispatch(
                    mission_id,
                    MissionDispatchReleasePayload(
                        worker_id=dispatch_owner,
                        dispatch_epoch=claimed.dispatch_epoch,
                    ),
                )
            except Exception as release_exc:
                if not _is_conflict(release_exc):
                    logger.warning(
                        "Mission dispatch release failed for %s",
                        mission_id,
                        exc_info=True,
                    )
            return False
        track_mission_dispatch("published")
        return True

    async def notify_runnable(
        self,
        mission_id: str,
        *,
        command_hint: str | None = None,
    ) -> bool:
        """Publish a best-effort delivery hint for durable runnable Mission state."""
        return await self._publish_wakeup(mission_id, command_hint=command_hint)

    def _slice_budget_exhausted(self, state: _SliceState) -> bool:
        remaining = state.deadline_monotonic - self.clock.monotonic()
        next_step_reserve = min(
            self.limits.next_step_reserve_seconds,
            self.limits.wall_time_seconds - self.limits.shutdown_margin_seconds,
        )
        return remaining <= next_step_reserve or state.model_turns >= self.limits.max_model_turns or state.tool_steps >= self.limits.max_tool_steps

    def _slice_time_below_operation_reserve(
        self,
        state: _SliceState,
        *,
        kind: str,
        required_budget_seconds: float = 0.0,
    ) -> bool:
        remaining = state.deadline_monotonic - self.clock.monotonic()
        if kind == "subagent":
            reserve = min(
                self.limits.next_step_reserve_seconds,
                self.limits.wall_time_seconds - self.limits.shutdown_margin_seconds,
            )
        else:
            reserve = min(
                max(
                    self.limits.tool_start_reserve_seconds,
                    required_budget_seconds,
                ),
                self.limits.wall_time_seconds
                - self.limits.shutdown_margin_seconds,
            )
        return remaining <= reserve

    def _inflight_operation_lacks_time(self, state: _SliceState) -> bool:
        inflight = state.run.snapshot_json.get("inflight_operation")
        if not isinstance(inflight, dict) or inflight.get("kind") != "tool":
            return False
        raw_required = inflight.get("required_budget_seconds")
        try:
            required = (
                float(raw_required)
                if isinstance(raw_required, (int, float))
                and not isinstance(raw_required, bool)
                else self.limits.wall_time_seconds
            )
        except (OverflowError, TypeError, ValueError):
            required = self.limits.wall_time_seconds
        if not isfinite(required) or required < 0:
            required = self.limits.wall_time_seconds
        return self._slice_time_below_operation_reserve(
            state,
            kind="tool",
            required_budget_seconds=required,
        )

    @staticmethod
    def _unavailable_resource_dimensions(
        run: MissionRunPayload,
        *,
        model_calls: int = 0,
        tool_operations: int = 0,
        subagent_jobs: int = 0,
    ) -> tuple[str, ...]:
        budget = execution_budget_from_runtime_context(run.runtime_context_json)
        usage = resource_usage_from_snapshot(run.snapshot_json)
        return unavailable_budget_dimensions(
            usage,
            budget,
            model_calls=model_calls,
            tool_operations=tool_operations,
            subagent_jobs=subagent_jobs,
        )

    async def _fail_resource_budget(
        self,
        state: _SliceState,
        dimensions: tuple[str, ...],
    ) -> MissionSliceOutcome:
        budget = execution_budget_from_runtime_context(
            state.run.runtime_context_json
        )
        usage = resource_usage_from_snapshot(state.run.snapshot_json)
        snapshot = self._merge_snapshot(
            state.run.snapshot_json,
            {
                "failure_reason": "resource_budget_exhausted",
                "resource_budget_stop": {
                    "dimensions": list(dimensions),
                    "usage": usage.model_dump(mode="json"),
                    "budget": budget.model_dump(mode="json"),
                },
            },
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="error",
                    phase=MissionItemPhase.FAILED,
                    stage_id=state.run.active_stage_id,
                    producer="mission_runtime",
                    summary=(
                        "Mission reached its cumulative execution limit; "
                        "partial work was preserved"
                    ),
                    payload_json={
                        "error_code": "resource_budget_exhausted",
                        "dimensions": list(dimensions),
                    },
                )
            ],
            snapshot=snapshot,
            patch=MissionRunPatchPayload(status=MissionStatus.FAILED),
        )
        return MissionSliceOutcome.TERMINAL

    async def _fail_model_call_reconciliation(
        self,
        state: _SliceState,
    ) -> None:
        for _attempt in range(16):
            model_calls = await self.store.list_model_call_states(
                state.run.mission_id
            )
            unresolved_ids = [
                str(model_call.started.operation_id)
                for model_call in model_calls
                if model_call.state is ModelCallState.UNRESOLVED
            ]
            if not unresolved_ids:
                return
            inflight = state.run.snapshot_json.get("inflight_operation")
            inflight_kind = (
                str(inflight.get("kind") or "")
                if isinstance(inflight, dict)
                else ""
            )
            snapshot = self._merge_snapshot(
                state.run.snapshot_json,
                {
                    "failure_reason": "model_usage_reconciliation_required",
                    "last_error": {
                        "kind": "model_usage_reconciliation_required",
                        "model_call_ids": unresolved_ids,
                    },
                    "inflight_operation": None,
                    "next_actions": None,
                },
            )
            try:
                await self._append(
                    state,
                    items=[
                        MissionItemDraftPayload(
                            item_type="error",
                            operation_id=unresolved_ids[0],
                            phase=MissionItemPhase.FAILED,
                            stage_id=state.run.active_stage_id,
                            producer="mission_runtime",
                            summary=(
                                "Mission stopped because model usage could not be "
                                "verified"
                            ),
                            payload_json={
                                "error_code": (
                                    "model_usage_reconciliation_required"
                                ),
                                "model_call_ids": unresolved_ids,
                            },
                        )
                    ],
                    snapshot=snapshot,
                    patch=MissionRunPatchPayload(
                        status=MissionStatus.FAILED,
                        active_subagent_count_delta=(
                            -1
                            if inflight_kind == "subagent"
                            and state.run.active_subagent_count > 0
                            else 0
                        ),
                    ),
                )
                return
            except Exception as append_exc:
                latest = await self.store.get(state.run.mission_id)
                if (
                    latest is not None
                    and latest.status is MissionStatus.FAILED
                    and latest.snapshot_json.get("failure_reason")
                    == "model_usage_reconciliation_required"
                ):
                    state.run = latest
                    return
                if (
                    not _is_conflict(append_exc)
                    or latest is None
                    or latest.lease_owner != state.worker_id
                    or latest.lease_epoch != state.run.lease_epoch
                ):
                    raise
                state.run = latest
                await asyncio.sleep(0)
        raise RuntimeError(
            "Mission state changed repeatedly while recording usage reconciliation"
        )

    @staticmethod
    def _merge_snapshot(
        current: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(current)
        for key, value in patch.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        return validate_mission_snapshot(merged)

    def _decision_snapshot(
        self,
        current: dict[str, Any],
        decision: MissionAgentDecision,
        *,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        patch = dict(decision.snapshot_patch)
        patch["pending_command_refs"] = None
        patch["last_error"] = None
        patch["degraded_reason"] = None
        patch["next_actions"] = None
        patch["loop_guard"] = {"consecutive_failures": 0, "transient_failures": 0}
        patch["last_agent_decision"] = {
            "decision_id": decision.decision_id,
            "kind": decision.kind.value,
            "summary": decision.summary[:500],
        }
        if extra:
            patch.update(extra)
        return self._merge_snapshot(current, patch)

    @staticmethod
    def _stage_patch(
        stage_id: str | None,
        **fields: Any,
    ) -> MissionRunPatchPayload:
        if stage_id:
            fields["active_stage_id"] = stage_id
        return MissionRunPatchPayload(**fields)

    @staticmethod
    def _pause_item(request: MissionPauseRequest) -> MissionItemDraftPayload:
        return MissionItemDraftPayload(
            item_type="pause_request",
            operation_id=request.request_id,
            phase=MissionItemPhase.COMPLETED,
            producer="mission_runtime",
            summary=request.summary,
            payload_json={
                "reason": request.reason,
                "pending_request": request.pending_request,
            },
        )

    @staticmethod
    def _scoped_pause_request(
        run: MissionRunPayload,
        request: MissionPauseRequest,
    ) -> MissionPauseRequest:
        if request.reason == "permission":
            return request
        digest = hashlib.sha256(f"{run.mission_id}:{run.state_version}:{run.last_item_seq}:{request.request_id}".encode()).hexdigest()[:24]
        semantic_id = request.request_id
        return request.model_copy(
            update={
                "request_id": f"pause:{semantic_id[:100]}:{digest}",
                "pending_request": {
                    **request.pending_request,
                    "semantic_request_id": semantic_id,
                },
            }
        )

    def _pause_snapshot(
        self,
        current: dict[str, Any],
        request: MissionPauseRequest,
    ) -> dict[str, Any]:
        return self._merge_snapshot(
            current,
            {
                "waiting_reason": request.reason,
                "pending_request": {
                    "request_id": request.request_id,
                    "summary": request.summary,
                    **request.pending_request,
                },
                "next_actions": ["wait_for_user_input"],
            },
        )

    async def _operation_has_terminal(
        self,
        mission_id: str,
        operation_id: str,
        *,
        item_types: tuple[str, ...],
    ) -> bool:
        after_seq = 0
        while True:
            items = await self.store.list_items(
                mission_id,
                after_seq=after_seq,
                limit=100,
                operation_id=operation_id,
            )
            if any(
                item.item_type in item_types
                and item.phase
                in {
                    MissionItemPhase.COMPLETED,
                    MissionItemPhase.FAILED,
                    MissionItemPhase.CANCELLED,
                }
                for item in items
            ):
                return True
            if len(items) < 100:
                return False
            after_seq = items[-1].seq

    @staticmethod
    def _decision_terminal_item_types(
        kind: MissionDecisionKind,
    ) -> tuple[str, ...]:
        return {
            MissionDecisionKind.TOOL: ("tool_result",),
            MissionDecisionKind.SUBAGENT: ("subagent_completed",),
            MissionDecisionKind.QUALITY: ("quality_check",),
            MissionDecisionKind.REVIEW: ("status_update", "error"),
        }[kind]

    @staticmethod
    def _cancelled_inflight_item(
        run: MissionRunPayload,
    ) -> MissionItemDraftPayload | None:
        inflight = run.snapshot_json.get("inflight_operation")
        if not isinstance(inflight, dict):
            return None
        operation_id = str(inflight.get("operation_id") or "").strip()
        kind = str(inflight.get("kind") or "").strip()
        item_type = {
            "tool": "tool_result",
            "subagent": "subagent_completed",
        }.get(kind)
        if not operation_id or item_type is None:
            return None
        return MissionItemDraftPayload(
            item_type=item_type,
            operation_id=operation_id,
            phase=MissionItemPhase.CANCELLED,
            stage_id=run.active_stage_id,
            producer="mission_runtime",
            summary="任务已按你的要求停止；该执行步骤没有继续运行。",
            payload_json={
                "status": "cancelled",
                "error_code": "cancelled_by_user",
                "recoverable": True,
            },
        )

    @staticmethod
    def _failed_port_outcome(summary: str, exc: BaseException) -> MissionPortOutcome:
        return MissionPortOutcome(
            status=MissionPortOutcomeStatus.FAILED,
            summary=summary,
            payload_json={
                "error_type": type(exc).__name__,
                "detail": str(exc)[:500],
            },
        )

    def _telemetry(
        self,
        run: MissionRunPayload,
        outcome: MissionSliceOutcome,
        reason: str,
        *,
        state: _SliceState | None = None,
        continuation_published: bool = False,
        command_hint: str | None = None,
    ) -> MissionSliceTelemetry:
        return MissionSliceTelemetry(
            mission_id=run.mission_id,
            outcome=outcome,
            status=run.status.value,
            reason=reason,
            state_version=run.state_version,
            last_item_seq=run.last_item_seq,
            lease_epoch=run.lease_epoch,
            model_turns=state.model_turns if state else 0,
            tool_steps=state.tool_steps if state else 0,
            continuation_published=continuation_published,
            command_hint=command_hint,
        )

    @staticmethod
    def _telemetry_missing(
        mission_id: str,
        *,
        command_hint: str | None,
    ) -> MissionSliceTelemetry:
        return MissionSliceTelemetry(
            mission_id=mission_id,
            outcome=MissionSliceOutcome.TERMINAL,
            status="not_found",
            reason="mission_not_found",
            state_version=0,
            last_item_seq=0,
            lease_epoch=0,
            model_turns=0,
            tool_steps=0,
            command_hint=command_hint,
        )


def _collect_ref_values(value: Any, key: str, target: list[str]) -> None:
    if isinstance(value, dict):
        for candidate_key, candidate_value in value.items():
            if candidate_key == key and isinstance(candidate_value, list):
                for item in candidate_value:
                    ref_id = _reference_id(item)
                    if ref_id is not None:
                        target.append(ref_id)
            else:
                _collect_ref_values(candidate_value, key, target)
    elif isinstance(value, list):
        for item in value:
            _collect_ref_values(item, key, target)


def _reference_id(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
    elif isinstance(value, dict):
        raw_ref_id = value.get("ref_id")
        candidate = raw_ref_id.strip() if isinstance(raw_ref_id, str) else ""
    else:
        candidate = ""
    return candidate[:300] if candidate else None


def _transient_retry_delay_seconds(run: MissionRunPayload) -> int:
    guard = run.snapshot_json.get("loop_guard")
    raw_attempt = guard.get("transient_failures") if isinstance(guard, dict) else 1
    attempt: int
    try:
        attempt = int(raw_attempt or 1)
    except (TypeError, ValueError):
        attempt = 1
    exponent = min(max(attempt - 1, 0), 4)
    return min(5 * (1 << exponent), 60)


def _expires_after(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    normalized_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    normalized_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return normalized_value > normalized_now


__all__ = [
    "MissionResumeRequestMismatchError",
    "MissionRuntime",
    "MissionStartRejectionCode",
    "MissionStartRejectedError",
]

"""Lease-fenced, bounded driver for one durable MissionRun."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, TypeVar

from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionApplyCommandsPayload,
    MissionCancelPayload,
    MissionCreatePayload,
    MissionItemDraftPayload,
    MissionItemPayload,
    MissionItemPhase,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionReasoningEffort,
    MissionResumePayload,
    MissionReviewItemsCreatePayload,
    MissionRiskLevel,
    MissionRunPatchPayload,
    MissionRunPayload,
    MissionStatus,
    validate_mission_snapshot,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    BillingOutcome,
    MissionAgentDecision,
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
    BillingPort,
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

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_PENDING_COMMAND_REF_LIMIT = 20
_RECENT_ITEM_LIMIT = 24

ResultT = TypeVar("ResultT")


class MissionStartRejectedError(RuntimeError):
    """Raised when budget/policy preflight rejects mission creation."""


class MissionResumeRequestMismatchError(RuntimeError):
    """Raised when input answers a different durable pause request."""


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
        billing: BillingPort,
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
        self.billing = billing
        self.events = events
        self.wakeups = wakeups
        self.limits = limits or MissionSliceLimits()
        self.clock = clock or SystemMissionClock()

    async def start(self, request: MissionStartRequest) -> MissionStartReceipt:
        request = await self.start_context.pin(request)
        preflight = await self.billing.preflight(request)
        if not preflight.allowed:
            raise MissionStartRejectedError(preflight.summary or "Mission budget preflight was not approved")

        snapshot = dict(request.snapshot_json)
        snapshot["billing"] = self._billing_snapshot(preflight, state="preflight")
        created = await self.store.create(
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
                reasoning_effort=MissionReasoningEffort(request.reasoning_effort),
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
        if created.created:
            wakeup_published = await self._publish_wakeup(created.mission.mission_id)
        return MissionStartReceipt(
            mission_id=created.mission.mission_id,
            status=created.mission.status.value,
            title=created.mission.title,
            created=created.created,
            wakeup_published=wakeup_published,
        )

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
        return result.mission

    async def cancel(
        self,
        mission_id: str,
        *,
        request_id: str,
        reason: str | None = None,
        producer: str = "workspace_agent",
    ) -> MissionRunPayload:
        result = await self.store.cancel(
            mission_id,
            MissionCancelPayload(
                request_id=request_id,
                reason=reason,
                producer=producer,
            ),
        )
        await publish_after_commit(self.events, self.clock, result.mission)
        await self._settle_best_effort(result.mission)
        return result.mission

    async def run_slice(
        self,
        mission_id: str,
        *,
        worker_id: str,
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
        if _status_value(initial) == "waiting" and initial.last_command_seq <= initial.last_applied_command_seq:
            return self._telemetry(
                initial,
                MissionSliceOutcome.WAITING,
                "mission_waiting_for_input",
                command_hint=command_hint,
            )

        try:
            claimed = await self.store.claim_lease(
                mission_id,
                MissionLeaseClaimPayload(
                    worker_id=worker_id,
                    expected_state_version=initial.state_version,
                    ttl_seconds=self.limits.lease_ttl_seconds,
                ),
            )
        except Exception as exc:
            if not _is_conflict(exc):
                raise
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
                if not _is_conflict(exc):
                    raise
                latest = await self.store.get(mission_id) or state.run
                if _status_value(latest) not in _TERMINAL_STATUSES and latest.lease_owner == state.worker_id and latest.lease_epoch == state.run.lease_epoch:
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
        billing_outcome = await self._ensure_billing(state)
        if billing_outcome is not None:
            return self._telemetry(
                state.run,
                MissionSliceOutcome.WAITING,
                "budget_confirmation_required",
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

        while True:
            command_result = await self._apply_commands_at_boundary(state)
            if command_result is not None:
                return self._telemetry(
                    state.run,
                    command_result,
                    "durable_command_applied",
                    state=state,
                    command_hint=command_hint,
                )

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

            if self._slice_budget_exhausted(state):
                return await self._checkpoint_and_yield(
                    state,
                    reason="slice_budget_exhausted",
                    command_hint=command_hint,
                )

            recovered = await self._recover_inflight_operation(state)
            if recovered:
                continue

            context = await self._build_loop_context(state)
            state.model_turns += 1
            try:
                decision = await self._invoke_with_deadline(
                    self.agent.decide(context),
                    state,
                )
            except Exception as exc:
                transient_failure = _is_transient_agent_failure(exc)
                terminal = await self._record_loop_failure(state, exc)
                if terminal:
                    await self._settle_best_effort(state.run)
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
                    retry_delay_seconds=(
                        _transient_retry_delay_seconds(state.run) if transient_failure else 0
                    ),
                )

            outcome = await self._handle_decision(state, decision)
            if outcome is not None:
                if outcome in {MissionSliceOutcome.COMPLETED, MissionSliceOutcome.TERMINAL}:
                    await self._settle_best_effort(state.run)
                return self._telemetry(
                    state.run,
                    outcome,
                    f"decision_{decision.kind.value}",
                    state=state,
                    command_hint=command_hint,
                )

    async def _ensure_billing(self, state: _SliceState) -> BillingOutcome | None:
        billing = state.run.snapshot_json.get("billing")
        if isinstance(billing, dict) and billing.get("state") == "ready":
            return None
        outcome = await self._invoke_with_deadline(
            self.billing.ensure_reservation(state.run),
            state,
        )
        if not outcome.allowed:
            assert outcome.pause_request is not None
            await self._pause_under_fence(state, outcome.pause_request)
            return outcome
        snapshot = self._merge_snapshot(
            state.run.snapshot_json,
            {"billing": self._billing_snapshot(outcome, state="ready")},
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="status_update",
                    phase=MissionItemPhase.COMPLETED,
                    producer="billing",
                    summary=outcome.summary or "Mission budget reserved",
                    payload_json={"free_policy": outcome.free_policy},
                )
            ],
            snapshot=snapshot,
        )
        return None

    async def _apply_commands_at_boundary(
        self,
        state: _SliceState,
    ) -> MissionSliceOutcome | None:
        commands = await self.store.list_unapplied_commands(
            state.run.mission_id,
            limit=100,
        )
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
        items = [
            MissionItemDraftPayload(
                item_type="status_update",
                operation_id=command.operation_id,
                phase=MissionItemPhase.COMPLETED,
                producer="mission_runtime",
                summary=command.summary or "Durable mission input applied",
                payload_json={
                    "command_seq": command.seq,
                    "command_type": str(command.payload_json.get("command_type") or "steer"),
                },
            )
            for command in commands
        ]

        command_types = {str(command.payload_json.get("command_type") or "steer") for command in commands}
        target_status: MissionStatus | None = None
        result: MissionSliceOutcome | None = None
        if "cancel" in command_types:
            target_status = MissionStatus.CANCELLED
            result = MissionSliceOutcome.TERMINAL
            snapshot_patch["failure_reason"] = "cancelled_by_user"
            items.append(
                MissionItemDraftPayload(
                    item_type="status_update",
                    phase=MissionItemPhase.CANCELLED,
                    producer="mission_runtime",
                    summary="Mission cancelled by durable command",
                    payload_json={},
                )
            )
        elif "pause" in command_types:
            target_status = MissionStatus.WAITING
            result = MissionSliceOutcome.WAITING
            snapshot_patch["waiting_reason"] = "user_input"
            snapshot_patch["pending_request"] = {
                "request_id": commands[-1].operation_id,
                "type": "user_pause",
            }
            items.append(
                MissionItemDraftPayload(
                    item_type="pause_request",
                    operation_id=commands[-1].operation_id,
                    phase=MissionItemPhase.COMPLETED,
                    producer="mission_runtime",
                    summary="Mission paused by user",
                    payload_json={"reason": "user_input"},
                )
            )
        elif _status_value(state.run) in {"running", "waiting"}:
            target_status = MissionStatus.PLANNING

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
                patch=MissionRunPatchPayload(status=target_status),
            ),
        )
        state.run = result_payload.mission
        await publish_after_commit(self.events, self.clock, state.run)
        if result == MissionSliceOutcome.TERMINAL:
            await self._settle_best_effort(state.run)
        return result

    async def _handle_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        if decision.kind == MissionDecisionKind.CONTINUE:
            if not await self._ensure_stage_start_allowed(state, decision):
                return None
            snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
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
            await self._pause_under_fence(state, decision.pause_request)
            return MissionSliceOutcome.WAITING

        if decision.kind == MissionDecisionKind.COMPLETE:
            missing_stages = self._missing_required_stage_acceptance(state.run)
            if missing_stages:
                await self._record_invalid_decision(
                    state,
                    decision,
                    "completion requires passed StageAcceptance results: " + ", ".join(missing_stages),
                )
                return None
            snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
            await self._append(
                state,
                items=[
                    MissionItemDraftPayload(
                        item_type="status_update",
                        operation_id=decision.decision_id,
                        phase=MissionItemPhase.COMPLETED,
                        producer="workspace_agent",
                        summary=decision.summary,
                        payload_json=decision.payload_json,
                    )
                ],
                snapshot=snapshot,
                patch=MissionRunPatchPayload(status=MissionStatus.COMPLETED),
            )
            return MissionSliceOutcome.COMPLETED

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
            )
            return None

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
        await self._begin_operation(
            state,
            decision,
            kind="tool",
            item_type="tool_call",
            payload_json={"tool_name": tool_name, "arguments": arguments},
        )
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
            context_checkpoint=dict(
                state.run.snapshot_json.get("context_checkpoint_summary") or {}
            ),
            prior_output_briefs=tuple(
                str(item.summary)[:1000]
                for item in recent_items[-8:]
                if item.summary
            ),
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
                        deadline_monotonic=state.deadline_monotonic,
                    )
                ),
                state,
            )
        except Exception as exc:
            await self._record_operation_failure(
                state,
                decision=decision,
                kind="quality",
                item_type="quality_check",
                producer="stage_quality",
                summary="Stage quality evaluation did not complete",
                exc=exc,
            )
            return None
        snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
        stage_acceptance = dict(snapshot.get("stage_acceptance") or {})
        stage_acceptance[stage_id] = dict(outcome.payload_json)
        snapshot = self._merge_snapshot(
            snapshot,
            {"stage_acceptance": stage_acceptance},
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
        patch = MissionRunPatchPayload()
        result: MissionSliceOutcome | None = None
        if outcome.verdict == StageQualityVerdict.ASK_USER:
            assert outcome.pause_request is not None
            snapshot = self._pause_snapshot(snapshot, outcome.pause_request)
            items.append(self._pause_item(outcome.pause_request))
            patch = MissionRunPatchPayload(status=MissionStatus.WAITING)
            result = MissionSliceOutcome.WAITING
        elif outcome.verdict == StageQualityVerdict.STOP:
            snapshot = self._merge_snapshot(snapshot, {"failure_reason": "repeated_failure"})
            patch = MissionRunPatchPayload(status=MissionStatus.FAILED)
            result = MissionSliceOutcome.TERMINAL
        elif outcome.verdict == StageQualityVerdict.REVISE:
            snapshot = self._merge_snapshot(snapshot, {"next_actions": ["revise_current_stage"]})
        else:
            snapshot = self._merge_snapshot(snapshot, {"next_actions": ["advance_stage"]})
        await self._append(state, items=items, snapshot=snapshot, patch=patch)
        return result

    async def _run_review_decision(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> MissionSliceOutcome | None:
        try:
            batch = await self._invoke_with_deadline(
                self.review_candidates.build_candidates(
                    ReviewCandidateRequest(
                        mission=state.run,
                        operation_id=decision.operation_id or "",
                        stage_id=decision.stage_id,
                        candidate_json=decision.payload_json,
                        deadline_monotonic=state.deadline_monotonic,
                    )
                ),
                state,
            )
        except Exception as exc:
            await self._record_operation_failure(
                state,
                decision=decision,
                kind="review",
                item_type="error",
                producer="review_candidate",
                summary="Review candidate generation did not complete",
                exc=exc,
            )
            return None
        result = await self.store.create_review_items(
            state.run.mission_id,
            MissionReviewItemsCreatePayload(
                expected_state_version=state.run.state_version,
                lease_owner=state.worker_id,
                lease_epoch=state.run.lease_epoch,
                items=batch.items,
            ),
        )
        state.run = result.mission
        await publish_after_commit(self.events, self.clock, state.run)
        raw_review_manifests = state.run.snapshot_json.get("review_candidate_manifests")
        review_manifests = dict(raw_review_manifests) if isinstance(raw_review_manifests, dict) else {}
        for item in result.items:
            review_manifests[item.review_item_id] = {
                "review_item_id": item.review_item_id,
                "artifact_kind": item.preview_json.get("artifact_kind"),
                "target_kind": item.target_kind,
                "target_room": item.target_room,
                "target_ref": item.target_ref,
                "preview_hash": item.preview_hash,
                "preview_ref": item.preview_ref,
                "status": item.status.value,
            }
        review_manifests = dict(list(review_manifests.items())[-100:])
        snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
        snapshot = self._merge_snapshot(
            snapshot,
            {"review_candidate_manifests": review_manifests},
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="status_update",
                    operation_id=decision.operation_id,
                    phase=MissionItemPhase.COMPLETED,
                    producer="review_candidate",
                    summary=batch.summary,
                    payload_json={"review_item_ids": [item.review_item_id for item in batch.items]},
                )
            ],
            snapshot=snapshot,
        )
        return None

    async def _ensure_stage_start_allowed(
        self,
        state: _SliceState,
        decision: MissionAgentDecision,
    ) -> bool:
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
            allowed, missing = await self.quality.can_start(state.run, stage_id)
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
            patch=MissionRunPatchPayload(active_subagent_count_delta=1 if kind == "subagent" else 0),
        )

    async def _recover_inflight_operation(self, state: _SliceState) -> bool:
        inflight = state.run.snapshot_json.get("inflight_operation")
        if not isinstance(inflight, dict):
            return False
        if state.tool_steps >= self.limits.max_tool_steps:
            return False
        operation_id = str(inflight.get("operation_id") or "")
        kind = str(inflight.get("kind") or "")
        item_seq = int(inflight.get("call_item_seq") or 0)
        call_item = await self._load_item(state.run.mission_id, item_seq)
        if call_item is None or call_item.operation_id != operation_id:
            await self._clear_invalid_inflight(state, operation_id)
            return True
        state.tool_steps += 1
        if kind == "tool":
            tool_name = str(call_item.payload_json.get("tool_name") or "")
            arguments = call_item.payload_json.get("arguments") or {}
            if not tool_name or not isinstance(arguments, dict):
                await self._clear_invalid_inflight(state, operation_id)
                return True
            await self._execute_tool_operation(
                state,
                operation_id=operation_id,
                tool_name=tool_name,
                arguments=arguments,
                stage_id=call_item.stage_id,
            )
            return True
        if kind == "subagent":
            task_summary = str(call_item.payload_json.get("task_summary") or "")
            input_scope = call_item.payload_json.get("input_scope") or {}
            raw_frozen_context = call_item.payload_json.get("frozen_context")
            if (
                not task_summary
                or not isinstance(input_scope, dict)
                or not isinstance(raw_frozen_context, dict)
            ):
                await self._clear_invalid_inflight(state, operation_id)
                return True
            try:
                frozen_context = SubagentFrozenContext.model_validate(
                    raw_frozen_context
                )
            except ValueError:
                await self._clear_invalid_inflight(state, operation_id)
                return True
            await self._execute_subagent_operation(
                state,
                operation_id=operation_id,
                task_summary=task_summary,
                input_scope=input_scope,
                stage_id=call_item.stage_id,
                frozen_context=frozen_context,
            )
            return True
        await self._clear_invalid_inflight(state, operation_id)
        return True

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
        try:
            outcome = await self._invoke_with_deadline(
                self.subagents.run(
                    SubagentExecutionRequest(
                        mission=state.run,
                        operation_id=operation_id,
                        task_summary=task_summary,
                        input_scope=input_scope,
                        stage_id=stage_id,
                        frozen_context=frozen_context,
                        deadline_monotonic=state.deadline_monotonic,
                    )
                ),
                state,
            )
        except Exception as exc:
            outcome = self._failed_port_outcome("Subagent did not complete", exc)
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
        if (
            latest is not None
            and latest.lease_owner == state.worker_id
            and latest.lease_epoch == state.run.lease_epoch
            and _status_value(latest) == _status_value(state.run)
        ):
            state.run = latest
        if outcome.status == MissionPortOutcomeStatus.WAITING:
            assert outcome.pause_request is not None
            snapshot = self._pause_snapshot(
                self._merge_snapshot(state.run.snapshot_json, outcome.snapshot_patch),
                outcome.pause_request,
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
                    self._pause_item(outcome.pause_request),
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
        if outcome.status == MissionPortOutcomeStatus.FAILED:
            snapshot = self._merge_snapshot(
                snapshot,
                {
                    "degraded_reason": "tool_partial",
                    "last_error": {
                        "operation_id": operation_id,
                        "summary": outcome.summary[:500],
                    },
                    "next_actions": ["replan_after_operation_failure"],
                },
            )
        await self._append(
            state,
            items=[
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
                )
            ],
            snapshot=snapshot,
            patch=MissionRunPatchPayload(
                evidence_count_delta=outcome.evidence_count_delta,
                artifact_count_delta=outcome.artifact_count_delta,
                active_subagent_count_delta=-1 if kind == "subagent" else 0,
            ),
        )
        return None

    async def _pause_under_fence(
        self,
        state: _SliceState,
        request: MissionPauseRequest,
    ) -> None:
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
    ) -> None:
        operation_id = decision.operation_id or decision.decision_id
        snapshot = self._decision_snapshot(state.run.snapshot_json, decision)
        snapshot = self._merge_snapshot(
            snapshot,
            {
                "degraded_reason": "tool_partial",
                "last_error": {
                    "operation_id": operation_id,
                    "error_type": type(exc).__name__,
                },
                "next_actions": ["replan_after_operation_failure"],
            },
        )
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type=item_type,
                    operation_id=operation_id,
                    phase=MissionItemPhase.FAILED,
                    stage_id=decision.stage_id,
                    producer=producer,
                    summary=summary,
                    payload_json={"error_type": type(exc).__name__},
                )
            ],
            snapshot=snapshot,
        )

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

    @staticmethod
    def _missing_required_stage_acceptance(run: MissionRunPayload) -> list[str]:
        raw_required = run.runtime_context_json.get("required_stage_ids")
        if not isinstance(raw_required, list):
            raw_required = run.snapshot_json.get("required_stage_ids")
        if not isinstance(raw_required, list) or not raw_required:
            return []
        acceptance = run.snapshot_json.get("stage_acceptance")
        results = acceptance if isinstance(acceptance, dict) else {}
        missing: list[str] = []
        for raw_stage_id in raw_required:
            stage_id = str(raw_stage_id).strip()
            result = results.get(stage_id)
            if not stage_id or not isinstance(result, dict) or result.get("result") != "pass":
                missing.append(stage_id or "<blank-stage-id>")
        return missing

    async def _record_loop_failure(
        self,
        state: _SliceState,
        exc: BaseException,
    ) -> bool:
        guard = state.run.snapshot_json.get("loop_guard")
        current_guard = guard if isinstance(guard, dict) else {}
        transient = _is_transient_agent_failure(exc)
        failures = int(current_guard.get("consecutive_failures") or 0) + (0 if transient else 1)
        transient_failures = int(current_guard.get("transient_failures") or 0) + (1 if transient else 0)
        terminal = not transient and failures >= self.limits.max_consecutive_failures
        snapshot = self._merge_snapshot(
            state.run.snapshot_json,
            {
                "loop_guard": {
                    "consecutive_failures": failures,
                    "transient_failures": transient_failures,
                },
                "last_error": {
                    "kind": "transient_model_failure" if transient else "agent_step_failure",
                    "error_type": type(exc).__name__,
                    "detail": str(exc)[:500],
                },
                "next_actions": [] if terminal else ["retry_agent_step_after_backoff" if transient else "retry_agent_step"],
            },
        )
        if terminal:
            snapshot = self._merge_snapshot(snapshot, {"failure_reason": "repeated_failure"})
        await self._append(
            state,
            items=[
                MissionItemDraftPayload(
                    item_type="error",
                    phase=MissionItemPhase.FAILED,
                    producer="mission_runtime",
                    summary=(
                        "Model service was temporarily unavailable; Mission will retry"
                        if transient
                        else "Mission agent step did not complete"
                    ),
                    payload_json={
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:500],
                        "attempt": transient_failures if transient else failures,
                        "recoverable": transient,
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
                "budgets": {
                    "last_slice_model_turns": state.model_turns,
                    "last_slice_tool_steps": state.tool_steps,
                },
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
                        "missing_criteria": [
                            str(item) for item in raw.get("missing_criteria") or ()
                        ][:20],
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
        manifests = run.snapshot_json.get("review_candidate_manifests")
        review_refs = list(manifests)[-20:] if isinstance(manifests, dict) else []
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
            "review_candidate_refs": review_refs,
            "recent_decisions": recent_decisions[-12:],
            "failure_history": failure_history[-12:],
            "pending_request": dict(pending_request) if isinstance(pending_request, dict) else None,
            "next_actions": [
                str(item) for item in run.snapshot_json.get("next_actions") or ()
            ][:10],
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

    async def _heartbeat_if_due(self, state: _SliceState) -> None:
        now = self.clock.monotonic()
        if now - state.last_heartbeat_monotonic < self.limits.heartbeat_interval_seconds:
            return
        state.run = await self.store.heartbeat_lease(
            state.run.mission_id,
            MissionLeaseHeartbeatPayload(
                worker_id=state.worker_id,
                lease_epoch=state.run.lease_epoch,
                expected_state_version=state.run.state_version,
                ttl_seconds=self.limits.lease_ttl_seconds,
            ),
        )
        state.last_heartbeat_monotonic = now

    async def _build_loop_context(self, state: _SliceState) -> MissionLoopContext:
        recent = await self._recent_items(state.run)
        pending_refs = state.run.snapshot_json.get("pending_command_refs")
        pending_seqs = {int(item.get("seq") or 0) for item in pending_refs if isinstance(item, dict)} if isinstance(pending_refs, list) else set()
        pending = [item for item in recent if item.seq in pending_seqs]
        return MissionLoopContext(
            mission=state.run,
            pending_commands=pending,
            recent_items=recent,
            model_turns_used=state.model_turns,
            tool_steps_used=state.tool_steps,
            deadline_monotonic=state.deadline_monotonic,
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
        async with asyncio.timeout(remaining):
            return await awaitable

    async def _publish_wakeup(
        self,
        mission_id: str,
        *,
        command_hint: str | None = None,
        delay_seconds: int = 0,
    ) -> bool:
        try:
            await self.wakeups.publish(
                mission_id,
                command_hint=command_hint,
                delay_seconds=delay_seconds,
            )
        except Exception:
            logger.warning(
                "Mission wakeup publish failed for %s; reconciler will recover it",
                mission_id,
                exc_info=True,
            )
            return False
        return True

    async def _settle_best_effort(self, mission: MissionRunPayload) -> None:
        try:
            await self.billing.settle(mission)
        except Exception:
            logger.warning(
                "Mission billing settlement deferred for %s",
                mission.mission_id,
                exc_info=True,
            )

    def _slice_budget_exhausted(self, state: _SliceState) -> bool:
        return self.clock.monotonic() >= state.deadline_monotonic or state.model_turns >= self.limits.max_model_turns or state.tool_steps >= self.limits.max_tool_steps

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
    def _billing_snapshot(outcome: BillingOutcome, *, state: str) -> dict[str, Any]:
        return {
            "state": state,
            "free_policy": outcome.free_policy,
            "reservation_id": outcome.reservation_id,
        }

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
                    **request.pending_request,
                },
                "next_actions": ["wait_for_user_input"],
            },
        )

    async def _operation_has_terminal(
        self,
        mission_id: str,
        operation_id: str,
    ) -> bool:
        items = await self.store.list_items(
            mission_id,
            limit=100,
            operation_id=operation_id,
        )
        return any(item.phase in {MissionItemPhase.COMPLETED, MissionItemPhase.FAILED} for item in items)

    @staticmethod
    def _failed_port_outcome(summary: str, exc: BaseException) -> MissionPortOutcome:
        return MissionPortOutcome(
            status=MissionPortOutcomeStatus.FAILED,
            summary=summary,
            payload_json={"error_type": type(exc).__name__},
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
                target.extend(str(item) for item in candidate_value if item)
            else:
                _collect_ref_values(candidate_value, key, target)
    elif isinstance(value, list):
        for item in value:
            _collect_ref_values(item, key, target)


def _is_transient_agent_failure(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code in {408, 409, 429} or status_code >= 500):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "PoolTimeout",
        "RateLimitError",
        "ReadError",
        "ReadTimeout",
    }


def _transient_retry_delay_seconds(run: MissionRunPayload) -> int:
    guard = run.snapshot_json.get("loop_guard")
    attempt = int(guard.get("transient_failures") or 1) if isinstance(guard, dict) else 1
    return min(5 * (2 ** min(max(attempt - 1, 0), 4)), 60)


__all__ = [
    "MissionResumeRequestMismatchError",
    "MissionRuntime",
    "MissionStartRejectedError",
]

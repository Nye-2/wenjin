from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionCancelPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionDispatchReleasePayload,
    MissionItemPayload,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionOperationClaimPayload,
    MissionOperationClaimResultPayload,
    MissionOperationFinishPayload,
    MissionOperationFinishResultPayload,
    MissionOperationReceiptPayload,
    MissionOperationStatus,
    MissionResumePayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewItemsResultPayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPayload,
    MissionStatus,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    BillingOutcome,
    MissionAgentDecision,
    MissionEventEnvelope,
    MissionLoopContext,
    MissionPortOutcome,
    MissionPortOutcomeStatus,
    MissionStartRequest,
    ReviewCandidateBatch,
    StageQualityOutcome,
    StageQualityVerdict,
)
from src.mission_runtime.runtime import MissionRuntime
from src.review_commit_runtime.policy import project_review_policy


def conflict(message: str = "conflict") -> DataServiceClientError:
    return DataServiceClientError(message, status_code=409)


class MutableClock:
    def __init__(self) -> None:
        self._monotonic = 100.0
        self._now = datetime(2026, 7, 10, tzinfo=UTC)

    def monotonic(self) -> float:
        return self._monotonic

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)


class FakeMissionStore:
    def __init__(self, clock: MutableClock) -> None:
        self.clock = clock
        self.runs: dict[str, MissionRunPayload] = {}
        self.items: dict[str, list[MissionItemPayload]] = {}
        self.review_items: dict[str, dict[str, MissionReviewItemPayload]] = {}
        self.operations: dict[tuple[str, str], MissionOperationReceiptPayload] = {}
        self.idempotency: dict[tuple[str, str], str] = {}
        self._mission_counter = 0
        self._item_counter = 0
        self.claim_runnable_calls = 0

    @staticmethod
    def _copy_run(run: MissionRunPayload) -> MissionRunPayload:
        return run.model_copy(deep=True)

    def _require_run(self, mission_id: str) -> MissionRunPayload:
        return self.runs[mission_id]

    def _require_version(self, run: MissionRunPayload, expected: int) -> None:
        if run.state_version != expected:
            raise conflict("stale state version")

    def _require_fence(
        self,
        run: MissionRunPayload,
        *,
        owner: str,
        epoch: int,
        version: int,
    ) -> None:
        self._require_version(run, version)
        if run.status.value in {"completed", "failed", "cancelled"} or run.lease_owner != owner or run.lease_epoch != epoch or run.lease_expires_at is None or run.lease_expires_at <= self.clock.now():
            raise conflict("lease fence rejected")

    def _append_drafts(
        self,
        run: MissionRunPayload,
        drafts: list[Any],
    ) -> list[MissionItemPayload]:
        appended: list[MissionItemPayload] = []
        for draft in drafts:
            self._item_counter += 1
            run.last_item_seq += 1
            item = MissionItemPayload(
                id=f"item-{self._item_counter}",
                mission_id=run.mission_id,
                seq=run.last_item_seq,
                item_type=draft.item_type,
                operation_id=draft.operation_id,
                phase=draft.phase,
                stage_id=draft.stage_id,
                producer=draft.producer,
                summary=draft.summary,
                risk_level=draft.risk_level,
                payload_json=draft.payload_json,
                payload_ref=draft.payload_ref,
                created_at=self.clock.now(),
            )
            self.items[run.mission_id].append(item)
            appended.append(item)
        return appended

    def _apply_patch(self, run: MissionRunPayload, command: MissionAppendPayload) -> None:
        if command.snapshot_json is not None:
            run.snapshot_json = dict(command.snapshot_json)
        patch = command.patch
        fields = patch.model_fields_set
        if patch.status is not None:
            run.status = patch.status
            if patch.status.value in {"planning", "running"} and run.started_at is None:
                run.started_at = self.clock.now()
            if patch.status.value in {"waiting", "completed", "failed", "cancelled"}:
                run.lease_owner = None
                run.lease_expires_at = None
            if patch.status.value in {"completed", "failed", "cancelled"}:
                run.completed_at = self.clock.now()
                run.next_wakeup_at = None
        if "active_stage_id" in fields:
            run.active_stage_id = patch.active_stage_id
        if "context_checkpoint_ref" in fields:
            run.context_checkpoint_ref = patch.context_checkpoint_ref
        if "next_wakeup_at" in fields and run.status.value not in {
            "completed",
            "failed",
            "cancelled",
        }:
            run.next_wakeup_at = patch.next_wakeup_at
        run.evidence_count += patch.evidence_count_delta
        run.artifact_count += patch.artifact_count_delta
        run.active_subagent_count += patch.active_subagent_count_delta

    def _touch(self, run: MissionRunPayload) -> None:
        run.state_version += 1
        run.updated_at = self.clock.now()

    async def create(self, command: MissionCreatePayload) -> MissionCreateResultPayload:
        key = (
            command.workspace_id,
            command.mission_idempotency_key or "",
        )
        if command.mission_idempotency_key and key in self.idempotency:
            existing = self.runs[self.idempotency[key]]
            if existing.objective != command.objective:
                raise conflict("idempotency key reused")
            return MissionCreateResultPayload(
                mission=self._copy_run(existing),
                created=False,
            )
        self._mission_counter += 1
        mission_id = f"mission-{self._mission_counter}"
        now = self.clock.now()
        run = MissionRunPayload(
            mission_id=mission_id,
            parent_mission_id=command.parent_mission_id,
            workspace_id=command.workspace_id,
            thread_id=command.thread_id,
            user_id=command.user_id,
            workspace_type=command.workspace_type,
            mission_policy_id=command.mission_policy_id,
            title=command.title,
            objective=command.objective,
            status="created",
            review_mode=command.review_mode,
            active_stage_id=None,
            model_id=command.model_id,
            reasoning_effort=command.reasoning_effort,
            snapshot_json=dict(command.snapshot_json),
            runtime_context_json=dict(command.runtime_context_json),
            context_checkpoint_ref=None,
            pending_review_count=0,
            evidence_count=0,
            artifact_count=0,
            active_subagent_count=0,
            mission_idempotency_key=command.mission_idempotency_key,
            last_command_seq=0,
            last_applied_command_seq=0,
            next_wakeup_at=now,
            lease_owner=None,
            lease_epoch=0,
            lease_expires_at=None,
            state_version=0,
            last_item_seq=0,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        self.runs[mission_id] = run
        self.items[mission_id] = []
        self.review_items[mission_id] = {}
        if command.mission_idempotency_key:
            self.idempotency[key] = mission_id
        return MissionCreateResultPayload(mission=self._copy_run(run), created=True)

    async def get(self, mission_id: str) -> MissionRunPayload | None:
        run = self.runs.get(mission_id)
        return self._copy_run(run) if run is not None else None

    async def claim_lease(
        self,
        mission_id: str,
        command: MissionLeaseClaimPayload,
    ) -> MissionRunPayload:
        run = self._require_run(mission_id)
        self._require_version(run, command.expected_state_version)
        if run.status.value in {"completed", "failed", "cancelled"}:
            raise conflict("terminal")
        if run.lease_owner is not None and run.lease_expires_at is not None and run.lease_expires_at > self.clock.now():
            raise conflict("active lease")
        run.lease_owner = command.worker_id
        run.lease_epoch += 1
        run.lease_expires_at = self.clock.now() + timedelta(seconds=command.ttl_seconds)
        run.next_wakeup_at = None
        run.dispatch_owner = None
        run.dispatch_expires_at = None
        self._touch(run)
        return self._copy_run(run)

    async def heartbeat_lease(
        self,
        mission_id: str,
        command: MissionLeaseHeartbeatPayload,
    ) -> MissionRunPayload:
        run = self._require_run(mission_id)
        self._require_fence(
            run,
            owner=command.worker_id,
            epoch=command.lease_epoch,
            version=command.expected_state_version,
        )
        run.lease_expires_at = self.clock.now() + timedelta(seconds=command.ttl_seconds)
        self._touch(run)
        return self._copy_run(run)

    async def release_lease(
        self,
        mission_id: str,
        command: MissionLeaseReleasePayload,
    ) -> MissionRunPayload:
        run = self._require_run(mission_id)
        self._require_fence(
            run,
            owner=command.worker_id,
            epoch=command.lease_epoch,
            version=command.expected_state_version,
        )
        run.lease_owner = None
        run.lease_expires_at = None
        run.next_wakeup_at = command.next_wakeup_at
        self._touch(run)
        return self._copy_run(run)

    async def claim_runnable(
        self,
        command: MissionRunnableBatchClaimPayload,
    ) -> list[MissionRunPayload]:
        self.claim_runnable_calls += 1
        result: list[MissionRunPayload] = []
        for run in self.runs.values():
            if len(result) >= command.limit:
                break
            due = (run.next_wakeup_at is not None and run.next_wakeup_at <= self.clock.now()) or (run.lease_expires_at is not None and run.lease_expires_at <= self.clock.now())
            lease_available = run.lease_owner is None or run.lease_expires_at is None or run.lease_expires_at <= self.clock.now()
            dispatch_available = run.dispatch_owner is None or run.dispatch_expires_at is None or run.dispatch_expires_at <= self.clock.now()
            if run.status.value not in {"completed", "failed", "cancelled"} and due and lease_available and dispatch_available:
                run.dispatch_owner = command.worker_id
                run.dispatch_epoch += 1
                run.dispatch_expires_at = self.clock.now() + timedelta(seconds=command.ttl_seconds)
                self._touch(run)
                result.append(self._copy_run(run))
        return result

    async def release_dispatch(self, mission_id: str, command: MissionDispatchReleasePayload) -> MissionRunPayload:
        run = self._require_run(mission_id)
        if run.dispatch_owner != command.worker_id or run.dispatch_epoch != command.dispatch_epoch:
            raise conflict("dispatch fence")
        run.dispatch_owner = None
        run.dispatch_expires_at = None
        self._touch(run)
        return self._copy_run(run)

    async def claim_operation(self, mission_id: str, command: MissionOperationClaimPayload) -> MissionOperationClaimResultPayload:
        key = (mission_id, command.operation_key)
        existing = self.operations.get(key)
        if existing is not None:
            return MissionOperationClaimResultPayload(receipt=existing.model_copy(deep=True), acquired=False)
        now = self.clock.now()
        receipt = MissionOperationReceiptPayload(
            receipt_id=f"receipt-{len(self.operations) + 1}", mission_id=mission_id,
            operation_key=command.operation_key, kind=command.kind,
            request_hash=command.request_hash, status=MissionOperationStatus.CLAIMED,
            claimant=command.claimant, lease_epoch=command.lease_epoch,
            lease_expires_at=now + timedelta(seconds=command.ttl_seconds), attempt=1,
            claimed_at=now, updated_at=now,
        )
        self.operations[key] = receipt
        return MissionOperationClaimResultPayload(receipt=receipt.model_copy(deep=True), acquired=True)

    async def get_operation(self, mission_id: str, operation_key: str) -> MissionOperationReceiptPayload | None:
        value = self.operations.get((mission_id, operation_key))
        return value.model_copy(deep=True) if value else None

    async def finish_operation(self, mission_id: str, command: MissionOperationFinishPayload) -> MissionOperationFinishResultPayload:
        receipt = self.operations[(mission_id, command.operation_key)]
        if receipt.status is not MissionOperationStatus.CLAIMED:
            return MissionOperationFinishResultPayload(receipt=receipt.model_copy(deep=True), finalized=False)
        receipt.status = command.status
        receipt.receipt_json = dict(command.receipt_json)
        receipt.payload_ref = command.payload_ref
        receipt.lease_expires_at = None
        receipt.completed_at = self.clock.now()
        receipt.updated_at = self.clock.now()
        return MissionOperationFinishResultPayload(receipt=receipt.model_copy(deep=True), finalized=True)

    async def append_items(
        self,
        mission_id: str,
        command: MissionAppendPayload,
    ) -> MissionAppendResultPayload:
        run = self._require_run(mission_id)
        self._require_fence(
            run,
            owner=command.lease_owner,
            epoch=command.lease_epoch,
            version=command.expected_state_version,
        )
        appended = self._append_drafts(run, command.items)
        self._apply_patch(run, command)
        self._touch(run)
        return MissionAppendResultPayload(
            mission=self._copy_run(run),
            items=[item.model_copy(deep=True) for item in appended],
        )

    async def list_items(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> list[MissionItemPayload]:
        items = [
            item
            for item in self.items[mission_id]
            if item.seq > after_seq
            and (item_type is None or item.item_type == item_type)
            and (operation_id is None or item.operation_id == operation_id)
        ]
        return [item.model_copy(deep=True) for item in items[:limit]]

    async def append_command(
        self,
        mission_id: str,
        *,
        command_id: str,
        command_type: str,
        summary: str,
        payload_json: dict[str, Any] | None = None,
    ) -> MissionItemPayload:
        run = self._require_run(mission_id)
        for item in self.items[mission_id]:
            if item.item_type == "command_received" and item.operation_id == command_id:
                return item.model_copy(deep=True)
        from src.dataservice_client.contracts.mission import MissionItemDraftPayload

        payload = dict(payload_json or {})
        payload["command_type"] = command_type
        item = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="command_received",
                    operation_id=command_id,
                    phase="completed",
                    producer="workspace_agent",
                    summary=summary,
                    payload_json=payload,
                )
            ],
        )[0]
        run.last_command_seq = item.seq
        run.next_wakeup_at = self.clock.now()
        self._touch(run)
        return item.model_copy(deep=True)

    async def list_unapplied_commands(
        self,
        mission_id: str,
        *,
        limit: int = 100,
    ) -> list[MissionItemPayload]:
        run = self._require_run(mission_id)
        return [item.model_copy(deep=True) for item in self.items[mission_id] if item.item_type == "command_received" and run.last_applied_command_seq < item.seq <= run.last_command_seq][:limit]

    async def apply_commands(
        self,
        mission_id: str,
        command: MissionApplyCommandsPayload,
    ) -> MissionAppendResultPayload:
        run = self._require_run(mission_id)
        self._require_fence(
            run,
            owner=command.lease_owner,
            epoch=command.lease_epoch,
            version=command.expected_state_version,
        )
        if command.through_command_seq <= run.last_applied_command_seq:
            return MissionAppendResultPayload(mission=self._copy_run(run), items=[])
        if command.through_command_seq > run.last_command_seq:
            raise conflict("cursor beyond command")
        appended = self._append_drafts(run, command.items)
        run.last_applied_command_seq = command.through_command_seq
        self._apply_patch(run, command)
        self._touch(run)
        return MissionAppendResultPayload(
            mission=self._copy_run(run),
            items=[item.model_copy(deep=True) for item in appended],
        )

    async def resume(
        self,
        mission_id: str,
        command: MissionResumePayload,
    ) -> MissionAppendResultPayload:
        run = self._require_run(mission_id)
        for item in self.items[mission_id]:
            if item.item_type == "resume_input" and item.operation_id == command.request_id:
                return MissionAppendResultPayload(
                    mission=self._copy_run(run),
                    items=[item.model_copy(deep=True)],
                )
        if run.status != MissionStatus.WAITING:
            raise conflict("not waiting")
        from src.dataservice_client.contracts.mission import MissionItemDraftPayload

        item = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="resume_input",
                    operation_id=command.request_id,
                    phase="completed",
                    producer=command.producer,
                    payload_json=command.input_json,
                )
            ],
        )[0]
        snapshot = dict(run.snapshot_json)
        snapshot.pop("waiting_reason", None)
        snapshot.pop("pending_request", None)
        run.snapshot_json = snapshot
        run.status = MissionStatus.PLANNING
        run.next_wakeup_at = self.clock.now()
        self._touch(run)
        return MissionAppendResultPayload(
            mission=self._copy_run(run),
            items=[item.model_copy(deep=True)],
        )

    async def cancel(
        self,
        mission_id: str,
        command: MissionCancelPayload,
    ) -> MissionAppendResultPayload:
        run = self._require_run(mission_id)
        for item in self.items[mission_id]:
            if item.item_type == "command_received" and item.operation_id == command.request_id:
                return MissionAppendResultPayload(
                    mission=self._copy_run(run),
                    items=[item.model_copy(deep=True)],
                )
        if run.status.value in {"completed", "failed", "cancelled"}:
            raise conflict("terminal")
        from src.dataservice_client.contracts.mission import MissionItemDraftPayload

        item = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="command_received",
                    operation_id=command.request_id,
                    phase="completed",
                    producer=command.producer,
                    summary=command.reason,
                    payload_json={"command_type": "cancel", "reason": command.reason},
                )
            ],
        )[0]
        run.last_command_seq = item.seq
        run.last_applied_command_seq = item.seq
        run.status = MissionStatus.CANCELLED
        run.lease_owner = None
        run.lease_expires_at = None
        run.next_wakeup_at = None
        run.completed_at = self.clock.now()
        self._touch(run)
        return MissionAppendResultPayload(
            mission=self._copy_run(run),
            items=[item.model_copy(deep=True)],
        )

    async def create_review_items(
        self,
        mission_id: str,
        command: MissionReviewItemsCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        run = self._require_run(mission_id)
        existing = self.review_items[mission_id]
        if all(item.review_item_id in existing for item in command.items):
            return MissionReviewItemsResultPayload(
                mission=self._copy_run(run),
                items=[existing[item.review_item_id].model_copy(deep=True) for item in command.items],
            )
        self._require_fence(
            run,
            owner=command.lease_owner,
            epoch=command.lease_epoch,
            version=command.expected_state_version,
        )
        now = self.clock.now()
        created: list[MissionReviewItemPayload] = []
        from src.dataservice_client.contracts.mission import MissionItemDraftPayload

        for draft in command.items:
            encoded_preview = json.dumps(
                draft.preview_json,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            policy = project_review_policy(
                review_mode=run.review_mode,
                target_kind=draft.target_kind,
                target_room=draft.target_room,
                risk_level=draft.risk_level.value,
            )
            payload = MissionReviewItemPayload(
                review_item_id=draft.review_item_id,
                mission_id=mission_id,
                source_item_seq=draft.source_item_seq,
                target_kind=draft.target_kind,
                target_room=draft.target_room,
                target_ref=draft.target_ref,
                base_revision_ref=draft.base_revision_ref,
                base_hash=draft.base_hash,
                title=draft.title,
                summary=draft.summary,
                risk_level=draft.risk_level,
                status="pending",
                review_required_reason=draft.review_required_reason,
                preview_json=draft.preview_json,
                preview_ref=draft.preview_ref,
                preview_hash=hashlib.sha256(encoded_preview).hexdigest(),
                preview_expires_at=draft.preview_expires_at,
                requires_explicit_review=policy.requires_explicit_review,
                batch_acceptable=policy.batch_acceptable,
                suggested_selected=policy.suggested_selected,
                decision_json=None,
                decided_by=None,
                decided_at=None,
                created_at=now,
                updated_at=now,
            )
            existing[draft.review_item_id] = payload
            created.append(payload)
            self._append_drafts(
                run,
                [
                    MissionItemDraftPayload(
                        item_type="review_candidate_created",
                        operation_id=draft.review_item_id,
                        phase="completed",
                        producer="mission_runtime",
                        summary=draft.title,
                        risk_level=draft.risk_level,
                        payload_json={"review_item_id": draft.review_item_id},
                    )
                ],
            )
        run.pending_review_count += len(created)
        self._touch(run)
        return MissionReviewItemsResultPayload(
            mission=self._copy_run(run),
            items=[item.model_copy(deep=True) for item in created],
        )


DecisionFactory = Callable[[MissionLoopContext], Any]


class ScriptedAgent:
    def __init__(self, decisions: list[MissionAgentDecision | DecisionFactory]) -> None:
        self.decisions = list(decisions)
        self.contexts: list[MissionLoopContext] = []

    async def decide(self, context: MissionLoopContext) -> MissionAgentDecision:
        self.contexts.append(context.model_copy(deep=True))
        if not self.decisions:
            raise RuntimeError("scripted agent exhausted")
        decision = self.decisions.pop(0)
        if callable(decision):
            decision = decision(context)
            if inspect.isawaitable(decision):
                decision = await decision
        return decision


class FakeStartContext:
    async def pin(self, request: MissionStartRequest) -> MissionStartRequest:
        return request


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.effects: set[str] = set()
        self.crash_once: set[str] = set()
        self._crashed: set[str] = set()
        self.outcomes: dict[str, MissionPortOutcome] = {}

    async def execute(self, request: Any) -> MissionPortOutcome:
        self.calls.append(request.operation_id)
        self.effects.add(request.operation_id)
        if request.operation_id in self.crash_once and request.operation_id not in self._crashed:
            self._crashed.add(request.operation_id)
            raise SimulatedWorkerCrash()
        return self.outcomes.get(
            request.operation_id,
            MissionPortOutcome(
                status=MissionPortOutcomeStatus.COMPLETED,
                summary=f"tool {request.operation_id} completed",
                payload_json={"receipt": request.operation_id},
            ),
        )


class SimulatedWorkerCrash(BaseException):
    pass


class FakeSubagents:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, request: Any) -> MissionPortOutcome:
        self.calls.append(request.operation_id)
        return MissionPortOutcome(
            status=MissionPortOutcomeStatus.COMPLETED,
            summary="subagent completed",
            payload_json={"result_ref": request.operation_id},
        )


class FakeQuality:
    def __init__(
        self,
        verdict: StageQualityVerdict = StageQualityVerdict.PASS,
        *,
        missing_prerequisites: tuple[str, ...] = (),
    ) -> None:
        self.verdict = verdict
        self.missing_prerequisites = missing_prerequisites
        self.calls: list[str] = []

    async def can_start(self, mission: Any, stage_id: str) -> tuple[bool, tuple[str, ...]]:
        del mission, stage_id
        return not self.missing_prerequisites, self.missing_prerequisites

    async def evaluate(self, request: Any) -> StageQualityOutcome:
        self.calls.append(request.operation_id)
        return StageQualityOutcome(
            verdict=self.verdict,
            summary=f"quality {self.verdict.value}",
        )


class FakeReviewCandidates:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def build_candidates(self, request: Any) -> ReviewCandidateBatch:
        from src.dataservice_client.contracts.mission import MissionReviewItemDraftPayload

        self.calls.append(request.operation_id)
        return ReviewCandidateBatch(
            summary="review candidate ready",
            items=[
                MissionReviewItemDraftPayload(
                    review_item_id=f"review-{request.operation_id}",
                    target_kind="document",
                    target_room="documents",
                    title="Research draft",
                    risk_level="medium",
                    preview_json={"text": "draft"},
                )
            ],
        )


class FakeBilling:
    def __init__(self) -> None:
        self.preflight_outcome = BillingOutcome(allowed=True, free_policy=True)
        self.reservation_outcome = BillingOutcome(allowed=True, free_policy=True)
        self.settled: list[str] = []

    async def preflight(self, _request: MissionStartRequest) -> BillingOutcome:
        return self.preflight_outcome

    async def ensure_reservation(self, _mission: MissionRunPayload) -> BillingOutcome:
        return self.reservation_outcome

    async def settle(self, mission: MissionRunPayload) -> None:
        self.settled.append(mission.mission_id)


class FakeEvents:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[MissionEventEnvelope] = []

    async def publish(self, event: MissionEventEnvelope) -> None:
        if self.fail:
            raise RuntimeError("event stream unavailable")
        self.events.append(event)


class FakeWakeups:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, str | None]] = []
        self.delays: list[int] = []

    async def publish(
        self,
        mission_id: str,
        *,
        command_hint: str | None = None,
        delay_seconds: int = 0,
    ) -> None:
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.published.append((mission_id, command_hint))
        self.delays.append(delay_seconds)


def start_request(**overrides: Any) -> MissionStartRequest:
    values: dict[str, Any] = {
        "workspace_id": "workspace-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "workspace_type": "sci",
        "title": "Federated PEFT study",
        "objective": "Map research gaps for federated LLM fine-tuning",
        "mission_idempotency_key": "start-1",
        "model_id": "gpt-5.5",
        "reasoning_effort": "xhigh",
    }
    values.update(overrides)
    return MissionStartRequest(**values)


@pytest.fixture
def runtime_factory():
    def build(
        *,
        agent: Any,
        start_context: Any | None = None,
        clock: MutableClock | None = None,
        store: FakeMissionStore | None = None,
        tools: FakeTools | None = None,
        subagents: FakeSubagents | None = None,
        quality: FakeQuality | None = None,
        review: FakeReviewCandidates | None = None,
        billing: FakeBilling | None = None,
        events: FakeEvents | None = None,
        wakeups: FakeWakeups | None = None,
        limits: Any = None,
    ) -> tuple[MissionRuntime, dict[str, Any]]:
        resolved_clock = clock or MutableClock()
        resolved_store = store or FakeMissionStore(resolved_clock)
        deps = {
            "clock": resolved_clock,
            "store": resolved_store,
            "agent": agent,
            "start_context": start_context or FakeStartContext(),
            "tools": tools or FakeTools(),
            "subagents": subagents or FakeSubagents(),
            "quality": quality or FakeQuality(),
            "review": review or FakeReviewCandidates(),
            "billing": billing or FakeBilling(),
            "events": events or FakeEvents(),
            "wakeups": wakeups or FakeWakeups(),
        }
        runtime = MissionRuntime(
            store=deps["store"],
            agent=deps["agent"],
            start_context=deps["start_context"],
            tools=deps["tools"],
            subagents=deps["subagents"],
            quality=deps["quality"],
            review_candidates=deps["review"],
            billing=deps["billing"],
            events=deps["events"],
            wakeups=deps["wakeups"],
            limits=limits,
            clock=deps["clock"],
        )
        return runtime, deps

    return build

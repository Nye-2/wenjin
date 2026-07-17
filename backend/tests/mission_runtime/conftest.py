from __future__ import annotations

import hashlib
import inspect
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.contracts.mission_budget import (
    resource_delta_for_item,
    resource_usage_from_snapshot,
    snapshot_with_resource_usage,
)
from src.contracts.model_usage import ModelCallState, ModelUsage, ModelUsageReceipt
from src.contracts.review_policy import project_review_policy
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionDispatchReleasePayload,
    MissionItemPayload,
    MissionItemPhase,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionModelCallStatePayload,
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
    MissionUserCommandPayload,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    MissionAgentDecision,
    MissionAgentResponseError,
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

    def advance_wall_clock(self, seconds: float) -> None:
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
        self.admission_status = MissionStatus.PLANNING

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
        usage = resource_usage_from_snapshot(run.snapshot_json)
        appended: list[MissionItemPayload] = []
        for draft in drafts:
            usage = usage.add(
                resource_delta_for_item(
                    item_type=draft.item_type,
                    payload_json=draft.payload_json,
                )
            )
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
        run.snapshot_json = snapshot_with_resource_usage(
            run.snapshot_json,
            usage,
        )
        return appended

    def _apply_patch(self, run: MissionRunPayload, command: MissionAppendPayload) -> None:
        if command.snapshot_json is not None:
            run.snapshot_json = snapshot_with_resource_usage(
                command.snapshot_json,
                resource_usage_from_snapshot(run.snapshot_json),
            )
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
        if patch.review_mode is not None:
            run.review_mode = patch.review_mode
        if "context_checkpoint_ref" in fields:
            run.context_checkpoint_ref = patch.context_checkpoint_ref
        if "next_wakeup_at" in fields and run.status.value not in {
            "completed",
            "failed",
            "cancelled",
        }:
            run.next_wakeup_at = patch.next_wakeup_at
        run.evidence_count += sum(item.item_type == "evidence" for item in command.items)
        run.artifact_count += sum(
            item.item_type in {"artifact", "output"} for item in command.items
        )
        run.active_subagent_count += patch.active_subagent_count_delta

    def _touch(self, run: MissionRunPayload) -> None:
        run.state_version += 1
        run.updated_at = self.clock.now()

    def seed_items(
        self,
        mission_id: str,
        drafts: list[Any],
    ) -> list[MissionItemPayload]:
        """Seed receipt-backed facts before a runtime slice in integration tests."""
        run = self._require_run(mission_id)
        appended = self._append_drafts(run, drafts)
        run.evidence_count += sum(item.item_type == "evidence" for item in drafts)
        run.artifact_count += sum(
            item.item_type in {"artifact", "output"}
            for item in drafts
        )
        self._touch(run)
        return [item.model_copy(deep=True) for item in appended]

    async def admit(self, command: MissionCreatePayload) -> MissionCreateResultPayload:
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
        admission_status = self.admission_status
        snapshot = dict(command.snapshot_json)
        if admission_status is MissionStatus.WAITING:
            snapshot.update(
                {
                    "billing": {"state": "waiting", "estimated_credits": 10},
                    "waiting_reason": "budget",
                    "pending_request": {
                        "request_id": f"billing:{mission_id}",
                        "request_type": "budget_confirmation",
                        "required_credits": 10,
                    },
                }
            )
        else:
            snapshot["billing"] = {"state": "ready", "free_policy": True}
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
            status=admission_status,
            review_mode=command.review_mode,
            active_stage_id=None,
            model_id=command.model_id,
            reasoning_effort=command.reasoning_effort,
            snapshot_json=snapshot,
            runtime_context_json=dict(command.runtime_context_json),
            context_checkpoint_ref=None,
            pending_review_count=0,
            evidence_count=0,
            artifact_count=0,
            active_subagent_count=0,
            mission_idempotency_key=command.mission_idempotency_key,
            last_command_seq=0,
            last_applied_command_seq=0,
            next_wakeup_at=(now if admission_status is MissionStatus.PLANNING else None),
            lease_owner=None,
            lease_epoch=0,
            lease_expires_at=None,
            state_version=1,
            last_item_seq=1,
            created_at=now,
            updated_at=now,
            started_at=(now if admission_status is MissionStatus.PLANNING else None),
            completed_at=None,
        )
        self.runs[mission_id] = run
        self.items[mission_id] = [
            MissionItemPayload(
                id=f"admission-{mission_id}",
                mission_id=mission_id,
                seq=1,
                item_type="status_update",
                operation_id=None,
                phase=MissionItemPhase.COMPLETED,
                stage_id=None,
                producer="mission_admission",
                summary="Mission admission resolved",
                risk_level=None,
                payload_json={"status": admission_status.value},
                payload_ref=None,
                created_at=now,
            )
        ]
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
            claim_token=secrets.token_urlsafe(32),
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
        if receipt.claim_token != command.claim_token:
            raise conflict("operation claim fence")
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
        if command.items and all(
            item.item_type
            in {"model_call_started", "usage_receipt", "model_call_terminal"}
            for item in command.items
        ):
            replayed: list[MissionItemPayload] = []
            for draft in command.items:
                existing = [
                    item
                    for item in self.items[mission_id]
                    if item.item_type == draft.item_type
                    and item.operation_id == draft.operation_id
                ]
                if not existing:
                    break
                if len(existing) != 1:
                    raise conflict("duplicate model ledger rows")
                item = existing[0]
                if not (
                    item.phase == draft.phase
                    and item.stage_id == draft.stage_id
                    and item.producer == draft.producer
                    and item.summary == draft.summary
                    and item.risk_level == draft.risk_level
                    and item.payload_json == draft.payload_json
                    and item.payload_ref == draft.payload_ref
                ):
                    raise conflict("divergent model ledger replay")
                replayed.append(item)
            if len(replayed) == len(command.items):
                if (
                    run.status.value in {"completed", "failed", "cancelled"}
                    or run.lease_owner != command.lease_owner
                    or run.lease_epoch != command.lease_epoch
                    or run.lease_expires_at is None
                    or run.lease_expires_at <= self.clock.now()
                ):
                    raise conflict("lease fence rejected")
                return MissionAppendResultPayload(
                    mission=self._copy_run(run),
                    items=[item.model_copy(deep=True) for item in replayed],
                )
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

    async def list_model_call_states(
        self,
        mission_id: str,
    ) -> list[MissionModelCallStatePayload]:
        states: list[MissionModelCallStatePayload] = []
        for started in self.items[mission_id]:
            if started.item_type != "model_call_started":
                continue
            terminals = [
                item
                for item in self.items[mission_id]
                if item.operation_id == started.operation_id
                and item.item_type in {"usage_receipt", "model_call_terminal"}
            ]
            if len(terminals) > 1:
                raise conflict("duplicate model call terminal")
            terminal = terminals[0] if terminals else None
            if terminal is None:
                state = ModelCallState.OPEN
            elif terminal.item_type == "usage_receipt":
                state = ModelCallState.RECEIPT
            else:
                state = ModelCallState(str(terminal.payload_json["outcome"]))
            states.append(
                MissionModelCallStatePayload(
                    state=state,
                    started=started.model_copy(deep=True),
                    terminal=(
                        terminal.model_copy(deep=True)
                        if terminal is not None
                        else None
                    ),
                )
            )
        return states

    async def list_review_items(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
    ) -> list[MissionReviewItemPayload]:
        allowed = set(status or ())
        return [
            item.model_copy(deep=True)
            for item in self.review_items[mission_id].values()
            if not allowed or item.status.value in allowed
        ]

    async def append_command(
        self,
        mission_id: str,
        command: MissionUserCommandPayload,
    ) -> MissionAppendResultPayload:
        run = self._require_run(mission_id)
        for item in self.items[mission_id]:
            if item.item_type == "command_received" and item.operation_id == command.command_id:
                return MissionAppendResultPayload(
                    mission=self._copy_run(run),
                    items=[item.model_copy(deep=True)],
                )
        from src.dataservice_client.contracts.mission import MissionItemDraftPayload

        payload = dict(command.payload_json)
        payload["command_type"] = command.command_type
        item = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="command_received",
                    operation_id=command.command_id,
                    phase="completed",
                    producer=command.producer,
                    summary=command.summary,
                    payload_json=payload,
                )
            ],
        )[0]
        run.last_command_seq = item.seq
        run.next_wakeup_at = self.clock.now()
        self._touch(run)
        return MissionAppendResultPayload(
            mission=self._copy_run(run),
            items=[item.model_copy(deep=True)],
        )

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

    async def create_review_items(
        self,
        mission_id: str,
        command: MissionReviewItemsCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        run = self._require_run(mission_id)
        existing = self.review_items[mission_id]
        if all(
            item.review_item_id in existing
            for item in command.review_items
        ):
            return MissionReviewItemsResultPayload(
                mission=self._copy_run(run),
                items=[
                    existing[item.review_item_id].model_copy(deep=True)
                    for item in command.review_items
                ],
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

        for draft in command.review_items:
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
                target_ref=draft.target_ref,
                risk_level=draft.risk_level.value,
            )
            payload = MissionReviewItemPayload(
                review_item_id=draft.review_item_id,
                mission_id=mission_id,
                source_item_seq=draft.source_item_seq,
                output_key=draft.output_key,
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
        self._append_drafts(run, command.items)
        self._apply_patch(run, command)
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
        self.provider_calls = 0

    def _usage_receipt(self, *, model_id: str) -> ModelUsageReceipt:
        return ModelUsageReceipt(
            model_id=model_id,
            provider_response_id=f"scripted-response-{self.provider_calls}",
            usage=ModelUsage(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            ),
        )

    async def decide(self, context: MissionLoopContext) -> MissionAgentDecision:
        self.contexts.append(context.model_copy(deep=True))
        if not self.decisions:
            raise RuntimeError("scripted agent exhausted")
        self.provider_calls += 1
        decision = self.decisions.pop(0)
        try:
            if callable(decision):
                decision = decision(context)
                if inspect.isawaitable(decision):
                    decision = await decision
        except MissionAgentResponseError as exc:
            if exc.usage_receipt is not None:
                raise
            raise type(exc)(
                str(exc),
                usage_receipt=self._usage_receipt(
                    model_id=context.mission.model_id
                ),
            ) from exc
        if decision.usage_receipt is None:
            decision = decision.model_copy(
                update={
                    "usage_receipt": self._usage_receipt(
                        model_id=context.mission.model_id
                    )
                }
            )
        return decision


class FakeStartContext:
    async def pin(self, request: MissionStartRequest) -> MissionStartRequest:
        runtime_context = dict(request.runtime_context_json)
        policy = dict(runtime_context.get("mission_policy_snapshot") or {})
        policy.setdefault(
            "execution_budget",
            {
                "max_model_calls": 1_000,
                "max_tool_operations": 1_000,
                "max_subagent_jobs": 100,
                "stop_after_total_tokens": 10_000_000,
            },
        )
        runtime_context["mission_policy_snapshot"] = policy
        return request.model_copy(
            update={"runtime_context_json": runtime_context}
        )


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

    async def adopt_terminal(self, request: Any) -> MissionPortOutcome | None:
        del request
        return None


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
                    output_key="research_draft",
                    target_kind="document",
                    target_room="documents",
                    title="Research draft",
                    risk_level="medium",
                    preview_json={
                        "text": "draft",
                        "candidate_ref": request.accepted_candidate_refs[0],
                    },
                )
            ],
        )


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
        "mission_policy_id": "sci_research",
        "model_id": "gpt-5.6-sol",
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
            events=deps["events"],
            wakeups=deps["wakeups"],
            limits=limits,
            clock=deps["clock"],
        )
        return runtime, deps

    return build

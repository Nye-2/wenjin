"""Mission lifecycle, leases, commands, pauses, and terminal settlement."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.contracts.mission_budget import (
    MissionResourceUsage,
    execution_budget_from_runtime_context,
    resource_usage_from_snapshot,
    snapshot_with_resource_usage,
)
from src.contracts.mission_input import merge_mission_input_manifests
from src.contracts.prism_context import PrismContextRef
from src.dataservice.common.errors import (
    DataServiceConflictError,
    DataServiceNotFoundError,
    DataServiceValidationError,
)
from src.dataservice.domains.mission._store_core import (
    TERMINAL_MISSION_STATUSES,
    _aware,
    _create_request_matches,
    _text,
)
from src.dataservice.domains.mission.projection import (
    mission_item_to_payload,
    mission_run_to_payload,
)
from src.dataservice_client.contracts.mission import (
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionDispatchReleasePayload,
    MissionItemDraftPayload,
    MissionItemPayload,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionPausePayload,
    MissionResumePayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPayload,
    MissionStatus,
    MissionUserCommandPayload,
    validate_mission_snapshot,
)


class MissionLifecycleOperations:
    """Mission lifecycle, leases, commands, pauses, and terminal settlement."""

    async def create_run(self, command: MissionCreatePayload) -> MissionCreateResultPayload:
        if command.mission_idempotency_key is not None:
            existing = await self.repository.find_by_idempotency_key(
                workspace_id=command.workspace_id,
                mission_idempotency_key=command.mission_idempotency_key,
            )
            if existing is not None:
                if not _create_request_matches(existing, command):
                    raise DataServiceConflictError(
                        "Mission idempotency key was reused for a different request",
                        detail={"mission_id": existing.mission_id},
                    )
                return MissionCreateResultPayload(mission=mission_run_to_payload(existing), created=False)
        if command.thread_id is not None:
            foreground = await self.repository.find_foreground_for_thread(command.thread_id)
            if foreground is not None:
                raise DataServiceConflictError(
                    "Thread already has a foreground MissionRun",
                    detail={
                        "thread_id": command.thread_id,
                        "mission_id": foreground.mission_id,
                    },
                )
        if command.parent_mission_id is not None:
            parent = await self.repository.get_run(command.parent_mission_id)
            if parent is None or parent.workspace_id != command.workspace_id:
                raise DataServiceValidationError("parent_mission_id must reference a mission in the same workspace")
        try:
            execution_budget_from_runtime_context(command.runtime_context_json)
            initial_usage = resource_usage_from_snapshot(command.snapshot_json)
        except ValueError as exc:
            raise DataServiceValidationError(
                "Mission resource accounting contract is invalid",
                detail={"reason": str(exc)},
            ) from exc
        if initial_usage != MissionResourceUsage():
            raise DataServiceValidationError(
                "Mission resource usage must start at zero"
            )
        now = await self.repository.database_now()
        values = command.model_dump(mode="json")
        values["snapshot_json"] = validate_mission_snapshot(
            snapshot_with_resource_usage(command.snapshot_json, initial_usage)
        )
        values.update(
            {
                "status": MissionStatus.CREATED.value,
                "pending_review_count": 0,
                "evidence_count": 0,
                "artifact_count": 0,
                "active_subagent_count": 0,
                "last_command_seq": 0,
                "last_applied_command_seq": 0,
                "next_wakeup_at": now,
                "lease_epoch": 0,
                "state_version": 0,
                "last_item_seq": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
        record = self.repository.create_run(values)
        try:
            await self._finish()
        except IntegrityError as exc:
            await self.session.rollback()
            if command.mission_idempotency_key is not None:
                existing = await self.repository.find_by_idempotency_key(
                    workspace_id=command.workspace_id,
                    mission_idempotency_key=command.mission_idempotency_key,
                )
                if existing is not None and _create_request_matches(existing, command):
                    return MissionCreateResultPayload(mission=mission_run_to_payload(existing), created=False)
            raise DataServiceConflictError(
                "Mission creation conflicts with an existing foreground or idempotent mission",
                detail={"workspace_id": command.workspace_id, "thread_id": command.thread_id},
            ) from exc
        return MissionCreateResultPayload(mission=mission_run_to_payload(record), created=True)

    async def apply_initial_admission(
        self,
        mission_id: str,
        *,
        status: MissionStatus,
        snapshot_json: dict[str, Any],
        item: MissionItemDraftPayload,
    ) -> MissionRunPayload:
        if status not in {MissionStatus.PLANNING, MissionStatus.WAITING}:
            raise DataServiceValidationError(
                "Mission admission must resolve to planning or waiting"
            )
        run = await self._locked_run(mission_id)
        if run.status != MissionStatus.CREATED.value:
            raise DataServiceConflictError(
                "Mission admission can only resolve a newly created MissionRun",
                detail={"mission_id": mission_id, "status": run.status},
            )
        now = await self.repository.database_now()
        prepared_snapshot = self._prepare_snapshot_replacement(run, snapshot_json)
        self._transition_status(run, status, now=now)
        run.next_wakeup_at = now if status is MissionStatus.PLANNING else None
        self._append_drafts(run, [item], now=now)
        self._install_prepared_snapshot(run, prepared_snapshot)
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def claim_run_lease(
        self,
        mission_id: str,
        command: MissionLeaseClaimPayload,
    ) -> MissionRunPayload:
        run = await self._locked_run(mission_id)
        self._require_nonterminal(run)
        self._require_state_version(run, command.expected_state_version)
        now = await self.repository.database_now()
        expires_at = _aware(run.lease_expires_at)
        wakeup_at = _aware(run.next_wakeup_at)
        wakeup_due = wakeup_at is not None and wakeup_at <= now
        lease_expired = run.lease_owner is not None and expires_at is not None and expires_at <= now
        if not wakeup_due and not lease_expired:
            raise DataServiceConflictError(
                "MissionRun is not runnable",
                detail={
                    "mission_id": mission_id,
                    "status": run.status,
                    "next_wakeup_at": wakeup_at.isoformat() if wakeup_at else None,
                },
            )
        if run.lease_owner is not None and expires_at is not None and expires_at > now:
            raise DataServiceConflictError(
                "MissionRun already has an active driver",
                detail={"mission_id": mission_id, "lease_owner": run.lease_owner},
            )
        run.lease_owner = command.worker_id
        run.lease_epoch += 1
        run.lease_expires_at = now + timedelta(seconds=command.ttl_seconds)
        run.next_wakeup_at = None
        run.dispatch_owner = None
        run.dispatch_expires_at = None
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def heartbeat_run_lease(
        self,
        mission_id: str,
        command: MissionLeaseHeartbeatPayload,
    ) -> MissionRunPayload:
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.worker_id,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        run.lease_expires_at = now + timedelta(seconds=command.ttl_seconds)
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def release_run_lease(
        self,
        mission_id: str,
        command: MissionLeaseReleasePayload,
    ) -> MissionRunPayload:
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.worker_id,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        model_call_issues = self._model_call_issue_ids(
            await self._model_call_states(run)
        )
        if model_call_issues:
            raise DataServiceConflictError(
                "Mission lease cannot be released with model calls requiring closure",
                detail={
                    "mission_id": mission_id,
                    "model_call_ids": list(model_call_issues),
                },
            )
        run.lease_owner = None
        run.lease_expires_at = None
        run.next_wakeup_at = command.next_wakeup_at
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def claim_runnable_batch_skip_locked(
        self,
        command: MissionRunnableBatchClaimPayload,
    ) -> list[MissionRunPayload]:
        now = await self.repository.database_now()
        runs = await self.repository.claim_runnable_rows(now=now, limit=command.limit)
        for run in runs:
            run.dispatch_owner = command.worker_id
            run.dispatch_epoch += 1
            run.dispatch_expires_at = now + timedelta(seconds=command.ttl_seconds)
            self._touch(run, now)
        await self._finish()
        return [mission_run_to_payload(run) for run in runs]

    async def release_dispatch_claim(
        self,
        mission_id: str,
        command: MissionDispatchReleasePayload,
    ) -> MissionRunPayload:
        run = await self._locked_run(mission_id)
        if run.dispatch_owner != command.worker_id or run.dispatch_epoch != command.dispatch_epoch:
            raise DataServiceConflictError("Mission dispatch lease fence was lost")
        now = await self.repository.database_now()
        run.dispatch_owner = None
        run.dispatch_expires_at = None
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def append_command_once(
        self,
        mission_id: str,
        command: MissionUserCommandPayload,
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
        raw_prism_ref = command.payload_json.get("prism_context_ref")
        if raw_prism_ref is not None:
            prism_ref = PrismContextRef.model_validate(raw_prism_ref)
            if prism_ref.workspace_id != run.workspace_id:
                raise DataServiceValidationError(
                    "Prism context does not belong to the Mission workspace",
                    detail={"mission_id": mission_id},
                )
        existing = await self.repository.find_item_by_operation(
            mission_id=mission_id,
            operation_id=command.command_id,
            item_type="command_received",
        )
        if existing is not None:
            expected_payload = dict(command.payload_json)
            expected_payload["command_type"] = command.command_type
            if dict(existing.payload_json or {}) != expected_payload or existing.summary != command.summary or existing.producer != command.producer:
                raise DataServiceConflictError(
                    "command_id was reused with different command content",
                    detail={"mission_id": mission_id, "command_id": command.command_id},
                )
            return MissionAppendResultPayload(
                mission=mission_run_to_payload(run),
                items=[mission_item_to_payload(existing)],
            )
        terminal_mode_change = (
            run.status in TERMINAL_MISSION_STATUSES
            and command.command_type == "set_review_mode"
        )
        if run.status in TERMINAL_MISSION_STATUSES and not terminal_mode_change:
            self._require_nonterminal(run)
        if terminal_mode_change and run.last_applied_command_seq != run.last_command_seq:
            raise DataServiceConflictError(
                "Terminal MissionRun has unapplied commands",
                detail={"mission_id": mission_id},
            )
        now = await self.repository.database_now()
        payload_json = dict(command.payload_json)
        payload_json["command_type"] = command.command_type
        drafts = [
            MissionItemDraftPayload(
                item_type="command_received",
                operation_id=command.command_id,
                phase="completed",
                producer=command.producer,
                summary=command.summary,
                payload_json=payload_json,
            )
        ]
        records = self._append_drafts(run, drafts, now=now)
        run.last_command_seq = records[0].seq
        if terminal_mode_change:
            run.review_mode = str(command.payload_json["review_mode"])
            run.last_applied_command_seq = records[0].seq
        else:
            run.next_wakeup_at = now
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(records[0])],
        )

    async def list_unapplied_commands(
        self,
        mission_id: str,
        *,
        limit: int = 100,
    ) -> list[MissionItemPayload]:
        run = await self.repository.get_run(mission_id)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found")
        records = await self.repository.list_items(
            mission_id=mission_id,
            after_seq=run.last_applied_command_seq,
            through_seq=run.last_command_seq,
            item_type="command_received",
            limit=limit,
        )
        return [mission_item_to_payload(record) for record in records]

    async def apply_commands_and_advance_cursor(
        self,
        mission_id: str,
        command: MissionApplyCommandsPayload,
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.lease_owner,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        if command.through_command_seq <= run.last_applied_command_seq:
            return MissionAppendResultPayload(mission=mission_run_to_payload(run), items=[])
        if command.through_command_seq > run.last_command_seq:
            raise DataServiceConflictError("Cannot advance beyond last_command_seq")
        cursor_item = await self.repository.get_item(mission_id=mission_id, seq=command.through_command_seq)
        if cursor_item is None or cursor_item.item_type != "command_received":
            raise DataServiceValidationError("through_command_seq must identify a durable command_received item")
        prepared_snapshot = (
            self._prepare_snapshot_replacement(run, command.snapshot_json)
            if command.snapshot_json is not None
            else None
        )
        records = self._append_drafts(run, command.items, now=now)
        run.last_applied_command_seq = command.through_command_seq
        if prepared_snapshot is not None:
            self._install_prepared_snapshot(run, prepared_snapshot)
        self._apply_patch(run, command.patch, now=now)
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(record) for record in records],
        )

    async def pause_run(
        self,
        mission_id: str,
        command: MissionPausePayload,
        *,
        snapshot_patch: dict[str, Any] | None = None,
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
        pending_request = dict(command.pending_request)
        supplied_request_id = _text(pending_request.get("request_id"))
        if supplied_request_id and supplied_request_id != command.request_id:
            raise DataServiceValidationError(
                "pending_request.request_id must match request_id"
            )
        pending_request["request_id"] = command.request_id
        existing = await self.repository.find_item_by_operation(
            mission_id=mission_id,
            operation_id=command.request_id,
            item_type="pause_request",
        )
        if existing is not None:
            if existing.summary != command.reason or existing.producer != command.producer or dict(existing.payload_json or {}).get("pending_request") != pending_request:
                raise DataServiceConflictError("pause request_id was reused with different content")
            return MissionAppendResultPayload(mission=mission_run_to_payload(run), items=[mission_item_to_payload(existing)])
        self._require_nonterminal(run)
        if run.status not in {"planning", "running", "waiting"}:
            raise DataServiceConflictError("MissionRun is not pausable")
        now = await self.repository.database_now()
        snapshot = dict(run.snapshot_json or {})
        snapshot.update(snapshot_patch or {})
        snapshot["waiting_reason"] = command.reason
        snapshot["pending_request"] = pending_request
        prepared_snapshot = self._prepare_snapshot_replacement(run, snapshot)
        records = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="pause_request",
                    operation_id=command.request_id,
                    phase="completed",
                    producer=command.producer,
                    summary=command.reason,
                    payload_json={"pending_request": pending_request},
                )
            ],
            now=now,
        )
        self._install_prepared_snapshot(run, prepared_snapshot)
        if run.status != "waiting":
            self._transition_status(run, MissionStatus.WAITING, now=now)
        run.next_wakeup_at = None
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(records[0])],
        )

    async def settle_terminal_mission(self, mission_id: str) -> MissionRunPayload:
        run = await self._locked_run(mission_id)
        if run.status not in TERMINAL_MISSION_STATUSES:
            raise DataServiceConflictError(
                "Only a terminal MissionRun can be settled",
                detail={"mission_id": mission_id, "status": run.status},
            )
        self._terminalized_mission_ids.add(mission_id)
        await self._finish()
        return mission_run_to_payload(run)

    async def resume_run(
        self,
        mission_id: str,
        command: MissionResumePayload,
        *,
        snapshot_patch: dict[str, Any] | None = None,
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
        existing = await self.repository.find_item_by_operation(
            mission_id=mission_id,
            operation_id=command.request_id,
            item_type="resume_input",
        )
        if existing is not None:
            if existing.producer != command.producer or dict(existing.payload_json or {}) != command.input_json:
                raise DataServiceConflictError("resume request_id was reused with different content")
            return MissionAppendResultPayload(mission=mission_run_to_payload(run), items=[mission_item_to_payload(existing)])
        if run.status != "waiting":
            raise DataServiceConflictError(
                "Only a waiting MissionRun can resume",
                detail={"mission_id": mission_id, "status": run.status},
            )
        pending_request = dict((run.snapshot_json or {}).get("pending_request") or {})
        if pending_request.get("request_id") != command.request_id:
            raise DataServiceConflictError(
                "Resume request does not match the pending Mission request",
                detail={
                    "mission_id": mission_id,
                    "expected_request_id": pending_request.get("request_id"),
                    "actual_request_id": command.request_id,
                },
            )
        now = await self.repository.database_now()
        snapshot = dict(run.snapshot_json or {})
        snapshot.update(snapshot_patch or {})
        snapshot.pop("waiting_reason", None)
        snapshot.pop("pending_request", None)
        incoming_inputs = command.input_json.get("mission_inputs")
        if isinstance(incoming_inputs, list) and incoming_inputs:
            snapshot["mission_inputs"] = merge_mission_input_manifests(
                snapshot.get("mission_inputs"),
                incoming_inputs,
                workspace_id=run.workspace_id,
                thread_id=run.thread_id,
            )
        prepared_snapshot = self._prepare_snapshot_replacement(run, snapshot)
        records = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="resume_input",
                    operation_id=command.request_id,
                    phase="completed",
                    producer=command.producer,
                    payload_json=dict(command.input_json),
                )
            ],
            now=now,
        )
        self._install_prepared_snapshot(run, prepared_snapshot)
        self._transition_status(run, MissionStatus.PLANNING, now=now)
        run.next_wakeup_at = now
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(records[0])],
        )

__all__ = ['MissionLifecycleOperations']

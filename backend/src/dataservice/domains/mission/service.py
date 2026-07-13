"""Transactional MissionStore for lifecycle, ledger, review, and commit facts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    stage_id_matches_contract,
    stage_instance_index,
)
from src.database.models.mission import (
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.dataservice.common.errors import (
    DataServiceConflictError,
    DataServiceNotFoundError,
    DataServiceValidationError,
)
from src.dataservice.domains.mission.projection import (
    mission_commit_to_payload,
    mission_item_to_payload,
    mission_review_item_to_payload,
    mission_run_to_payload,
)
from src.dataservice.domains.mission.repository import MissionRepository
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionArtifactSummaryPayload,
    MissionAttentionActionPayload,
    MissionAttentionInputPayload,
    MissionAttentionRequestPayload,
    MissionCancelPayload,
    MissionCheckpointPayload,
    MissionCommitCreatePayload,
    MissionCommitCreateResultPayload,
    MissionCommitFinishPayload,
    MissionCommitResultPayload,
    MissionCommitStartPayload,
    MissionCommitStatus,
    MissionCommitSummaryPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionDispatchReleasePayload,
    MissionEvidenceSummaryPayload,
    MissionItemDraftPayload,
    MissionItemPayload,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionOperationClaimPayload,
    MissionOperationClaimResultPayload,
    MissionOperationFinishPayload,
    MissionOperationFinishResultPayload,
    MissionOperationReceiptPayload,
    MissionPausePayload,
    MissionPreviewCleanupPayload,
    MissionPreviewCleanupResultPayload,
    MissionProjectionPagePayload,
    MissionResumePayload,
    MissionReviewDecisionsPayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewItemsResultPayload,
    MissionReviewPolicyPayload,
    MissionReviewSummaryPayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPagePayload,
    MissionRunPatchPayload,
    MissionRunPayload,
    MissionStageSummaryPayload,
    MissionStatus,
    MissionSubagentSummaryPayload,
    MissionUserCommandPayload,
    MissionViewPayload,
    validate_mission_snapshot,
)
from src.review_commit_runtime.policy import project_review_policy

TERMINAL_MISSION_STATUSES = frozenset({"completed", "failed", "cancelled"})
_HISTORY_CURSOR_VERSION = 1


def _encode_history_cursor(*, updated_at: datetime, mission_id: str) -> str:
    normalized_updated_at = (
        updated_at if updated_at.tzinfo is not None else updated_at.replace(tzinfo=UTC)
    )
    payload = json.dumps(
        {
            "mission_id": mission_id,
            "updated_at": normalized_updated_at.isoformat(),
            "version": _HISTORY_CURSOR_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_history_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {
            "mission_id",
            "updated_at",
            "version",
        }:
            raise ValueError("invalid cursor shape")
        if payload["version"] != _HISTORY_CURSOR_VERSION:
            raise ValueError("unsupported cursor version")
        mission_id = payload["mission_id"]
        if not isinstance(mission_id, str) or not mission_id:
            raise ValueError("invalid mission id")
        updated_at = datetime.fromisoformat(payload["updated_at"])
        if updated_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
    except (binascii.Error, json.JSONDecodeError, TypeError, UnicodeError, ValueError) as exc:
        raise DataServiceValidationError("Invalid Mission history cursor") from exc
    return updated_at, mission_id


def _create_request_matches(run: MissionRunRecord, command: MissionCreatePayload) -> bool:
    """Bind an idempotency key to the complete immutable Mission contract."""

    return (
        run.parent_mission_id == command.parent_mission_id
        and run.workspace_id == command.workspace_id
        and run.thread_id == command.thread_id
        and run.user_id == command.user_id
        and run.workspace_type == command.workspace_type
        and run.mission_policy_id == command.mission_policy_id
        and run.title == command.title
        and run.objective == command.objective
        and run.review_mode == command.review_mode.value
        and run.model_id == command.model_id
        and run.reasoning_effort == command.reasoning_effort.value
        and dict(run.snapshot_json or {}) == command.snapshot_json
        and dict(run.runtime_context_json or {}) == command.runtime_context_json
        and run.mission_idempotency_key == command.mission_idempotency_key
    )
_ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"planning", "failed", "cancelled"}),
    "planning": frozenset({"running", "waiting", "failed", "cancelled"}),
    "running": frozenset({"planning", "waiting", "completed", "failed", "cancelled"}),
    "waiting": frozenset({"planning", "running", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
_REVIEW_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"accepted", "rejected", "needs_more_evidence", "superseded"}),
    "accepted": frozenset({"committed", "superseded"}),
    "rejected": frozenset({"superseded"}),
    "needs_more_evidence": frozenset({"superseded"}),
    "committed": frozenset(),
    "superseded": frozenset(),
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _operation_receipt_from_items(
    mission_id: str,
    operation_key: str,
    items: list[MissionItemRecord],
) -> MissionOperationReceiptPayload | None:
    claims = [item for item in items if item.item_type == "operation_claim"]
    if not claims:
        return None
    claim = claims[-1]
    claim_payload = dict(claim.payload_json or {})
    terminals = [
        item
        for item in items
        if item.item_type == "operation_terminal" and item.seq > claim.seq
    ]
    terminal = terminals[-1] if terminals else None
    terminal_payload = dict(terminal.payload_json or {}) if terminal is not None else {}
    status = str(terminal_payload.get("status") or "claimed")
    lease_expires_at: datetime | None = None
    if terminal is None:
        raw_expiry = claim_payload.get("lease_expires_at")
        if isinstance(raw_expiry, str):
            lease_expires_at = datetime.fromisoformat(raw_expiry)
    return MissionOperationReceiptPayload(
        receipt_id=str(claim.id),
        mission_id=mission_id,
        operation_key=operation_key,
        kind=claim_payload["kind"],
        request_hash=claim_payload["request_hash"],
        status=status,
        claimant=str(terminal_payload.get("claimant") or claim_payload["claimant"]),
        lease_epoch=int(terminal_payload.get("lease_epoch") or claim_payload["lease_epoch"]),
        lease_expires_at=lease_expires_at,
        receipt_json=dict(terminal_payload.get("receipt") or {}),
        payload_ref=terminal.payload_ref if terminal is not None else None,
        attempt=int(claim_payload.get("attempt") or len(claims)),
        claimed_at=claim.created_at,
        updated_at=terminal.created_at if terminal is not None else claim.created_at,
        completed_at=terminal.created_at if terminal is not None else None,
    )


class MissionStore:
    """Single transaction boundary for every durable Mission Runtime mutation."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = False) -> None:
        self.session = session
        self.repository = MissionRepository(session)
        self.autocommit = autocommit

    async def _finish(self) -> None:
        await self.session.flush()
        if self.autocommit:
            await self.session.commit()

    @staticmethod
    def _version_conflict(run: MissionRunRecord, expected: int) -> DataServiceConflictError:
        return DataServiceConflictError(
            "Mission state version is stale",
            detail={
                "mission_id": run.mission_id,
                "expected_state_version": expected,
                "actual_state_version": run.state_version,
            },
        )

    @staticmethod
    def _require_state_version(run: MissionRunRecord, expected: int) -> None:
        if run.state_version != expected:
            raise MissionStore._version_conflict(run, expected)

    @staticmethod
    def _require_nonterminal(run: MissionRunRecord) -> None:
        if run.status in TERMINAL_MISSION_STATUSES:
            raise DataServiceConflictError(
                "Terminal MissionRun cannot re-enter the agent loop",
                detail={"mission_id": run.mission_id, "status": run.status},
            )

    @staticmethod
    def _require_driver_fence(
        run: MissionRunRecord,
        *,
        expected_state_version: int,
        lease_owner: str,
        lease_epoch: int,
        now: datetime,
    ) -> None:
        MissionStore._require_nonterminal(run)
        MissionStore._require_state_version(run, expected_state_version)
        expires_at = _aware(run.lease_expires_at)
        if run.lease_owner != lease_owner or run.lease_epoch != lease_epoch or expires_at is None or expires_at <= now:
            raise DataServiceConflictError(
                "Mission driver lease fence rejected the write",
                detail={
                    "mission_id": run.mission_id,
                    "expected_lease_owner": lease_owner,
                    "actual_lease_owner": run.lease_owner,
                    "expected_lease_epoch": lease_epoch,
                    "actual_lease_epoch": run.lease_epoch,
                },
            )

    @staticmethod
    def _require_effect_epoch(
        run: MissionRunRecord,
        *,
        lease_epoch: int,
        now: datetime,
    ) -> None:
        expires_at = _aware(run.lease_expires_at)
        if (
            run.status in TERMINAL_MISSION_STATUSES
            or run.lease_owner is None
            or run.lease_epoch != lease_epoch
            or expires_at is None
            or expires_at <= now
        ):
            raise DataServiceConflictError(
                "Mission effect lease epoch is stale",
                detail={
                    "mission_id": run.mission_id,
                    "expected_lease_epoch": lease_epoch,
                    "actual_lease_epoch": run.lease_epoch,
                },
            )

    async def _locked_run(self, mission_id: str) -> MissionRunRecord:
        run = await self.repository.get_run(mission_id, for_update=True)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found", detail={"mission_id": mission_id})
        return run

    @staticmethod
    def _touch(run: MissionRunRecord, now: datetime) -> None:
        run.state_version += 1
        run.updated_at = now

    @staticmethod
    def _transition_status(
        run: MissionRunRecord,
        status: MissionStatus,
        *,
        now: datetime,
    ) -> None:
        target = status.value
        if target == run.status:
            return
        if target not in _ALLOWED_STATUS_TRANSITIONS[run.status]:
            raise DataServiceConflictError(
                "Invalid MissionRun status transition",
                detail={"mission_id": run.mission_id, "from": run.status, "to": target},
            )
        run.status = target
        if target in {"planning", "running"} and run.started_at is None:
            run.started_at = now
        if target == "waiting" or target in TERMINAL_MISSION_STATUSES:
            run.lease_owner = None
            run.lease_expires_at = None
        if target in TERMINAL_MISSION_STATUSES:
            run.next_wakeup_at = None
            run.dispatch_owner = None
            run.dispatch_expires_at = None
            run.completed_at = now

    @classmethod
    def _resolve_review_wait(
        cls,
        run: MissionRunRecord,
        *,
        review_item_id: str,
        next_action: str,
        now: datetime,
    ) -> bool:
        if run.status != MissionStatus.WAITING.value:
            return False
        snapshot = dict(run.snapshot_json or {})
        pending_request = snapshot.get("pending_request")
        if not isinstance(pending_request, dict):
            return False
        if str(pending_request.get("review_item_id") or "") != review_item_id:
            return False
        snapshot.pop("waiting_reason", None)
        snapshot.pop("pending_request", None)
        snapshot["next_actions"] = [next_action]
        run.snapshot_json = validate_mission_snapshot(snapshot)
        cls._transition_status(run, MissionStatus.PLANNING, now=now)
        return True

    @staticmethod
    def _apply_patch(
        run: MissionRunRecord,
        patch: MissionRunPatchPayload,
        *,
        now: datetime,
    ) -> None:
        fields = patch.model_fields_set
        if patch.status is not None:
            MissionStore._transition_status(run, patch.status, now=now)
        if "active_stage_id" in fields:
            run.active_stage_id = patch.active_stage_id
        if "context_checkpoint_ref" in fields:
            run.context_checkpoint_ref = patch.context_checkpoint_ref
        if "next_wakeup_at" in fields and run.status not in TERMINAL_MISSION_STATUSES:
            run.next_wakeup_at = patch.next_wakeup_at
        run.evidence_count += patch.evidence_count_delta
        run.artifact_count += patch.artifact_count_delta
        next_subagent_count = run.active_subagent_count + patch.active_subagent_count_delta
        if next_subagent_count < 0:
            raise DataServiceValidationError(
                "active_subagent_count cannot become negative",
                detail={"mission_id": run.mission_id},
            )
        run.active_subagent_count = next_subagent_count

    def _append_drafts(
        self,
        run: MissionRunRecord,
        drafts: list[MissionItemDraftPayload],
        *,
        now: datetime,
    ) -> list[MissionItemRecord]:
        records: list[MissionItemRecord] = []
        for draft in drafts:
            run.last_item_seq += 1
            values = draft.model_dump(mode="python")
            records.append(
                self.repository.append_item(
                    mission_id=run.mission_id,
                    seq=run.last_item_seq,
                    values=values,
                    created_at=now,
                )
            )
        return records

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
        now = await self.repository.database_now()
        values = command.model_dump(mode="json")
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

    async def load_run_snapshot(self, mission_id: str) -> MissionRunPayload | None:
        record = await self.repository.get_run(mission_id)
        return mission_run_to_payload(record) if record is not None else None

    async def foreground_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        record = await self.repository.find_foreground_for_thread(thread_id)
        if record is None:
            return None
        if record.workspace_id != workspace_id or record.user_id != user_id:
            return None
        return mission_run_to_payload(record)

    async def find_by_mission_idempotency_key(
        self,
        *,
        workspace_id: str,
        mission_idempotency_key: str,
    ) -> MissionRunPayload | None:
        record = await self.repository.find_by_idempotency_key(
            workspace_id=workspace_id,
            mission_idempotency_key=mission_idempotency_key,
        )
        return mission_run_to_payload(record) if record is not None else None

    async def list_runs_summary(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        status: list[MissionStatus] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> MissionRunPagePayload:
        before_updated_at, before_mission_id = (
            _decode_history_cursor(cursor) if cursor else (None, None)
        )
        records = await self.repository.list_runs(
            workspace_id=workspace_id,
            user_id=user_id,
            status=[item.value for item in status] if status else None,
            limit=limit + 1,
            before_updated_at=before_updated_at,
            before_mission_id=before_mission_id,
        )
        page_records = records[:limit]
        next_cursor = None
        if len(records) > limit and page_records:
            last = page_records[-1]
            next_cursor = _encode_history_cursor(
                updated_at=last.updated_at,
                mission_id=last.mission_id,
            )
        return MissionRunPagePayload(
            items=[mission_run_to_payload(record) for record in page_records],
            next_cursor=next_cursor,
        )

    async def list_runs_updated_after(
        self,
        *,
        workspace_id: str,
        updated_at: datetime,
        mission_id: str,
        limit: int = 100,
    ) -> list[MissionRunPayload]:
        records = await self.repository.list_runs_updated_after(
            workspace_id=workspace_id,
            updated_at=updated_at,
            mission_id=mission_id,
            limit=limit,
        )
        return [mission_run_to_payload(record) for record in records]

    async def aggregate_stats(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ):
        from src.dataservice_client.contracts.mission import (
            MissionStatsKpisPayload,
            MissionStatsPayload,
            MissionStatsTimePointPayload,
            MissionWorkspaceTypeCountPayload,
        )

        if granularity not in {"day", "week"}:
            raise ValueError("granularity must be day or week")
        rows = await self.repository.aggregate_stats(
            created_since=created_since,
            granularity=granularity,
        )
        by_date: dict[str, dict[str, dict[str, int]]] = {}
        by_workspace_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for bucket, status, workspace_type, count in rows:
            date_key = bucket.date().isoformat()
            point = by_date.setdefault(date_key, {"by_type": {}, "by_status": {}})
            point["by_type"][workspace_type] = point["by_type"].get(workspace_type, 0) + count
            point["by_status"][status] = point["by_status"].get(status, 0) + count
            by_workspace_type[workspace_type] = by_workspace_type.get(workspace_type, 0) + count
            by_status[status] = by_status.get(status, 0) + count
        total = sum(by_status.values())
        success = by_status.get("completed", 0)
        failed = by_status.get("failed", 0) + by_status.get("cancelled", 0)
        return MissionStatsPayload(
            kpis=MissionStatsKpisPayload(
                total=total,
                success=success,
                failed=failed,
                success_rate=(success / total) if total else 0.0,
            ),
            time_series=[MissionStatsTimePointPayload(date=date, **counts) for date, counts in sorted(by_date.items())],
            by_workspace_type=[MissionWorkspaceTypeCountPayload(type=workspace_type, count=count) for workspace_type, count in sorted(by_workspace_type.items())],
        )

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
        if (
            run.dispatch_owner != command.worker_id
            or run.dispatch_epoch != command.dispatch_epoch
        ):
            raise DataServiceConflictError("Mission dispatch lease fence was lost")
        now = await self.repository.database_now()
        run.dispatch_owner = None
        run.dispatch_expires_at = None
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def claim_operation(
        self,
        mission_id: str,
        command: MissionOperationClaimPayload,
    ) -> MissionOperationClaimResultPayload:
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_effect_epoch(run, lease_epoch=command.lease_epoch, now=now)
        items = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=command.operation_key,
        )
        receipt = _operation_receipt_from_items(mission_id, command.operation_key, items)
        if receipt is not None and (
            receipt.kind != command.kind or receipt.request_hash != command.request_hash
        ):
            raise DataServiceConflictError(
                "Operation key is already bound to a different request",
                detail={"mission_id": mission_id, "operation_key": command.operation_key},
            )
        if receipt is not None and receipt.status.value != "claimed":
            return MissionOperationClaimResultPayload(receipt=receipt, acquired=False)
        expires_at = _aware(receipt.lease_expires_at) if receipt is not None else None
        if receipt is not None and expires_at is not None and expires_at > now:
            return MissionOperationClaimResultPayload(receipt=receipt, acquired=False)
        attempt = (receipt.attempt + 1) if receipt is not None else 1
        expires_at = now + timedelta(seconds=command.ttl_seconds)
        claim = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="operation_claim",
                    operation_id=command.operation_key,
                    phase="started",
                    producer=command.claimant,
                    summary=f"{command.kind.value} operation claimed",
                    payload_json={
                        "kind": command.kind.value,
                        "request_hash": command.request_hash,
                        "status": "claimed",
                        "claimant": command.claimant,
                        "lease_epoch": command.lease_epoch,
                        "lease_expires_at": expires_at.isoformat(),
                        "attempt": attempt,
                    },
                )
            ],
            now=now,
        )[0]
        self._touch(run, now)
        await self._finish()
        return MissionOperationClaimResultPayload(
            receipt=_operation_receipt_from_items(
                mission_id,
                command.operation_key,
                [*items, claim],
            ),
            acquired=True,
        )

    async def get_operation(
        self,
        mission_id: str,
        operation_key: str,
    ) -> MissionOperationReceiptPayload | None:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        items = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=operation_key,
        )
        return _operation_receipt_from_items(mission_id, operation_key, items)

    async def finish_operation(
        self,
        mission_id: str,
        command: MissionOperationFinishPayload,
    ) -> MissionOperationFinishResultPayload:
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_effect_epoch(run, lease_epoch=command.lease_epoch, now=now)
        items = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=command.operation_key,
        )
        receipt = _operation_receipt_from_items(mission_id, command.operation_key, items)
        if receipt is None:
            raise DataServiceConflictError("Operation must be claimed before it can finish")
        if receipt.kind != command.kind or receipt.request_hash != command.request_hash:
            raise DataServiceConflictError("Operation finish does not match the claimed request")
        desired = command.model_dump(mode="json")["receipt_json"]
        if receipt.status.value != "claimed":
            same = (
                receipt.status == command.status
                and receipt.receipt_json == desired
                and receipt.payload_ref == command.payload_ref
            )
            if not same:
                raise DataServiceConflictError("Terminal operation receipt is immutable")
            return MissionOperationFinishResultPayload(
                receipt=receipt,
                finalized=False,
            )
        if receipt.claimant != command.claimant or receipt.lease_epoch != command.lease_epoch:
            raise DataServiceConflictError("Operation terminal fence was lost")
        terminal = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="operation_terminal",
                    operation_id=command.operation_key,
                    phase=("completed" if command.status.value == "succeeded" else "failed"),
                    producer=command.claimant,
                    summary=f"{command.kind.value} operation {command.status.value}",
                    payload_json={
                        "kind": command.kind.value,
                        "request_hash": command.request_hash,
                        "status": command.status.value,
                        "claimant": command.claimant,
                        "lease_epoch": command.lease_epoch,
                        "attempt": receipt.attempt,
                        "receipt": desired,
                    },
                    payload_ref=command.payload_ref,
                )
            ],
            now=now,
        )[0]
        self._touch(run, now)
        await self._finish()
        return MissionOperationFinishResultPayload(
            receipt=_operation_receipt_from_items(
                mission_id,
                command.operation_key,
                [*items, terminal],
            ),
            finalized=True,
        )

    async def append_items_and_update_snapshot(
        self,
        mission_id: str,
        command: MissionAppendPayload,
    ) -> MissionAppendResultPayload:
        if any(item.item_type == "command_received" for item in command.items):
            raise DataServiceValidationError("command_received must use append_command_once so the durable cursor advances")
        run = await self._locked_run(mission_id)
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.lease_owner,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        records = self._append_drafts(run, command.items, now=now)
        if command.snapshot_json is not None:
            run.snapshot_json = dict(command.snapshot_json)
        self._apply_patch(run, command.patch, now=now)
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(record) for record in records],
        )

    async def checkpoint_run(
        self,
        mission_id: str,
        command: MissionCheckpointPayload,
    ) -> MissionAppendResultPayload:
        """Persist one safe-boundary snapshot under the normal driver fence."""
        return await self.append_items_and_update_snapshot(mission_id, command)

    async def append_command_once(
        self,
        mission_id: str,
        command: MissionUserCommandPayload,
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
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
        self._require_nonterminal(run)
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
        if command.command_type == "set_review_mode":
            review_mode = command.payload_json.get("review_mode")
            if review_mode not in {"review_all", "balanced_default", "auto_draft"}:
                raise DataServiceValidationError(
                    "set_review_mode requires a valid review_mode"
                )
            run.review_mode = str(review_mode)
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
        records = self._append_drafts(run, command.items, now=now)
        run.last_applied_command_seq = command.through_command_seq
        if command.snapshot_json is not None:
            run.snapshot_json = dict(command.snapshot_json)
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
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
        existing = await self.repository.find_item_by_operation(
            mission_id=mission_id,
            operation_id=command.request_id,
            item_type="pause_request",
        )
        if existing is not None:
            if existing.summary != command.reason or existing.producer != command.producer or dict(existing.payload_json or {}).get("pending_request") != command.pending_request:
                raise DataServiceConflictError("pause request_id was reused with different content")
            return MissionAppendResultPayload(mission=mission_run_to_payload(run), items=[mission_item_to_payload(existing)])
        self._require_nonterminal(run)
        if run.status not in {"planning", "running", "waiting"}:
            raise DataServiceConflictError("MissionRun is not pausable")
        now = await self.repository.database_now()
        snapshot = dict(run.snapshot_json or {})
        snapshot["waiting_reason"] = command.reason
        snapshot["pending_request"] = dict(command.pending_request)
        run.snapshot_json = validate_mission_snapshot(snapshot)
        records = self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="pause_request",
                    operation_id=command.request_id,
                    phase="completed",
                    producer=command.producer,
                    summary=command.reason,
                    payload_json={"pending_request": command.pending_request},
                )
            ],
            now=now,
        )
        if run.status != "waiting":
            self._transition_status(run, MissionStatus.WAITING, now=now)
        run.next_wakeup_at = None
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(records[0])],
        )

    async def resume_run(
        self,
        mission_id: str,
        command: MissionResumePayload,
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
        snapshot.pop("waiting_reason", None)
        snapshot.pop("pending_request", None)
        run.snapshot_json = validate_mission_snapshot(snapshot)
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
        self._transition_status(run, MissionStatus.PLANNING, now=now)
        run.next_wakeup_at = now
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(records[0])],
        )

    async def cancel_run(
        self,
        mission_id: str,
        command: MissionCancelPayload,
    ) -> MissionAppendResultPayload:
        run = await self._locked_run(mission_id)
        existing = await self.repository.find_item_by_operation(
            mission_id=mission_id,
            operation_id=command.request_id,
            item_type="command_received",
        )
        if existing is not None:
            expected_payload = {"command_type": "cancel", "reason": command.reason}
            if existing.summary != command.reason or existing.producer != command.producer or dict(existing.payload_json or {}) != expected_payload:
                raise DataServiceConflictError("cancel request_id was reused with different content")
            return MissionAppendResultPayload(mission=mission_run_to_payload(run), items=[mission_item_to_payload(existing)])
        self._require_nonterminal(run)
        now = await self.repository.database_now()
        records = self._append_drafts(
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
            now=now,
        )
        run.last_command_seq = records[0].seq
        run.last_applied_command_seq = records[0].seq
        self._transition_status(run, MissionStatus.CANCELLED, now=now)
        self._touch(run, now)
        await self._finish()
        return MissionAppendResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_item_to_payload(records[0])],
        )

    async def create_review_items(
        self,
        mission_id: str,
        command: MissionReviewItemsCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        run = await self._locked_run(mission_id)
        requested_ids = [item.review_item_id for item in command.items]
        if len(requested_ids) != len(set(requested_ids)):
            raise DataServiceValidationError("review_item_id values must be unique")
        existing = await self.repository.list_review_items_by_ids(
            mission_id=mission_id,
            review_item_ids=requested_ids,
        )
        if existing:
            if len(existing) != len(requested_ids):
                raise DataServiceConflictError("Review-item retry mixed existing and new identifiers")
            existing_by_id = {item.review_item_id: item for item in existing}
            for draft in command.items:
                record = existing_by_id[draft.review_item_id]
                preview_json, preview_hash = _canonical_preview(draft)
                policy = project_review_policy(
                    review_mode=run.review_mode,
                    target_kind=draft.target_kind,
                    target_room=draft.target_room,
                    risk_level=draft.risk_level.value,
                )
                if (
                    record.source_item_seq != draft.source_item_seq
                    or record.target_kind != draft.target_kind
                    or record.target_room != draft.target_room
                    or record.target_ref != draft.target_ref
                    or record.base_revision_ref != draft.base_revision_ref
                    or record.base_hash != draft.base_hash
                    or record.title != draft.title
                    or record.summary != draft.summary
                    or record.risk_level != draft.risk_level.value
                    or record.review_required_reason != draft.review_required_reason
                    or dict(record.preview_json or {}) != preview_json
                    or record.preview_ref != draft.preview_ref
                    or record.preview_hash != preview_hash
                    or _aware(record.preview_expires_at) != _aware(draft.preview_expires_at)
                    or record.requires_explicit_review != policy.requires_explicit_review
                    or record.batch_acceptable != policy.batch_acceptable
                    or record.suggested_selected != policy.suggested_selected
                ):
                    raise DataServiceConflictError(
                        "review_item_id was reused with different candidate content",
                        detail={"review_item_id": draft.review_item_id},
                    )
            return MissionReviewItemsResultPayload(
                mission=mission_run_to_payload(run),
                items=[mission_review_item_to_payload(existing_by_id[item_id]) for item_id in requested_ids],
            )
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.lease_owner,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        records: list[MissionReviewItemRecord] = []
        audit_drafts: list[MissionItemDraftPayload] = []
        for draft in command.items:
            if draft.source_item_seq is not None:
                source_item = await self.repository.get_item(mission_id=mission_id, seq=draft.source_item_seq)
                if source_item is None:
                    raise DataServiceValidationError("source_item_seq must reference the same mission ledger")
            preview_json, preview_hash = _canonical_preview(draft)
            policy = project_review_policy(
                review_mode=run.review_mode,
                target_kind=draft.target_kind,
                target_room=draft.target_room,
                risk_level=draft.risk_level.value,
            )
            values = draft.model_dump(mode="python")
            values.update(
                {
                    "mission_id": mission_id,
                    "status": "pending",
                    "decision_json": None,
                    "decided_by": None,
                    "decided_at": None,
                    "created_at": now,
                    "updated_at": now,
                    "preview_json": preview_json,
                    "preview_hash": preview_hash,
                    "requires_explicit_review": policy.requires_explicit_review,
                    "batch_acceptable": policy.batch_acceptable,
                    "suggested_selected": policy.suggested_selected,
                }
            )
            records.append(self.repository.create_review_item(values))
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_candidate_created",
                    operation_id=draft.review_item_id,
                    phase="completed",
                    producer="mission_runtime",
                    summary=draft.title,
                    risk_level=draft.risk_level,
                    payload_json={
                        "review_item_id": draft.review_item_id,
                        "target_kind": draft.target_kind,
                        "target_room": draft.target_room,
                    },
                )
            )
        self._append_drafts(run, audit_drafts, now=now)
        run.pending_review_count += len(records)
        self._touch(run, now)
        await self._finish()
        return MissionReviewItemsResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_review_item_to_payload(item) for item in records],
        )

    async def list_review_items(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
    ) -> list[MissionReviewItemPayload]:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        records = await self.repository.list_review_items(mission_id=mission_id, status=status)
        return [mission_review_item_to_payload(record) for record in records]

    async def apply_review_decisions(
        self,
        mission_id: str,
        command: MissionReviewDecisionsPayload,
    ) -> MissionReviewItemsResultPayload:
        run = await self._locked_run(mission_id)
        prior_audits = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=command.decision_id,
            item_type="review_decision_audit",
        )
        requested_ids = [decision.review_item_id for decision in command.decisions]
        if prior_audits:
            if any(audit.producer != command.actor_user_id for audit in prior_audits):
                raise DataServiceConflictError(
                    "decision_id was reused by a different actor",
                    detail={"decision_id": command.decision_id},
                )
            recorded_ids: set[str] = set()
            recorded_targets: dict[str, str] = {}
            recorded_decisions: dict[str, dict[str, object]] = {}
            for audit in prior_audits:
                payload = dict(audit.payload_json or {})
                review_item_id = payload.get("review_item_id")
                if review_item_id is not None:
                    item_id = str(review_item_id)
                    recorded_ids.add(item_id)
                    if payload.get("status_to") is not None:
                        recorded_targets[item_id] = str(payload["status_to"])
                    recorded_decisions[item_id] = dict(payload.get("decision_json") or {})
                for replayed in payload.get("decisions") or []:
                    item_id = str(replayed["review_item_id"])
                    recorded_ids.add(item_id)
                    recorded_targets[item_id] = str(replayed["status"])
                    recorded_decisions[item_id] = dict(replayed.get("decision_json") or {})
            requested_targets = {decision.review_item_id: decision.status.value for decision in command.decisions}
            requested_decisions = {decision.review_item_id: dict(decision.decision_json) for decision in command.decisions}
            if recorded_ids != set(requested_ids) or recorded_targets != requested_targets or recorded_decisions != requested_decisions:
                raise DataServiceConflictError(
                    "decision_id was reused with different review content",
                    detail={"decision_id": command.decision_id},
                )
            records = await self.repository.list_review_items_by_ids(mission_id=mission_id, review_item_ids=requested_ids)
            by_id = {record.review_item_id: record for record in records}
            return MissionReviewItemsResultPayload(
                mission=mission_run_to_payload(run),
                items=[mission_review_item_to_payload(by_id[item_id]) for item_id in requested_ids],
            )
        self._require_state_version(run, command.expected_state_version)
        records = await self.repository.list_review_items_by_ids(
            mission_id=mission_id,
            review_item_ids=requested_ids,
            for_update=True,
        )
        if len(records) != len(requested_ids):
            raise DataServiceNotFoundError("One or more MissionReviewItems do not belong to the mission")
        by_id = {record.review_item_id: record for record in records}
        now = await self.repository.database_now()
        audit_drafts: list[MissionItemDraftPayload] = []
        for decision in command.decisions:
            record = by_id[decision.review_item_id]
            target = decision.status.value
            if target == record.status:
                continue
            if target not in _REVIEW_TRANSITIONS[record.status]:
                raise DataServiceConflictError(
                    "Invalid MissionReviewItem transition",
                    detail={
                        "review_item_id": record.review_item_id,
                        "from": record.status,
                        "to": target,
                    },
                )
            if record.status == "accepted":
                active_commit = await self.repository.find_commit_by_review_item(
                    record.review_item_id
                )
                if active_commit is not None and active_commit.status == "applying":
                    raise DataServiceConflictError(
                        "Review item has an applying commit",
                        detail={"review_item_id": record.review_item_id},
                    )
            if record.status == "pending":
                run.pending_review_count -= 1
            previous = record.status
            record.status = target
            record.decision_json = {
                **dict(decision.decision_json),
                "decision_id": command.decision_id,
            }
            record.decided_by = command.actor_user_id
            record.decided_at = now
            record.updated_at = now
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_decision_audit",
                    operation_id=command.decision_id,
                    phase="completed",
                    producer=command.actor_user_id,
                    summary=f"{previous} -> {target}",
                    risk_level=record.risk_level,
                    payload_json={
                        "review_item_id": record.review_item_id,
                        "status_from": previous,
                        "status_to": target,
                        "decision_json": decision.decision_json,
                    },
                )
            )
        if not audit_drafts:
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_decision_audit",
                    operation_id=command.decision_id,
                    phase="completed",
                    producer=command.actor_user_id,
                    summary="Review decision was already reflected",
                    payload_json={
                        "decisions": [
                            {
                                "review_item_id": decision.review_item_id,
                                "status": decision.status.value,
                                "decision_json": decision.decision_json,
                            }
                            for decision in command.decisions
                        ]
                    },
                )
            )
        self._append_drafts(run, audit_drafts, now=now)
        revision_ids = [
            decision.review_item_id
            for decision in command.decisions
            if decision.status.value != "accepted"
        ]
        for review_item_id in revision_ids:
            if self._resolve_review_wait(
                run,
                review_item_id=review_item_id,
                next_action="revise_current_stage",
                now=now,
            ):
                break
        if run.status not in TERMINAL_MISSION_STATUSES and revision_ids:
            run.next_wakeup_at = now
        self._touch(run, now)
        await self._finish()
        return MissionReviewItemsResultPayload(
            mission=mission_run_to_payload(run),
            items=[mission_review_item_to_payload(by_id[item_id]) for item_id in requested_ids],
        )

    async def record_commit(
        self,
        mission_id: str,
        command: MissionCommitCreatePayload,
    ) -> MissionCommitCreateResultPayload:
        run = await self._locked_run(mission_id)
        existing_by_key = await self.repository.find_commit_by_key(mission_id=mission_id, commit_key=command.commit_key)
        existing_by_item = await self.repository.find_commit_by_review_item(command.review_item_id)
        existing = existing_by_key or existing_by_item
        if existing is not None:
            if existing.mission_id != mission_id or existing.review_item_id != command.review_item_id or existing.commit_key != command.commit_key:
                raise DataServiceConflictError("Commit key or review item is already bound to another commit")
            return MissionCommitCreateResultPayload(
                mission=mission_run_to_payload(run),
                commit=mission_commit_to_payload(existing),
                created=False,
            )
        self._require_state_version(run, command.expected_state_version)
        review_item = await self.repository.get_review_item(command.review_item_id, for_update=True)
        if review_item is None or review_item.mission_id != mission_id:
            raise DataServiceNotFoundError("MissionReviewItem not found for mission")
        if review_item.status != "accepted":
            raise DataServiceConflictError(
                "Only an accepted MissionReviewItem can be committed",
                detail={
                    "review_item_id": command.review_item_id,
                    "status": review_item.status,
                },
            )
        now = await self.repository.database_now()
        commit = self.repository.create_commit(
            {
                "mission_id": mission_id,
                "review_item_id": command.review_item_id,
                "commit_key": command.commit_key,
                "status": "pending",
                "actor_user_id": command.actor_user_id,
                "targets_json": {},
                "error_json": None,
                "attempt_count": 0,
                "attempt_token": None,
                "attempt_started_at": None,
                "attempt_expires_at": None,
                "created_at": now,
                "completed_at": None,
            }
        )
        self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="commit_started",
                    operation_id=command.commit_key,
                    phase="started",
                    producer=command.actor_user_id,
                    payload_json={
                        "commit_id": commit.commit_id,
                        "review_item_id": command.review_item_id,
                    },
                )
            ],
            now=now,
        )
        self._touch(run, now)
        await self._finish()
        return MissionCommitCreateResultPayload(
            mission=mission_run_to_payload(run),
            commit=mission_commit_to_payload(commit),
            created=True,
        )

    async def start_commit(
        self,
        mission_id: str,
        commit_id: str,
        command: MissionCommitStartPayload,
    ) -> MissionCommitResultPayload:
        run = await self._locked_run(mission_id)
        commit = await self.repository.get_commit(commit_id, for_update=True)
        if commit is None or commit.mission_id != mission_id:
            raise DataServiceNotFoundError("MissionCommit not found for mission")
        now = await self.repository.database_now()
        if commit.status == "applying":
            if commit.attempt_token == command.attempt_token:
                return MissionCommitResultPayload(
                    mission=mission_run_to_payload(run),
                    commit=mission_commit_to_payload(commit),
                )
            if (
                commit.attempt_expires_at is not None
                and _aware(commit.attempt_expires_at) > _aware(now)
            ):
                raise DataServiceConflictError("MissionCommit is already applying")
        if commit.status in {"committed", "cancelled"}:
            raise DataServiceConflictError("Terminal MissionCommit cannot restart")
        if commit.status not in {"pending", "failed", "applying"}:
            raise DataServiceConflictError("MissionCommit is not startable")
        review_item = await self.repository.get_review_item(
            commit.review_item_id,
            for_update=True,
        )
        if review_item is None or review_item.mission_id != mission_id:
            raise DataServiceConflictError("MissionCommit lost its review item")
        if review_item.status != "accepted":
            raise DataServiceConflictError(
                "Only an accepted MissionReviewItem can start materialization",
                detail={
                    "review_item_id": review_item.review_item_id,
                    "status": review_item.status,
                },
            )
        commit.status = "applying"
        commit.attempt_count += 1
        commit.attempt_token = command.attempt_token
        commit.attempt_started_at = now
        commit.attempt_expires_at = now + timedelta(seconds=command.lease_seconds)
        commit.completed_at = None
        commit.error_json = None
        self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="commit_started",
                    operation_id=commit.commit_key,
                    phase="progress",
                    producer=commit.actor_user_id,
                    payload_json={
                        "commit_id": commit.commit_id,
                        "attempt_count": commit.attempt_count,
                        "attempt_token": command.attempt_token,
                    },
                )
            ],
            now=now,
        )
        self._touch(run, now)
        await self._finish()
        return MissionCommitResultPayload(mission=mission_run_to_payload(run), commit=mission_commit_to_payload(commit))

    async def finish_commit(
        self,
        mission_id: str,
        commit_id: str,
        command: MissionCommitFinishPayload,
    ) -> MissionCommitResultPayload:
        run = await self._locked_run(mission_id)
        commit = await self.repository.get_commit(commit_id, for_update=True)
        if commit is None or commit.mission_id != mission_id:
            raise DataServiceNotFoundError("MissionCommit not found for mission")
        target_status = command.status.value
        if commit.status == target_status:
            expected_error = (
                dict(command.error_json) if command.error_json is not None else None
            )
            if (
                commit.attempt_token != command.attempt_token
                or dict(commit.targets_json or {}) != dict(command.targets_json)
                or commit.error_json != expected_error
            ):
                raise DataServiceConflictError(
                    "MissionCommit terminal replay does not match the stored receipt"
                )
            return MissionCommitResultPayload(mission=mission_run_to_payload(run), commit=mission_commit_to_payload(commit))
        if commit.status != "applying":
            raise DataServiceConflictError("Only an applying MissionCommit can finish")
        if commit.attempt_token != command.attempt_token:
            raise DataServiceConflictError("MissionCommit attempt fence was lost")
        now = await self.repository.database_now()
        commit.status = target_status
        commit.targets_json = dict(command.targets_json)
        commit.error_json = dict(command.error_json) if command.error_json is not None else None
        commit.completed_at = now
        commit.attempt_expires_at = None
        if target_status == MissionCommitStatus.COMMITTED.value:
            review_item = await self.repository.get_review_item(commit.review_item_id, for_update=True)
            if review_item is None or review_item.mission_id != mission_id:
                raise DataServiceConflictError("MissionCommit lost its review item")
            if review_item.status != "accepted":
                raise DataServiceConflictError(
                    "Review item changed before commit completion",
                    detail={"review_item_id": review_item.review_item_id},
                )
            review_item.status = "committed"
            review_item.updated_at = now
            if run.status not in TERMINAL_MISSION_STATUSES:
                self._resolve_review_wait(
                    run,
                    review_item_id=review_item.review_item_id,
                    next_action="plan_or_replan",
                    now=now,
                )
                run.next_wakeup_at = now
        phase = {
            "committed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }[target_status]
        self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="commit_completed",
                    operation_id=commit.commit_key,
                    phase=phase,
                    producer=commit.actor_user_id,
                    payload_json={
                        "commit_id": commit.commit_id,
                        "status": target_status,
                        "targets": command.targets_json,
                    },
                )
            ],
            now=now,
        )
        self._touch(run, now)
        await self._finish()
        return MissionCommitResultPayload(mission=mission_run_to_payload(run), commit=mission_commit_to_payload(commit))

    async def list_items_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> list[MissionItemPayload]:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        if operation_id is not None:
            records = await self.repository.list_items_by_operation(
                mission_id=mission_id,
                operation_id=operation_id,
                item_type=item_type,
            )
            records = [record for record in records if record.seq > after_seq][:limit]
        else:
            records = await self.repository.list_items(
                mission_id=mission_id,
                after_seq=after_seq,
                limit=limit,
                item_type=item_type,
            )
        return [mission_item_to_payload(record) for record in records]

    async def get_view(
        self,
        mission_id: str,
        *,
        projection_item_limit: int = 50,
    ) -> MissionViewPayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        review_records = await self.repository.list_review_items(mission_id=mission_id)
        commit_records = await self.repository.list_commits(mission_id=mission_id)
        evidence_records = await self.repository.list_items_by_types(
            mission_id=mission_id,
            item_types=("evidence",),
            limit=projection_item_limit + 1,
        )
        artifact_records = await self.repository.list_items_by_types(
            mission_id=mission_id,
            item_types=("artifact", "output"),
            limit=projection_item_limit + 1,
        )
        pending_review_sources = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=tuple(
                record.source_item_seq
                for record in review_records
                if record.status == "pending" and record.source_item_seq is not None
            ),
        )
        review_counts = {status: 0 for status in _REVIEW_TRANSITIONS}
        for record in review_records:
            review_counts[record.status] += 1
        commit_counts = {status: 0 for status in ("pending", "applying", "committed", "failed", "cancelled")}
        for record in commit_records:
            commit_counts[record.status] += 1
        evidence_page_records = evidence_records[:projection_item_limit]
        artifact_page_records = artifact_records[:projection_item_limit]
        required_stage_ids, stage_summaries = _project_stages(
            run,
            observed_stage_ids=[
                record.stage_id
                for record in pending_review_sources
                if record.stage_id is not None
            ],
        )
        team_summary, subagents = _project_subagents(run)
        committed_review_ids = {
            record.review_item_id for record in commit_records if record.status == "committed"
        }
        return MissionViewPayload(
            mission=mission_run_to_payload(run),
            attention_request=_project_attention_request(run),
            review_summary=MissionReviewSummaryPayload(**review_counts),
            commit_summary=MissionCommitSummaryPayload(**commit_counts),
            review_items=[mission_review_item_to_payload(record) for record in review_records],
            commits=[mission_commit_to_payload(record) for record in commit_records],
            required_stage_ids=required_stage_ids,
            stage_summaries=stage_summaries,
            team_summary=team_summary,
            subagents=subagents,
            evidence_items=[_project_evidence(record) for record in evidence_page_records],
            evidence_page=MissionProjectionPagePayload(
                total=run.evidence_count,
                returned=len(evidence_page_records),
                next_cursor=(
                    evidence_page_records[-1].seq
                    if len(evidence_records) > projection_item_limit
                    else None
                ),
            ),
            artifact_items=[
                _project_artifact(record, committed_review_ids)
                for record in artifact_page_records
            ],
            artifact_page=MissionProjectionPagePayload(
                total=run.artifact_count,
                returned=len(artifact_page_records),
                next_cursor=(
                    artifact_page_records[-1].seq
                    if len(artifact_records) > projection_item_limit
                    else None
                ),
            ),
            review_policy=MissionReviewPolicyPayload(
                mode=run.review_mode,
                protected_outputs_require_confirmation=True,
                draft_outputs_may_be_automatic=run.review_mode != "review_all",
            ),
            quality_highlights=_project_quality_highlights(run),
            refresh_token=f"{run.updated_at.isoformat()}:{run.mission_id}:{run.state_version}",
        )

    async def cleanup_expired_previews(
        self,
        command: MissionPreviewCleanupPayload,
    ) -> MissionPreviewCleanupResultPayload:
        records = await self.repository.list_expired_review_previews(
            now=command.now,
            limit=command.limit,
            for_update=True,
        )
        refs: list[str] = []
        for record in records:
            if record.preview_ref:
                refs.append(record.preview_ref)
            record.preview_json = {}
            record.preview_ref = None
            record.updated_at = command.now
        await self._finish()
        return MissionPreviewCleanupResultPayload(
            review_item_ids=[record.review_item_id for record in records],
            preview_refs=refs,
        )


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _project_attention_request(
    run: MissionRunRecord,
) -> MissionAttentionRequestPayload | None:
    if run.status != MissionStatus.WAITING.value:
        return None
    pending = run.snapshot_json.get("pending_request")
    request = pending if isinstance(pending, dict) else {}
    reason = _text(run.snapshot_json.get("waiting_reason")) or "user_input"
    request_id = _text(request.get("request_id")) or f"waiting:{run.mission_id}:{run.state_version}"
    summary = (
        _text(request.get("summary"))
        or _text(request.get("question"))
        or _text(request.get("prompt"))
        or _attention_default_summary(reason)
    )

    inputs = _project_attention_inputs(reason, request)
    actions = [
        MissionAttentionActionPayload(
            action_id="reply",
            label="回到对话回复",
            action_type="reply_in_chat",
            primary=True,
        )
    ]
    if any(item.input_type == "file" for item in inputs):
        actions.append(
            MissionAttentionActionPayload(
                action_id="upload",
                label="添加材料",
                action_type="upload_file",
            )
        )
    if reason == "review":
        actions.append(
            MissionAttentionActionPayload(
                action_id="review",
                label="查看待确认内容",
                action_type="open_review",
            )
        )
    return MissionAttentionRequestPayload(
        request_id=request_id,
        reason=reason,
        title=_attention_title(reason),
        summary=summary,
        impact=_attention_impact(reason),
        required_inputs=inputs,
        actions=actions,
    )


def _project_attention_inputs(
    reason: str,
    request: dict,
) -> list[MissionAttentionInputPayload]:
    blocking = request.get("blocking_user_inputs")
    labels = [_text(value) for value in blocking] if isinstance(blocking, list) else []
    inputs = [
        MissionAttentionInputPayload(
            input_id=f"input-{index + 1}",
            label=label,
            input_type="file" if reason == "external_data" else "text",
        )
        for index, label in enumerate(labels)
        if label
    ]
    if inputs:
        return inputs
    if request.get("required_credits") is not None:
        return [
            MissionAttentionInputPayload(
                input_id="credits",
                label=f"补足本次任务所需的 {request['required_credits']} 点额度",
                input_type="credits",
            )
        ]
    if reason == "external_data":
        return [
            MissionAttentionInputPayload(
                input_id="source-material",
                label="任务所需的数据、文献或题目材料",
                input_type="file",
            )
        ]
    if reason in {"approval", "permission", "review"}:
        return [
            MissionAttentionInputPayload(
                input_id="decision",
                label="你的确认或调整意见",
                input_type="confirmation",
            )
        ]
    return [
        MissionAttentionInputPayload(
            input_id="response",
            label=_text(request.get("question")) or "完成当前阶段所需的补充信息",
            input_type="text",
        )
    ]


def _attention_title(reason: str) -> str:
    return {
        "clarification": "需要你明确一个关键选择",
        "approval": "需要你确认后继续",
        "permission": "需要你确认本次操作",
        "external_data": "需要你补充研究材料",
        "budget": "需要补足任务额度",
        "review": "有研究结果等待确认",
    }.get(reason, "需要你补充信息")


def _attention_default_summary(reason: str) -> str:
    return {
        "external_data": "当前研究缺少继续推进所需的材料，请在对话中补充或上传文件。",
        "budget": "当前可用额度不足以继续执行这项研究任务。",
        "review": "请确认当前研究结果或提出调整意见。",
    }.get(reason, "问津需要你的补充信息，收到后会从当前进度继续。")


def _attention_impact(reason: str) -> str:
    return {
        "external_data": "收到材料前，相关证据核验与后续写作会暂停。",
        "budget": "补足额度前，研究团队不会继续产生调用费用。",
        "review": "确认前，受保护的结果不会保存到工作区。",
        "permission": "确认前，本次受控操作不会执行。",
        "approval": "确认前，问津会保留当前进度，不进入下一阶段。",
    }.get(reason, "收到回复前，问津会保留当前进度并暂停后续阶段。")


def _project_stages(
    run: MissionRunRecord,
    *,
    observed_stage_ids: list[str] | None = None,
) -> tuple[list[str], list[MissionStageSummaryPayload]]:
    raw_ids = run.runtime_context_json.get("required_stage_ids")
    required_families = [item for item in raw_ids if isinstance(item, str)] if isinstance(raw_ids, list) else []
    acceptance = run.snapshot_json.get("stage_acceptance")
    accepted = acceptance if isinstance(acceptance, dict) else {}
    contracts = _stage_contracts(run.runtime_context_json.get("stage_contracts"))
    required = _project_stage_instance_ids(
        required_families,
        observed_ids=[
            *(stage_id for stage_id in accepted if isinstance(stage_id, str)),
            *((run.active_stage_id,) if run.active_stage_id else ()),
            *(observed_stage_ids or ()),
        ],
        contracts=contracts,
    )
    summaries: list[MissionStageSummaryPayload] = []
    for stage_id in required:
        value = accepted.get(stage_id)
        detail = value if isinstance(value, dict) else {}
        raw_status = _text(detail.get("result")) or _text(detail.get("status"))
        if raw_status in {"pass", "passed"}:
            status = "passed"
        elif raw_status in {"revise", "revising"}:
            status = "revising"
        elif raw_status in {"ask_user", "waiting"}:
            status = "waiting"
        elif stage_id == run.active_stage_id:
            status = "active"
        else:
            status = "pending"
        summaries.append(
            MissionStageSummaryPayload(
                stage_id=stage_id,
                title=_text(detail.get("title"))
                or _text(detail.get("label"))
                or _stage_projection_title(
                    workspace_type=run.workspace_type,
                    stage_id=stage_id,
                    contracts=contracts,
                ),
                status=status,
                summary=_text(detail.get("summary")),
            )
        )
    return required, summaries


def _stage_contracts(raw: object) -> tuple[StageAcceptanceContract, ...]:
    if not isinstance(raw, dict):
        return ()
    contracts: list[StageAcceptanceContract] = []
    for value in raw.values():
        if not isinstance(value, dict):
            continue
        try:
            contracts.append(StageAcceptanceContract.model_validate(value))
        except ValueError:
            continue
    return tuple(contracts)


def _project_stage_instance_ids(
    required_families: list[str],
    *,
    observed_ids: list[str],
    contracts: tuple[StageAcceptanceContract, ...],
) -> list[str]:
    family_contracts = {
        family_id: contract
        for family_id in required_families
        if (contract := next((item for item in contracts if item.stage_id == family_id), None))
        is not None
        and contract.instantiation.mode == "per_item"
    }
    family_order = {family_id: index for index, family_id in enumerate(required_families)}
    dynamic_instances: list[tuple[int, int, str]] = []
    families_with_instances: set[str] = set()
    for stage_id in dict.fromkeys(observed_ids):
        for family_id, contract in family_contracts.items():
            if not stage_id_matches_contract(contract, stage_id):
                continue
            index = stage_instance_index(contract.instantiation.instance_id_template, stage_id)
            if index is not None:
                dynamic_instances.append((index, family_order[family_id], stage_id))
                families_with_instances.add(family_id)
            break
    dynamic_ids = [stage_id for _, _, stage_id in sorted(dynamic_instances)]

    projected: list[str] = []
    consumed: set[str] = set()
    dynamic_block_inserted = False
    for family_id in required_families:
        if family_id in family_contracts:
            if dynamic_block_inserted:
                continue
            dynamic_block_inserted = True
            selected = [
                *dynamic_ids,
                *(
                    candidate
                    for candidate in required_families
                    if candidate in family_contracts and candidate not in families_with_instances
                ),
            ]
        else:
            selected = [family_id]
        for stage_id in selected:
            if stage_id not in consumed:
                projected.append(stage_id)
                consumed.add(stage_id)
    for stage_id in observed_ids:
        if stage_id not in consumed:
            projected.append(stage_id)
            consumed.add(stage_id)
    return projected


def _stage_projection_title(
    *,
    workspace_type: str,
    stage_id: str,
    contracts: tuple[StageAcceptanceContract, ...],
) -> str:
    if workspace_type == "math_modeling":
        labels = {
            "problem_understanding": "题目理解",
            "question_model": "逐问建模",
            "question_solution_validation": "逐问求解与验证",
            "paper_integration": "论文整合",
        }
        if stage_id in labels:
            return labels[stage_id]
        for contract in contracts:
            if contract.instantiation.mode != "per_item" or not stage_id_matches_contract(contract, stage_id):
                continue
            index = stage_instance_index(contract.instantiation.instance_id_template, stage_id)
            if index is not None and contract.stage_id == "question_model":
                return f"第 {index} 问建模"
            if index is not None and contract.stage_id == "question_solution_validation":
                return f"第 {index} 问求解与验证"
    return stage_id.replace("_", " ")


def _project_subagents(
    run: MissionRunRecord,
) -> tuple[str | None, list[MissionSubagentSummaryPayload]]:
    team_summary = _text(run.snapshot_json.get("team_summary"))
    raw = run.snapshot_json.get("subagent_summary")
    summary = raw if isinstance(raw, dict) else {}
    latest = summary.get("latest")
    rows = latest if isinstance(latest, list) else []
    projected: list[MissionSubagentSummaryPayload] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        projected.append(
            MissionSubagentSummaryPayload(
                subagent_id=_text(row.get("job_id")) or f"member-{index + 1}",
                display_name=_text(row.get("display_name")) or f"研究成员 {index + 1}",
                role_label=_text(row.get("role_label")) or "研究协作",
                status=_text(row.get("status")) or "working",
                summary=_text(row.get("result_brief")),
            )
        )
    return team_summary, projected


def _project_evidence(record: MissionItemRecord) -> MissionEvidenceSummaryPayload:
    payload = record.payload_json or {}
    source_type = _text(payload.get("source_type")) or "paper"
    if source_type not in {"paper", "web_page", "dataset", "upload"}:
        source_type = "paper"
    return MissionEvidenceSummaryPayload(
        item_id=record.id,
        seq=record.seq,
        title=_text(payload.get("title")) or record.summary or "研究证据",
        source_type=source_type,
        source_label=_text(payload.get("source_label")) or _text(payload.get("source")),
        summary=_text(payload.get("summary")) or record.summary,
        citation=_text(payload.get("citation")),
        verified=payload.get("verified") is True,
    )


def _project_artifact(
    record: MissionItemRecord,
    committed_review_ids: set[str],
) -> MissionArtifactSummaryPayload:
    payload = record.payload_json or {}
    review_item_id = _text(payload.get("review_item_id"))
    return MissionArtifactSummaryPayload(
        item_id=record.id,
        seq=record.seq,
        title=_text(payload.get("title")) or record.summary or "研究成果",
        kind=_text(payload.get("kind")) or record.item_type,
        summary=_text(payload.get("summary")) or record.summary,
        preview_available=bool(record.payload_ref or payload),
        committed=bool(review_item_id and review_item_id in committed_review_ids),
    )


def _project_quality_highlights(run: MissionRunRecord) -> list[str]:
    raw = run.snapshot_json.get("quality_summary")
    summary = raw if isinstance(raw, dict) else {}
    highlights = summary.get("highlights")
    rows = highlights if isinstance(highlights, list) else []
    values: list[str] = []
    for row in rows:
        value = _text(row.get("text")) if isinstance(row, dict) else _text(row)
        if value:
            values.append(value)
    return values


def _canonical_preview(draft) -> tuple[dict, str]:
    if not draft.preview_json:
        raise DataServiceValidationError("review preview must contain bounded display metadata")
    if draft.preview_ref is not None and draft.preview_expires_at is None:
        raise DataServiceValidationError("external review preview requires preview_expires_at")
    encoded = json.dumps(
        draft.preview_json,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    canonical = json.loads(encoded)
    return canonical, hashlib.sha256(encoded).hexdigest()


__all__ = ["MissionStore", "TERMINAL_MISSION_STATUSES"]

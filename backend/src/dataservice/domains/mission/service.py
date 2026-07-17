"""Transactional MissionStore for lifecycle, ledger, review, and commit facts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.policies import calculate_model_usage_credits
from src.contracts.mission_input import merge_mission_input_manifests
from src.contracts.prism_context import PrismContextRef
from src.contracts.review_policy import project_review_policy
from src.contracts.stage_acceptance import (
    StageAcceptanceContract,
    format_stage_instance_id,
    stage_id_matches_contract,
    stage_instance_index,
)
from src.database.models.mission import (
    MissionCommitRecord,
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
    mission_run_to_view_payload,
)
from src.dataservice.domains.mission.repository import MissionRepository
from src.dataservice.domains.pricing.repository import PricingPolicyRepository
from src.dataservice.domains.pricing.resolver import CanonicalPricingResolver
from src.dataservice_client.contracts.mission import (
    MissionActivityPayload,
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionArtifactPagePayload,
    MissionArtifactSummaryPayload,
    MissionAttentionActionPayload,
    MissionAttentionInputPayload,
    MissionAttentionRequestPayload,
    MissionCheckpointPayload,
    MissionCommitCreatePayload,
    MissionCommitCreateResultPayload,
    MissionCommitFinishPayload,
    MissionCommitPagePayload,
    MissionCommitResultPayload,
    MissionCommitStartPayload,
    MissionCommitStatus,
    MissionCommitSummaryPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionCursorPagePayload,
    MissionDerivedReviewItemCreatePayload,
    MissionDispatchReleasePayload,
    MissionEvidencePagePayload,
    MissionEvidenceSummaryPayload,
    MissionHistoryPagePayload,
    MissionItemDraftPayload,
    MissionItemPagePayload,
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
    MissionReviewItemDraftPayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewItemsResultPayload,
    MissionReviewPagePayload,
    MissionReviewPolicyPayload,
    MissionReviewSummaryPayload,
    MissionReviewViewItemPayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPatchPayload,
    MissionRunPayload,
    MissionStageSummaryPayload,
    MissionStatus,
    MissionSubagentSummaryPayload,
    MissionUserCommandPayload,
    MissionUserSummaryPayload,
    MissionViewPayload,
    MissionWorkspaceSummaryPayload,
    validate_mission_snapshot,
)

TERMINAL_MISSION_STATUSES = frozenset({"completed", "failed", "cancelled"})
NONTERMINAL_MISSION_STATUSES = frozenset({"created", "planning", "running", "waiting"})
_HISTORY_CURSOR_VERSION = 1
_MISSION_RECORD_CURSOR_VERSION = 1
_MISSION_VIEW_READ_ATTEMPTS = 3


def _encode_history_cursor(*, updated_at: datetime, mission_id: str) -> str:
    normalized_updated_at = updated_at if updated_at.tzinfo is not None else updated_at.replace(tzinfo=UTC)
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


def _encode_record_cursor(
    *,
    kind: str,
    created_at: datetime,
    record_id: str,
) -> str:
    normalized_created_at = (
        created_at
        if created_at.tzinfo is not None
        else created_at.replace(tzinfo=UTC)
    )
    payload = json.dumps(
        {
            "created_at": normalized_created_at.isoformat(),
            "kind": kind,
            "record_id": record_id,
            "version": _MISSION_RECORD_CURSOR_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_record_cursor(cursor: str, *, kind: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {
            "created_at",
            "kind",
            "record_id",
            "version",
        }:
            raise ValueError("invalid cursor shape")
        if payload["version"] != _MISSION_RECORD_CURSOR_VERSION:
            raise ValueError("unsupported cursor version")
        if payload["kind"] != kind:
            raise ValueError("cursor kind mismatch")
        created_at = _aware(datetime.fromisoformat(str(payload["created_at"])))
        record_id = str(payload["record_id"])
        if not record_id:
            raise ValueError("missing record id")
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        raise DataServiceValidationError(
            "Invalid Mission projection cursor",
            detail={"kind": kind},
        ) from exc
    return created_at, record_id


class MissionProjectionStaleError(DataServiceConflictError):
    """A coherent MissionView could not be observed within the read budget."""

    code = "MISSION_PROJECTION_STALE"


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
    "created": frozenset({"planning", "waiting", "failed", "cancelled"}),
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
    terminals = [item for item in items if item.item_type == "operation_terminal" and item.seq > claim.seq]
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
        claim_token=str(claim_payload["claim_token"]),
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
        self._terminalized_mission_ids: set[str] = set()

    async def _finish(self) -> None:
        await self._settle_terminal_missions()
        await self.session.flush()
        if self.autocommit:
            await self.session.commit()

    async def _settle_terminal_missions(self) -> None:
        if not self._terminalized_mission_ids:
            return
        from src.dataservice.domains.credit.service import DataServiceCreditService

        mission_ids = tuple(self._terminalized_mission_ids)
        self._terminalized_mission_ids.clear()
        credits = DataServiceCreditService(self.session, autocommit=False)
        for mission_id in mission_ids:
            run = await self._locked_run(mission_id)
            billing = dict((run.snapshot_json or {}).get("billing") or {})
            reservation = await credits.repository.get_mission_reservation_for_update(
                mission_id
            )
            usage_summary: dict[str, Any] = {}
            if reservation is None:
                billing["state"] = "settled"
                billing["free_policy"] = True
                billing["settled_credits"] = 0
            else:
                settled_credits, usage_summary = await self._calculate_settlement(
                    run,
                    reservation,
                )
                reservation, transaction = await credits.settle_reservation(
                    reservation_id=str(reservation.id),
                    settled_credits=settled_credits,
                    description=f"Mission {run.title[:120]} settlement",
                    mission_policy_id=run.mission_policy_id,
                    mission_id=mission_id,
                    metadata={
                        "mission_id": mission_id,
                        "status": run.status,
                        "pricing_policy_id": dict(
                            reservation.metadata_json or {}
                        ).get("pricing_policy_id"),
                        "usage": usage_summary,
                    },
                )
                billing.update(
                    {
                        "state": "settled",
                        "free_policy": False,
                        "reservation_id": str(reservation.id),
                        "estimated_credits": int(
                            reservation.reserved_credits or 0
                        ),
                        "settled_credits": int(reservation.settled_credits or 0),
                        "transaction_id": (
                            str(transaction.id) if transaction is not None else None
                        ),
                    }
                )
            snapshot = dict(run.snapshot_json or {})
            snapshot["billing"] = billing
            run.snapshot_json = validate_mission_snapshot(snapshot)
            now = await self.repository.database_now()
            self._append_drafts(
                run,
                [
                    MissionItemDraftPayload(
                        item_type="billing_settled",
                        phase="completed",
                        producer="mission_store",
                        summary="Mission billing settled with terminal state",
                        payload_json={
                            "status": run.status,
                            "settled_credits": billing.get("settled_credits", 0),
                            "transaction_id": billing.get("transaction_id"),
                            "usage": usage_summary if reservation is not None else {},
                        },
                    )
                ],
                now=now,
            )
            self._touch(run, now)

    async def _calculate_settlement(
        self,
        run: MissionRunRecord,
        reservation: Any,
    ) -> tuple[int, dict[str, Any]]:
        usage_items = await self.repository.list_items(
            mission_id=str(run.mission_id),
            item_type="usage_receipt",
            limit=10_000,
        )
        usage = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }
        for item in usage_items:
            raw_usage = dict((item.payload_json or {}).get("usage") or {})
            for key in usage:
                usage[key] += max(int(raw_usage.get(key) or 0), 0)
        if run.status == MissionStatus.FAILED.value or usage["total_tokens"] <= 0:
            return 0, usage

        pricing = PricingPolicyRepository(self.session)
        resolver = CanonicalPricingResolver(self.session)
        model_policy = await resolver.resolve_model_usage(run.model_id)
        global_policy = await resolver.resolve_global_credit()
        charge = calculate_model_usage_credits(
            model_policy=dict(model_policy.config_json or {}),
            global_policy=(
                dict(global_policy.config_json or {})
                if global_policy is not None
                else None
            ),
            token_usage=usage,
            surface="mission",
        )
        credits = charge.credits_to_charge
        if run.status == MissionStatus.COMPLETED.value:
            pricing_policy_id = str(
                dict(reservation.metadata_json or {}).get("pricing_policy_id") or ""
            )
            mission_policy = (
                await pricing.get_policy(pricing_policy_id)
                if pricing_policy_id
                else None
            )
            if mission_policy is not None:
                credits = max(
                    credits,
                    int(
                        dict(mission_policy.config_json or {}).get(
                            "base_fee_credits",
                            0,
                        )
                        or 0
                    ),
                )
        usage["calculated_credits"] = credits
        return min(credits, max(int(reservation.reserved_credits or 0), 0)), usage

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
        if run.status in TERMINAL_MISSION_STATUSES or run.lease_owner is None or run.lease_epoch != lease_epoch or expires_at is None or expires_at <= now:
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

    def _transition_status(
        self,
        run: MissionRunRecord,
        status: MissionStatus,
        *,
        now: datetime,
    ) -> None:
        target = status.value
        if target == run.status:
            if target == "waiting" or target in TERMINAL_MISSION_STATUSES:
                run.lease_owner = None
                run.lease_expires_at = None
                run.next_wakeup_at = None
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
            run.next_wakeup_at = None
        if target in TERMINAL_MISSION_STATUSES:
            run.next_wakeup_at = None
            run.dispatch_owner = None
            run.dispatch_expires_at = None
            run.completed_at = now
            self._terminalized_mission_ids.add(str(run.mission_id))

    def _resolve_review_wait(
        self,
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
        self._transition_status(run, MissionStatus.PLANNING, now=now)
        return True

    def _apply_patch(
        self,
        run: MissionRunRecord,
        patch: MissionRunPatchPayload,
        *,
        now: datetime,
    ) -> None:
        fields = patch.model_fields_set
        if patch.status is not None:
            self._transition_status(run, patch.status, now=now)
        if patch.review_mode is not None:
            run.review_mode = patch.review_mode.value
        if "active_stage_id" in fields:
            run.active_stage_id = patch.active_stage_id
        if "context_checkpoint_ref" in fields:
            run.context_checkpoint_ref = patch.context_checkpoint_ref
        if "next_wakeup_at" in fields and run.status not in TERMINAL_MISSION_STATUSES:
            run.next_wakeup_at = patch.next_wakeup_at
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
            if draft.item_type == "evidence":
                run.evidence_count += 1
            elif draft.item_type in {"artifact", "output"}:
                run.artifact_count += 1
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
        run.snapshot_json = validate_mission_snapshot(snapshot_json)
        self._transition_status(run, status, now=now)
        run.next_wakeup_at = now if status is MissionStatus.PLANNING else None
        self._append_drafts(run, [item], now=now)
        self._touch(run, now)
        await self._finish()
        return mission_run_to_payload(run)

    async def load_run_snapshot(self, mission_id: str) -> MissionRunPayload | None:
        record = await self.repository.get_run(mission_id)
        return mission_run_to_payload(record) if record is not None else None

    async def load_commit_for_review_item(
        self,
        mission_id: str,
        review_item_id: str,
    ) -> MissionCommitResultPayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        commit = await self.repository.find_commit_by_review_item(
            mission_id=mission_id,
            review_item_id=review_item_id,
        )
        if commit is None:
            return None
        return MissionCommitResultPayload(
            mission=mission_run_to_payload(run),
            commit=mission_commit_to_payload(commit),
        )

    async def list_commits_page(
        self,
        mission_id: str,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> MissionCommitPagePayload:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        after_created_at: datetime | None = None
        after_commit_id: str | None = None
        if cursor is not None:
            after_created_at, after_commit_id = _decode_record_cursor(
                cursor,
                kind="commit",
            )
        records = await self.repository.list_commits(
            mission_id=mission_id,
            after_created_at=after_created_at,
            after_commit_id=after_commit_id,
            limit=limit + 1,
        )
        page_records = records[:limit]
        next_cursor = None
        if len(records) > limit and page_records:
            last = page_records[-1]
            next_cursor = _encode_record_cursor(
                kind="commit",
                created_at=last.created_at,
                record_id=str(last.commit_id),
            )
        return MissionCommitPagePayload(
            items=[mission_commit_to_payload(record) for record in page_records],
            page=MissionCursorPagePayload(
                total=await self.repository.count_commits(mission_id=mission_id),
                returned=len(page_records),
                next_cursor=next_cursor,
            ),
        )

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

    async def latest_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        record = await self.repository.find_latest_for_thread(thread_id)
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
    ) -> MissionHistoryPagePayload:
        before_updated_at, before_mission_id = _decode_history_cursor(cursor) if cursor else (None, None)
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
        return MissionHistoryPagePayload(
            items=[mission_run_to_view_payload(record) for record in page_records],
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

    async def get_workspace_summary(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
    ) -> MissionWorkspaceSummaryPayload:
        rows = await self.repository.aggregate_workspace_runs(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        status_counts = {status: count for status, count, _, _, _ in rows}
        latest_records = await self.repository.list_runs(
            workspace_id=workspace_id,
            user_id=user_id,
            limit=1,
        )
        active_records = await self.repository.list_runs(
            workspace_id=workspace_id,
            user_id=user_id,
            status=list(NONTERMINAL_MISSION_STATUSES),
            limit=1,
        )
        return MissionWorkspaceSummaryPayload(
            total=sum(status_counts.values()),
            status_counts=status_counts,
            pending_review_count=sum(row[2] for row in rows),
            evidence_count=sum(row[3] for row in rows),
            artifact_count=sum(row[4] for row in rows),
            latest=(mission_run_to_view_payload(latest_records[0]) if latest_records else None),
            active=(mission_run_to_view_payload(active_records[0]) if active_records else None),
        )

    async def get_user_summary(
        self,
        *,
        user_id: str,
        recent_limit: int = 10,
    ) -> MissionUserSummaryPayload:
        rows = await self.repository.aggregate_user_runs(user_id=user_id)
        recent_records = await self.repository.list_user_runs(
            user_id=user_id,
            limit=recent_limit,
        )
        status_counts = {status: count for status, count in rows}
        return MissionUserSummaryPayload(
            total=sum(status_counts.values()),
            status_counts=status_counts,
            recent=[mission_run_to_view_payload(record) for record in recent_records],
        )

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
        if run.dispatch_owner != command.worker_id or run.dispatch_epoch != command.dispatch_epoch:
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
        if receipt is not None and (receipt.kind != command.kind or receipt.request_hash != command.request_hash):
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
        claim_token = secrets.token_urlsafe(32)
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
                        "claim_token": claim_token,
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
        if receipt.claim_token != command.claim_token:
            raise DataServiceConflictError("Operation terminal claim fence was lost")
        desired = command.model_dump(mode="json")["receipt_json"]
        reference_projection = [item.model_dump(mode="json") for item in command.references]
        reference_projection_hash = hashlib.sha256(
            json.dumps(
                reference_projection,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if receipt.status.value != "claimed":
            terminal_item = next(
                (item for item in reversed(items) if item.item_type == "operation_terminal"),
                None,
            )
            same = (
                receipt.status == command.status
                and receipt.receipt_json == desired
                and receipt.payload_ref == command.payload_ref
                and terminal_item is not None
                and terminal_item.payload_json.get("reference_projection_hash") == reference_projection_hash
            )
            if not same:
                raise DataServiceConflictError("Terminal operation receipt is immutable")
            return MissionOperationFinishResultPayload(
                receipt=receipt,
                finalized=False,
            )
        if receipt.claimant != command.claimant or receipt.lease_epoch != command.lease_epoch:
            raise DataServiceConflictError("Operation terminal fence was lost")
        appended = self._append_drafts(
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
                        "claim_token": command.claim_token,
                        "attempt": receipt.attempt,
                        "receipt": desired,
                        "reference_projection_hash": reference_projection_hash,
                    },
                    payload_ref=command.payload_ref,
                ),
                *[
                    MissionItemDraftPayload(
                        item_type=reference.category,
                        operation_id=command.operation_key,
                        phase="completed",
                        stage_id=command.stage_id,
                        producer=command.producer or command.claimant,
                        summary=reference.title or reference.reference_id,
                        payload_json={
                            "reference_id": reference.reference_id,
                            "kind": reference.reference_kind,
                            "title": reference.title,
                            "uri": reference.uri,
                            "metadata": reference.metadata,
                            "source_type": reference.source_type,
                            "verified": reference.verified,
                            "receipt_operation_key": command.operation_key,
                        },
                        payload_ref=reference.reference_id,
                    )
                    for reference in command.references
                ],
            ],
            now=now,
        )
        terminal = appended[0]
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
                    payload_json={"pending_request": pending_request},
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

    async def create_review_items(
        self,
        mission_id: str,
        command: MissionReviewItemsCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        run = await self._locked_run(mission_id)
        replay = await self._review_item_replay(
            run,
            mission_id=mission_id,
            drafts=command.review_items,
        )
        if replay is not None:
            return replay
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.lease_owner,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        return await self._create_new_review_items_locked(
            run,
            mission_id=mission_id,
            drafts=command.review_items,
            now=now,
            producer="mission_runtime",
            ledger_items=command.items,
            snapshot_json=command.snapshot_json,
            patch=command.patch,
        )

    async def create_derived_review_item(
        self,
        mission_id: str,
        command: MissionDerivedReviewItemCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        """Stage one review item derived from a committed Mission output."""

        run = await self._locked_run(mission_id)
        source = await self.repository.get_review_item(
            command.source_review_item_id,
            for_update=True,
        )
        if (
            source is None
            or source.mission_id != mission_id
            or source.status != "committed"
            or source.target_kind != "workspace_asset"
        ):
            raise DataServiceConflictError(
                "Derived review items require a committed source review item"
            )
        source_commit = await self.repository.find_commit_by_review_item(
            mission_id=mission_id,
            review_item_id=source.review_item_id,
        )
        if source_commit is None or source_commit.status != "committed":
            raise DataServiceConflictError(
                "Derived review source has no committed materialization receipt"
            )
        commit_items = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=source_commit.commit_key,
            item_type="commit_completed",
        )
        if not commit_items:
            raise DataServiceConflictError(
                "Derived review source has no immutable commit receipt"
            )
        draft = command.item.model_copy(
            update={"source_item_seq": commit_items[-1].seq}
        )
        materialization = draft.preview_json.get("materialization")
        materialization_payload = (
            materialization.get("payload")
            if isinstance(materialization, dict)
            else None
        )
        committed_target_ref = str(
            dict(source_commit.targets_json or {}).get("target_ref") or ""
        )
        if (
            draft.target_kind != "prism_visual_insertion"
            or draft.target_room != "documents"
            or not draft.target_ref
            or not isinstance(materialization, dict)
            or materialization.get("operation") != "documents.insert_visual_asset"
            or not isinstance(materialization_payload, dict)
            or materialization_payload.get("asset_id") != committed_target_ref
            or materialization_payload.get("source_mission_commit_id")
            != source_commit.commit_id
        ):
            raise DataServiceValidationError(
                "Derived visual review items require one canonical Prism insertion target"
            )
        replay = await self._review_item_replay(
            run,
            mission_id=mission_id,
            drafts=(draft,),
        )
        if replay is not None:
            return replay
        self._require_state_version(run, command.expected_state_version)
        now = await self.repository.database_now()
        return await self._create_new_review_items_locked(
            run,
            mission_id=mission_id,
            drafts=(draft,),
            now=now,
            producer=command.actor_user_id,
        )

    async def _review_item_replay(
        self,
        run: MissionRunRecord,
        *,
        mission_id: str,
        drafts: Sequence[MissionReviewItemDraftPayload],
    ) -> MissionReviewItemsResultPayload | None:
        requested_ids = [item.review_item_id for item in drafts]
        if len(requested_ids) != len(set(requested_ids)):
            raise DataServiceValidationError("review_item_id values must be unique")
        output_keys = [item.output_key for item in drafts]
        if len(output_keys) != len(set(output_keys)):
            raise DataServiceValidationError("output_key values must be unique within one review batch")
        existing = await self.repository.list_review_items_by_ids(
            mission_id=mission_id,
            review_item_ids=requested_ids,
        )
        if existing:
            if len(existing) != len(requested_ids):
                raise DataServiceConflictError("Review-item retry mixed existing and new identifiers")
            existing_by_id = {item.review_item_id: item for item in existing}
            for draft in drafts:
                record = existing_by_id[draft.review_item_id]
                preview_json, preview_hash = _canonical_preview(draft)
                if (
                    record.source_item_seq != draft.source_item_seq
                    or record.output_key != draft.output_key
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
                ):
                    raise DataServiceConflictError(
                        "review_item_id was reused with different candidate content",
                        detail={"review_item_id": draft.review_item_id},
                    )
            return MissionReviewItemsResultPayload(
                mission=mission_run_to_payload(run),
                items=[
                    mission_review_item_to_payload(
                        existing_by_id[item_id],
                        review_mode=run.review_mode,
                    )
                    for item_id in requested_ids
                ],
            )
        return None

    async def _create_new_review_items_locked(
        self,
        run: MissionRunRecord,
        *,
        mission_id: str,
        drafts: Sequence[MissionReviewItemDraftPayload],
        now: datetime,
        producer: str,
        ledger_items: Sequence[MissionItemDraftPayload] = (),
        snapshot_json: dict[str, object] | None = None,
        patch: MissionRunPatchPayload | None = None,
    ) -> MissionReviewItemsResultPayload:
        output_keys = [item.output_key for item in drafts]
        candidate_destinations = {
            destination
            for draft in drafts
            if (
                destination := _review_materialization_destination(
                    target_kind=draft.target_kind,
                    target_room=draft.target_room,
                    target_ref=draft.target_ref,
                    preview_json=draft.preview_json,
                )
            )
            is not None
        }
        prior_candidates = await self.repository.list_review_items_for_replacement(
            mission_id=mission_id,
            output_keys=output_keys,
            destinations=list(candidate_destinations),
            for_update=True,
        )
        accepted_candidate_ids = [
            str(record.review_item_id)
            for record in prior_candidates
            if record.status == "accepted"
        ]
        active_commits = {
            str(commit.review_item_id): commit
            for commit in await self.repository.list_commits_by_review_item_ids(
                mission_id=mission_id,
                review_item_ids=accepted_candidate_ids,
            )
        }
        superseded_ids: list[str] = []
        superseded_pending = 0
        for record in prior_candidates:
            same_output = record.output_key in output_keys
            same_destination = (
                _review_materialization_destination(
                    target_kind=record.target_kind,
                    target_room=record.target_room,
                    target_ref=record.target_ref,
                    preview_json=dict(record.preview_json or {}),
                )
                in candidate_destinations
            )
            if not same_output and not same_destination:
                continue
            if record.status in {"committed", "superseded"}:
                continue
            if record.status == "accepted":
                active_commit = active_commits.get(str(record.review_item_id))
                if active_commit is not None and active_commit.status in {
                    "pending",
                    "applying",
                }:
                    raise DataServiceConflictError(
                        "Cannot replace an output while its accepted candidate is being saved",
                        detail={
                            "review_item_id": record.review_item_id,
                            "commit_status": active_commit.status,
                        },
                    )
            if record.status == "pending":
                superseded_pending += 1
            record.status = "superseded"
            record.decision_json = {
                "decision": "superseded",
                "reason": "A newer candidate now represents this output.",
            }
            record.decided_by = None
            record.decided_at = now
            record.updated_at = now
            superseded_ids.append(str(record.review_item_id))
        records: list[MissionReviewItemRecord] = []
        audit_drafts: list[MissionItemDraftPayload] = []
        for review_item_id in superseded_ids:
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_candidate_superseded",
                    operation_id=review_item_id,
                    phase="completed",
                    producer=producer,
                    summary="A newer candidate replaced this output.",
                    payload_json={"review_item_id": review_item_id},
                )
            )
        source_seqs = tuple(
            sorted(
                {
                    draft.source_item_seq
                    for draft in drafts
                    if draft.source_item_seq is not None
                }
            )
        )
        source_items = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=source_seqs,
        )
        if {record.seq for record in source_items} != set(source_seqs):
            raise DataServiceValidationError(
                "source_item_seq must reference the same mission ledger"
            )
        for draft in drafts:
            preview_json, preview_hash = _canonical_preview(draft)
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
                }
            )
            records.append(self.repository.create_review_item(values))
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_candidate_created",
                    operation_id=draft.review_item_id,
                    phase="completed",
                    producer=producer,
                    summary=draft.title,
                    risk_level=draft.risk_level,
                    payload_json={
                        "review_item_id": draft.review_item_id,
                        "target_kind": draft.target_kind,
                        "target_room": draft.target_room,
                    },
                )
            )
        self._append_drafts(run, [*audit_drafts, *ledger_items], now=now)
        run.pending_review_count = max(
            run.pending_review_count - superseded_pending + len(records),
            0,
        )
        if snapshot_json is not None:
            run.snapshot_json = dict(snapshot_json)
        if patch is not None:
            self._apply_patch(run, patch, now=now)
        self._touch(run, now)
        await self._finish()
        return MissionReviewItemsResultPayload(
            mission=mission_run_to_payload(run),
            items=[
                mission_review_item_to_payload(item, review_mode=run.review_mode)
                for item in records
            ],
            superseded_review_item_ids=superseded_ids,
        )

    async def list_review_items(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[MissionReviewItemPayload]:
        page = await self.list_review_items_page(
            mission_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        return page.items

    async def list_review_items_page(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> MissionReviewPagePayload:
        run = await self.repository.get_run(mission_id)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found")
        after_created_at: datetime | None = None
        after_review_item_id: str | None = None
        if cursor is not None:
            after_created_at, after_review_item_id = _decode_record_cursor(
                cursor,
                kind="review",
            )
        records = await self.repository.list_review_items(
            mission_id=mission_id,
            status=status,
            after_created_at=after_created_at,
            after_review_item_id=after_review_item_id,
            limit=limit + 1,
        )
        page_records = records[:limit]
        next_cursor = None
        if len(records) > limit and page_records:
            last = page_records[-1]
            next_cursor = _encode_record_cursor(
                kind="review",
                created_at=last.created_at,
                record_id=str(last.review_item_id),
            )
        return MissionReviewPagePayload(
            items=[
                mission_review_item_to_payload(record, review_mode=run.review_mode)
                for record in page_records
            ],
            page=MissionCursorPagePayload(
                total=await self.repository.count_review_items(
                    mission_id=mission_id,
                    status=status,
                ),
                returned=len(page_records),
                next_cursor=next_cursor,
            ),
        )

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
                items=[
                    mission_review_item_to_payload(
                        by_id[item_id],
                        review_mode=run.review_mode,
                    )
                    for item_id in requested_ids
                ],
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
        accepted_review_ids = [
            str(record.review_item_id)
            for record in records
            if record.status == "accepted"
        ]
        active_commits = {
            str(commit.review_item_id): commit
            for commit in await self.repository.list_commits_by_review_item_ids(
                mission_id=mission_id,
                review_item_ids=accepted_review_ids,
            )
        }
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
                active_commit = active_commits.get(str(record.review_item_id))
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
        revision_ids = [decision.review_item_id for decision in command.decisions if decision.status.value != "accepted"]
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
            items=[
                mission_review_item_to_payload(
                    by_id[item_id],
                    review_mode=run.review_mode,
                )
                for item_id in requested_ids
            ],
        )

    async def record_commit(
        self,
        mission_id: str,
        command: MissionCommitCreatePayload,
    ) -> MissionCommitCreateResultPayload:
        run = await self._locked_run(mission_id)
        existing_by_key = await self.repository.find_commit_by_key(mission_id=mission_id, commit_key=command.commit_key)
        existing_by_item = await self.repository.find_commit_by_review_item(
            mission_id=mission_id,
            review_item_id=command.review_item_id,
        )
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
            if commit.attempt_expires_at is not None and _aware(commit.attempt_expires_at) > _aware(now):
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
            expected_error = dict(command.error_json) if command.error_json is not None else None
            if commit.attempt_token != command.attempt_token or dict(commit.targets_json or {}) != dict(command.targets_json) or commit.error_json != expected_error:
                raise DataServiceConflictError("MissionCommit terminal replay does not match the stored receipt")
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
        page = await self.get_items_page(
            mission_id,
            after_seq=after_seq,
            limit=limit,
            item_type=item_type,
            operation_id=operation_id,
        )
        return page.items

    async def get_items_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> MissionItemPagePayload:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        if operation_id is not None:
            records = await self.repository.list_items_by_operation(
                mission_id=mission_id,
                operation_id=operation_id,
                item_type=item_type,
                after_seq=after_seq,
                limit=limit + 1,
            )
        else:
            records = await self.repository.list_items(
                mission_id=mission_id,
                after_seq=after_seq,
                limit=limit + 1,
                item_type=item_type,
            )
        page_records = records[:limit]
        return MissionItemPagePayload(
            items=[mission_item_to_payload(record) for record in page_records],
            page=MissionProjectionPagePayload(
                total=await self.repository.count_items(
                    mission_id=mission_id,
                    item_type=item_type,
                    operation_id=operation_id,
                ),
                returned=len(page_records),
                next_cursor=(
                    page_records[-1].seq
                    if len(records) > limit and page_records
                    else None
                ),
            ),
        )

    async def list_items_by_seqs(
        self,
        mission_id: str,
        *,
        seqs: tuple[int, ...],
    ) -> list[MissionItemPayload]:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        records = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=seqs,
        )
        return [mission_item_to_payload(record) for record in records]

    async def get_view(
        self,
        mission_id: str,
        *,
        projection_item_limit: int = 50,
    ) -> MissionViewPayload | None:
        last_start_version: int | None = None
        last_end_version: int | None = None
        for _attempt in range(_MISSION_VIEW_READ_ATTEMPTS):
            start_version = await self.repository.get_run_state_version(mission_id)
            if start_version is None:
                return None
            view = await self._project_view_once(
                mission_id,
                projection_item_limit=projection_item_limit,
            )
            if view is None:
                return None
            end_version = await self.repository.get_run_state_version(mission_id)
            if (
                start_version == end_version
                and view.mission.state_version == start_version
            ):
                return view
            last_start_version = start_version
            last_end_version = end_version
            self.session.expire_all()
        raise MissionProjectionStaleError(
            "Mission projection changed repeatedly while it was being read",
            detail={
                "mission_id": mission_id,
                "attempts": _MISSION_VIEW_READ_ATTEMPTS,
                "start_state_version": last_start_version,
                "end_state_version": last_end_version,
            },
        )

    async def _project_view_once(
        self,
        mission_id: str,
        *,
        projection_item_limit: int,
    ) -> MissionViewPayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        visible_review_records = await self.repository.list_current_review_items(
            mission_id=mission_id,
            limit=projection_item_limit,
        )
        artifact_records = await self.repository.list_current_artifact_review_items(
            mission_id=mission_id,
            limit=projection_item_limit + 1,
        )
        artifact_review_records = artifact_records[:projection_item_limit]
        review_status_counts = await self.repository.aggregate_current_review_statuses(
            mission_id=mission_id
        )
        commit_status_counts = await self.repository.aggregate_commit_statuses(
            mission_id=mission_id
        )
        projected_review_ids = {
            str(record.review_item_id)
            for record in [*visible_review_records, *artifact_review_records]
        }
        commit_records = await self.repository.list_commits_by_review_item_ids(
            mission_id=mission_id,
            review_item_ids=sorted(projected_review_ids),
        )
        evidence_records = await self.repository.list_items_by_types(
            mission_id=mission_id,
            item_types=("evidence",),
            limit=projection_item_limit + 1,
        )
        pending_review_sources = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=tuple(record.source_item_seq for record in visible_review_records if record.status == "pending" and record.source_item_seq is not None),
        )
        review_counts = {status: 0 for status in _REVIEW_TRANSITIONS}
        review_counts.update(dict(review_status_counts))
        commit_counts = {status: 0 for status in ("pending", "applying", "committed", "failed", "cancelled")}
        commit_counts.update(dict(commit_status_counts))
        evidence_page_records = evidence_records[:projection_item_limit]
        required_stage_ids, stage_summaries = _project_stages(
            run,
            observed_stage_ids=[record.stage_id for record in pending_review_sources if record.stage_id is not None],
        )
        team_summary, subagents = _project_subagents(run)
        committed_review_ids = {record.review_item_id for record in commit_records if record.status == "committed"}
        commits_by_review_item = {
            str(record.review_item_id): record for record in commit_records
        }
        projection_now = datetime.now(UTC)
        return MissionViewPayload(
            mission=mission_run_to_view_payload(run),
            activity=_project_activity(run),
            attention_request=_project_attention_request(run),
            review_summary=MissionReviewSummaryPayload(**review_counts),
            commit_summary=MissionCommitSummaryPayload(**commit_counts),
            review_items=[
                _project_review_view_item(
                    record,
                    review_mode=run.review_mode,
                    commit=commits_by_review_item.get(str(record.review_item_id)),
                    now=projection_now,
                )
                for record in visible_review_records
            ],
            required_stage_ids=required_stage_ids,
            stage_summaries=stage_summaries,
            team_summary=team_summary,
            subagents=subagents,
            evidence_items=[_project_evidence(record) for record in evidence_page_records],
            evidence_page=MissionProjectionPagePayload(
                total=run.evidence_count,
                returned=len(evidence_page_records),
                next_cursor=(evidence_page_records[-1].seq if len(evidence_records) > projection_item_limit else None),
            ),
            artifact_items=[
                _project_artifact(record, committed_review_ids)
                for record in artifact_review_records
            ],
            artifact_page=MissionProjectionPagePayload(
                total=await self.repository.count_current_artifact_review_items(
                    mission_id=mission_id
                ),
                returned=len(artifact_review_records),
                next_cursor=(
                    artifact_review_records[-1].source_item_seq
                    if len(artifact_records) > projection_item_limit
                    else None
                ),
                next_tiebreaker=(
                    str(artifact_review_records[-1].review_item_id)
                    if len(artifact_records) > projection_item_limit
                    else None
                ),
            ),
            review_policy=MissionReviewPolicyPayload(
                mode=run.review_mode,
                protected_outputs_require_confirmation=True,
                draft_outputs_may_be_automatic=run.review_mode != "review_all",
            ),
            review_selection_revision=_review_selection_revision(
                visible_review_records,
                review_mode=run.review_mode,
            ),
            quality_highlights=_project_quality_highlights(run),
            refresh_token=f"{run.updated_at.isoformat()}:{run.mission_id}:{run.state_version}",
        )

    async def list_evidence_projection_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 50,
    ) -> MissionEvidencePagePayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        records = await self.repository.list_items_by_types(
            mission_id=mission_id,
            item_types=("evidence",),
            after_seq=after_seq,
            limit=limit + 1,
        )
        page_records = records[:limit]
        return MissionEvidencePagePayload(
            items=[_project_evidence(record) for record in page_records],
            page=MissionProjectionPagePayload(
                total=run.evidence_count,
                returned=len(page_records),
                next_cursor=(page_records[-1].seq if len(records) > limit else None),
            ),
        )

    async def list_artifact_projection_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        after_review_item_id: str = "",
        limit: int = 50,
    ) -> MissionArtifactPagePayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        artifact_records = await self.repository.list_current_artifact_review_items(
            mission_id=mission_id,
            after_seq=after_seq,
            after_review_item_id=after_review_item_id,
            limit=limit + 1,
        )
        page_records = artifact_records[:limit]
        commit_records = await self.repository.list_commits_by_review_item_ids(
            mission_id=mission_id,
            review_item_ids=[
                str(record.review_item_id) for record in page_records
            ],
        )
        committed_review_ids = {
            str(record.review_item_id)
            for record in commit_records
            if record.status == "committed"
        }
        return MissionArtifactPagePayload(
            items=[
                _project_artifact(record, committed_review_ids)
                for record in page_records
            ],
            page=MissionProjectionPagePayload(
                total=await self.repository.count_current_artifact_review_items(
                    mission_id=mission_id
                ),
                returned=len(page_records),
                next_cursor=(
                    page_records[-1].source_item_seq
                    if len(artifact_records) > limit and page_records
                    else None
                ),
                next_tiebreaker=(
                    str(page_records[-1].review_item_id)
                    if len(artifact_records) > limit and page_records
                    else None
                ),
            ),
        )

    async def cleanup_expired_previews(
        self,
        command: MissionPreviewCleanupPayload,
    ) -> MissionPreviewCleanupResultPayload:
        mission_ids = await self.repository.list_mission_ids_with_expired_previews(
            now=command.now,
            limit=command.limit,
        )
        refs: list[str] = []
        review_item_ids: list[str] = []
        remaining = command.limit
        for mission_id in mission_ids:
            if remaining <= 0:
                break
            run = await self._locked_run(mission_id)
            records = await self.repository.list_expired_review_previews(
                mission_id=mission_id,
                now=command.now,
                limit=remaining,
                for_update=True,
            )
            commits = await self.repository.list_commits_by_review_item_ids(
                mission_id=mission_id,
                review_item_ids=[str(record.review_item_id) for record in records],
            )
            commits_by_review_item = {
                str(commit.review_item_id): commit for commit in commits
            }
            audit: list[MissionItemDraftPayload] = []
            changed = False
            for record in records:
                if remaining <= 0:
                    break
                expires_at = _aware(record.preview_expires_at)
                if (
                    expires_at is None
                    or expires_at > _aware(command.now)
                    or (record.preview_ref is None and not record.preview_json)
                ):
                    continue
                commit = commits_by_review_item.get(str(record.review_item_id))
                if _commit_holds_review_preview(commit):
                    continue
                remaining -= 1
                changed = True
                review_item_ids.append(str(record.review_item_id))
                if record.preview_ref:
                    refs.append(record.preview_ref)
                if record.status in {"pending", "accepted"}:
                    if record.status == "pending":
                        run.pending_review_count = max(
                            run.pending_review_count - 1,
                            0,
                        )
                    record.status = "superseded"
                    record.decision_json = {
                        "decision": "superseded",
                        "reason_code": "review_preview_expired",
                    }
                    record.decided_by = None
                    record.decided_at = command.now
                    audit.append(
                        MissionItemDraftPayload(
                            item_type="review_candidate_superseded",
                            operation_id=record.review_item_id,
                            phase="completed",
                            producer="preview_cleanup",
                            summary="Expired review preview was retired.",
                            payload_json={
                                "review_item_id": record.review_item_id,
                                "reason_code": "review_preview_expired",
                            },
                        )
                    )
                record.preview_json = {}
                record.preview_ref = None
                record.updated_at = command.now
            if changed:
                if audit:
                    self._append_drafts(run, audit, now=command.now)
                self._touch(run, command.now)
        await self._finish()
        return MissionPreviewCleanupResultPayload(
            review_item_ids=review_item_ids,
            preview_refs=refs,
        )


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _project_activity(run: MissionRunRecord) -> MissionActivityPayload:
    snapshot = run.snapshot_json or {}
    if run.status == MissionStatus.WAITING.value:
        reason = _text(snapshot.get("waiting_reason"))
        return MissionActivityPayload(
            state="reviewing" if reason == "review" else "waiting",
            title=("等待你确认结果" if reason == "review" else "等待你的回应"),
            summary=_attention_default_summary(reason or "user_input"),
        )
    if run.status == MissionStatus.COMPLETED.value:
        return MissionActivityPayload(state="completed", title="研究任务已完成")
    if run.status == MissionStatus.FAILED.value:
        if snapshot.get("failure_reason") == "model_service_unavailable":
            return MissionActivityPayload(
                state="unavailable",
                title="模型服务暂时不可用",
                summary="已保留完成阶段和待确认内容，稍后可在对话中继续。",
            )
        return MissionActivityPayload(
            state="stopped",
            title="研究任务未完整完成",
            summary="已保留当前进度和可用结果。",
        )
    if run.status == MissionStatus.CANCELLED.value:
        return MissionActivityPayload(state="stopped", title="研究任务已取消")

    guard = snapshot.get("loop_guard")
    loop_guard = guard if isinstance(guard, dict) else {}
    transient_attempt = int(loop_guard.get("transient_failures") or 0)
    next_actions = snapshot.get("next_actions")
    actions = next_actions if isinstance(next_actions, list) else []
    if transient_attempt > 0 and "retry_agent_step_after_backoff" in actions:
        return MissionActivityPayload(
            state="retrying",
            title="连接暂时波动，问津正在重试",
            summary="任务进度已经保留，无需重新开始。",
            attempt=transient_attempt,
            retry_at=run.next_wakeup_at,
        )
    if "replan_after_operation_failure" in actions:
        return MissionActivityPayload(
            state="recovering",
            title="当前步骤未完成，问津正在调整方案",
            summary="已保留可用结果，并会从当前阶段继续。",
        )
    if "repair_structured_decision" in actions or "retry_agent_step" in actions:
        return MissionActivityPayload(
            state="recovering",
            title="问津正在校正下一步",
            summary="任务进度已经保留，校正后会从当前阶段继续。",
        )
    if run.active_subagent_count > 0:
        return MissionActivityPayload(
            state="collaborating",
            title="研究成员正在协作",
            summary="已分派并行研究工作，结果会汇总回当前阶段。",
        )
    if run.status == MissionStatus.CREATED.value:
        return MissionActivityPayload(state="starting", title="正在准备研究任务")
    return MissionActivityPayload(
        state="working",
        title="问津正在推进当前研究",
    )


def _review_selection_revision(
    records: list[MissionReviewItemRecord],
    *,
    review_mode: str,
) -> str:
    selection = []
    for record in sorted(records, key=lambda item: item.review_item_id):
        policy = project_review_policy(
            review_mode=review_mode,
            target_kind=record.target_kind,
            target_room=record.target_room,
            target_ref=record.target_ref,
            risk_level=record.risk_level,
        )
        selection.append(
            {
                "batch_acceptable": policy.batch_acceptable,
                "requires_explicit_review": policy.requires_explicit_review,
                "review_item_id": record.review_item_id,
                "status": record.status,
                "suggested_selected": policy.suggested_selected,
            }
        )
    encoded = json.dumps(
        selection,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _project_review_view_item(
    record: MissionReviewItemRecord,
    *,
    review_mode: str,
    commit: MissionCommitRecord | None,
    now: datetime,
) -> MissionReviewViewItemPayload:
    item = mission_review_item_to_payload(record, review_mode=review_mode)
    commit_status = commit.status if commit is not None else None
    block_reason: str | None = None
    if record.status != "accepted":
        block_reason = (
            "already_committed"
            if record.status == "committed"
            else "review_item_not_accepted"
        )
    elif commit_status == "committed":
        block_reason = "already_committed"
    elif commit_status == "cancelled":
        block_reason = "commit_cancelled"
    elif (
        commit_status == "applying"
        and commit is not None
        and commit.attempt_expires_at is not None
        and _aware(commit.attempt_expires_at) > _aware(now)
    ):
        block_reason = "commit_in_progress"
    elif not record.preview_hash:
        block_reason = "review_preview_unavailable"
    elif (
        record.preview_expires_at is not None
        and _aware(record.preview_expires_at) <= _aware(now)
    ):
        block_reason = "review_preview_expired"
    error_json = dict(commit.error_json or {}) if commit is not None else {}
    targets_json = dict(commit.targets_json or {}) if commit is not None else {}
    return MissionReviewViewItemPayload.model_validate(
        {
            **item.model_dump(mode="python"),
            "commit_status": commit_status,
            "commit_eligible": block_reason is None,
            "commit_block_reason": block_reason,
            "commit_error_code": str(error_json.get("code") or "") or None,
            "committed_target_ref": (
                str(targets_json.get("target_ref"))
                if targets_json.get("target_ref") is not None
                else None
            ),
        }
    )


def _commit_holds_review_preview(commit: MissionCommitRecord | None) -> bool:
    return commit is not None and commit.status in {"pending", "applying", "failed"}


def _project_attention_request(
    run: MissionRunRecord,
) -> MissionAttentionRequestPayload | None:
    if run.status != MissionStatus.WAITING.value:
        return None
    pending = run.snapshot_json.get("pending_request")
    request = pending if isinstance(pending, dict) else {}
    reason = _text(run.snapshot_json.get("waiting_reason")) or "user_input"
    request_id = _text(request.get("request_id")) or f"waiting:{run.mission_id}:{run.state_version}"
    summary = _text(request.get("summary")) or _text(request.get("question")) or _text(request.get("prompt")) or _attention_default_summary(reason)

    inputs = _project_attention_inputs(reason, request)
    if reason == "permission":
        actions = [
            MissionAttentionActionPayload(
                action_id="allow-once",
                label="仅本次允许",
                action_type="permission_allow_once",
                primary=True,
            ),
            MissionAttentionActionPayload(
                action_id="allow-mission",
                label="本任务内允许",
                action_type="permission_allow_mission",
            ),
            MissionAttentionActionPayload(
                action_id="reject",
                label="不允许",
                action_type="permission_reject",
            ),
        ]
    else:
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
    inputs: list[MissionAttentionInputPayload] = [
        MissionAttentionInputPayload(
            input_id=f"input-{index + 1}",
            label=label,
            input_type="file" if reason == "external_data" else "text",
        )
        for index, label in enumerate(labels)
        if label
    ]
    required_assets = request.get("required_assets")
    asset_labels = (
        [_text(value) for value in required_assets]
        if isinstance(required_assets, list)
        else []
    )
    inputs.extend(
        MissionAttentionInputPayload(
            input_id=f"asset-{index + 1}",
            label=label,
            input_type="file",
        )
        for index, label in enumerate(asset_labels)
        if label
    )
    minimum_schema = _text(request.get("minimum_schema"))
    if minimum_schema:
        inputs.append(
            MissionAttentionInputPayload(
                input_id="field-schema",
                label="字段与单位说明",
                description=minimum_schema,
                input_type="text",
            )
        )
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
        item_counts=(
            run.snapshot_json.get("stage_item_counts")
            if isinstance(run.snapshot_json.get("stage_item_counts"), dict)
            else {}
        ),
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
    item_counts: dict[str, object] | None = None,
) -> list[str]:
    family_contracts = {family_id: contract for family_id in required_families if (contract := next((item for item in contracts if item.stage_id == family_id), None)) is not None and contract.instantiation.mode == "per_item"}
    family_order = {family_id: index for index, family_id in enumerate(required_families)}
    dynamic_instances: list[tuple[int, int, str]] = []
    dynamic_ids_seen: set[str] = set()
    families_with_instances: set[str] = set()
    counts = item_counts or {}
    for family_id, contract in family_contracts.items():
        source_key = contract.instantiation.source_context_key or ""
        raw_count = counts.get(source_key)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            continue
        if not 1 <= raw_count <= 100:
            continue
        for index in range(1, raw_count + 1):
            stage_id = format_stage_instance_id(
                contract.instantiation.instance_id_template,
                index,
            )
            dynamic_instances.append((index, family_order[family_id], stage_id))
            dynamic_ids_seen.add(stage_id)
        families_with_instances.add(family_id)
    for stage_id in dict.fromkeys(observed_ids):
        for family_id, contract in family_contracts.items():
            if not stage_id_matches_contract(contract, stage_id):
                continue
            index = stage_instance_index(contract.instantiation.instance_id_template, stage_id)
            if index is not None:
                if stage_id not in dynamic_ids_seen:
                    dynamic_instances.append((index, family_order[family_id], stage_id))
                    dynamic_ids_seen.add(stage_id)
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
                *(candidate for candidate in required_families if candidate in family_contracts and candidate not in families_with_instances),
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
        raw_status = _text(row.get("status")) or "working"
        status = {
            "pending": "queued",
            "queued": "queued",
            "running": "working",
            "working": "working",
            "completed": "done",
            "done": "done",
            "needs_input": "needs_input",
            "failed": "failed",
            "cancelled": "cancelled",
        }.get(raw_status, "working")
        projected.append(
            MissionSubagentSummaryPayload(
                subagent_id=_text(row.get("job_id")) or f"member-{index + 1}",
                display_name=_text(row.get("display_name")) or f"研究成员 {index + 1}",
                role_label=_public_subagent_role(row.get("role_label")),
                status=status,
                summary=_text(row.get("result_brief")),
            )
        )
    return team_summary, projected


def _public_subagent_role(value: object) -> str:
    label = _text(value)
    if not label:
        return "研究协作"
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", label):
        normalized = label.lower()
        if "audit" in normalized or "critic" in normalized:
            return "专项核验"
        return "专项研究"
    return label


def _project_evidence(record: MissionItemRecord) -> MissionEvidenceSummaryPayload:
    payload = record.payload_json or {}
    raw_metadata = payload.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    return MissionEvidenceSummaryPayload(
        item_id=record.id,
        seq=record.seq,
        title=_text(payload.get("title")) or record.summary or "研究证据",
        source_type=_text(payload.get("source_type")),
        source_label=(_text(payload.get("source_label")) or _text(payload.get("source")) or _text(metadata.get("publisher"))),
        summary=_text(payload.get("summary")) or record.summary,
        citation=_text(payload.get("citation")) or _text(payload.get("uri")),
        verified=payload.get("verified") is True,
    )


def _project_artifact(
    record: MissionReviewItemRecord,
    committed_review_ids: set[str],
) -> MissionArtifactSummaryPayload:
    preview = record.preview_json or {}
    return MissionArtifactSummaryPayload(
        item_id=record.review_item_id,
        seq=record.source_item_seq or 0,
        title=record.title,
        kind=_text(preview.get("artifact_kind")) or record.target_kind,
        summary=record.summary,
        preview_available=bool(record.preview_ref or preview),
        committed=record.status == "committed" or record.review_item_id in committed_review_ids,
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


def _review_materialization_destination(
    *,
    target_kind: str,
    target_room: str | None,
    target_ref: str | None,
    preview_json: dict,
) -> tuple[str, ...] | None:
    """Identify a protected write destination independently of model-chosen output keys."""

    if target_ref:
        return ("existing", target_kind, target_room or "", target_ref)
    descriptor = preview_json.get("materialization")
    if not isinstance(descriptor, dict):
        return None
    operation = descriptor.get("operation")
    payload = descriptor.get("payload")
    if operation != "documents.upsert_prism_file" or not isinstance(payload, dict):
        return None
    path = payload.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    return ("new", target_kind, target_room or "", operation, path.strip())


__all__ = [
    "MissionProjectionStaleError",
    "MissionStore",
    "TERMINAL_MISSION_STATUSES",
]

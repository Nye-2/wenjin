"""Shared transaction kernel and pure projections for Mission persistence."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.policies import calculate_model_usage_credits
from src.contracts.archive_filename import recover_legacy_zip_filename
from src.contracts.mission_budget import (
    execution_budget_from_runtime_context,
    resource_delta_for_item,
    resource_usage_from_snapshot,
    snapshot_with_resource_usage,
    unavailable_budget_dimensions,
)
from src.contracts.model_usage import ModelCallState
from src.contracts.pricing_snapshot import MissionPricingSnapshot
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
    mission_review_item_to_payload,
)
from src.dataservice.domains.mission.repository import (
    ArtifactProjectionRevisionRow,
    MissionRepository,
)
from src.dataservice.domains.pricing.contracts import (
    GlobalCreditPolicyConfig,
    MissionPricingPolicyConfig,
    ModelUsagePolicyConfig,
)
from src.dataservice_client.contracts.mission import (
    MissionActivityPayload,
    MissionArtifactSummaryPayload,
    MissionAttentionActionPayload,
    MissionAttentionInputPayload,
    MissionAttentionRequestPayload,
    MissionCreatePayload,
    MissionCurrentOperationPayload,
    MissionEvidenceSummaryPayload,
    MissionFailurePayload,
    MissionInputSummaryPayload,
    MissionItemDraftPayload,
    MissionOperationReceiptPayload,
    MissionReviewViewItemPayload,
    MissionRunPatchPayload,
    MissionStageSummaryPayload,
    MissionStatus,
    MissionSubagentMilestonePayload,
    MissionSubagentSummaryPayload,
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
        and dict(run.snapshot_json or {})
        == snapshot_with_resource_usage(
            command.snapshot_json,
            resource_usage_from_snapshot(command.snapshot_json),
        )
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

class _MissionStoreCore:
    """Locks, invariants, accounting, and mutation primitives shared by Mission surfaces."""

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

        await self.session.flush()
        mission_ids = tuple(self._terminalized_mission_ids)
        self._terminalized_mission_ids.clear()
        credits = DataServiceCreditService(self.session, autocommit=False)
        for mission_id in mission_ids:
            run = await self._locked_run(mission_id)
            model_calls = await self._model_call_states(run)
            open_model_call_ids = [
                str(model_call.started.operation_id)
                for model_call in model_calls
                if model_call.state is ModelCallState.OPEN
            ]
            if open_model_call_ids:
                raise DataServiceConflictError(
                    "Terminal Mission settlement requires every model call to close",
                    detail={
                        "mission_id": mission_id,
                        "model_call_ids": open_model_call_ids,
                    },
                )
            unresolved_model_call_ids = [
                str(model_call.started.operation_id)
                for model_call in model_calls
                if model_call.state is ModelCallState.UNRESOLVED
            ]
            billing = dict((run.snapshot_json or {}).get("billing") or {})
            reservation = await credits.repository.get_mission_reservation_for_update(
                mission_id
            )
            if unresolved_model_call_ids:
                billing.update(
                    {
                        "state": "reconciliation_required",
                        "unresolved_model_call_ids": unresolved_model_call_ids,
                    }
                )
                if reservation is not None:
                    reservation.expires_at = None
                    reservation.metadata_json = {
                        **dict(reservation.metadata_json or {}),
                        "reconciliation_required": True,
                        "unresolved_model_call_ids": unresolved_model_call_ids,
                    }
                    billing["reservation_id"] = str(reservation.id)
                snapshot = dict(run.snapshot_json or {})
                snapshot["billing"] = billing
                run.snapshot_json = validate_mission_snapshot(snapshot)
                operation_id = f"model-usage-reconciliation:{mission_id}"
                audit_payload = {
                    "status": run.status,
                    "reservation_id": (
                        str(reservation.id) if reservation is not None else None
                    ),
                    "unresolved_model_call_ids": unresolved_model_call_ids,
                }
                existing = await self.repository.find_item_by_operation(
                    mission_id=mission_id,
                    operation_id=operation_id,
                    item_type="billing_reconciliation_required",
                )
                if existing is not None:
                    if dict(existing.payload_json or {}) != audit_payload:
                        raise DataServiceConflictError(
                            "Mission billing reconciliation audit is divergent",
                            detail={"mission_id": mission_id},
                        )
                    continue
                now = await self.repository.database_now()
                self._append_drafts(
                    run,
                    [
                        MissionItemDraftPayload(
                            item_type="billing_reconciliation_required",
                            operation_id=operation_id,
                            phase="failed",
                            producer="mission_store",
                            summary=(
                                "Mission billing requires model usage reconciliation"
                            ),
                            payload_json=audit_payload,
                        )
                    ],
                    now=now,
                )
                self._touch(run, now)
                continue
            usage_summary: dict[str, Any] = {}
            if reservation is None:
                billing["state"] = "settled"
                billing["free_policy"] = True
                billing["settled_credits"] = 0
            else:
                settled_credits, usage_summary = self._calculate_settlement(
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

    @staticmethod
    def _calculate_settlement(
        run: MissionRunRecord,
        reservation: Any,
    ) -> tuple[int, dict[str, Any]]:
        resource_usage = resource_usage_from_snapshot(dict(run.snapshot_json or {}))
        usage = resource_usage.token_usage()
        if usage["total_tokens"] <= 0:
            return 0, usage

        try:
            pricing_snapshot = MissionPricingSnapshot.model_validate(
                dict(reservation.metadata_json or {})["pricing_snapshot"]
            )
            model_policy = ModelUsagePolicyConfig.model_validate(
                pricing_snapshot.model_policy.config
            )
            global_policy = (
                GlobalCreditPolicyConfig.model_validate(
                    pricing_snapshot.global_policy.config
                )
                if pricing_snapshot.global_policy is not None
                else None
            )
            mission_policy = MissionPricingPolicyConfig.model_validate(
                pricing_snapshot.mission_policy.config
            )
        except (KeyError, ValueError) as exc:
            raise DataServiceValidationError(
                "Mission reservation has no valid pricing snapshot",
                detail={"mission_id": run.mission_id},
            ) from exc
        charge = calculate_model_usage_credits(
            model_policy=model_policy.model_dump(mode="python"),
            global_policy=(
                global_policy.model_dump(mode="python")
                if global_policy is not None
                else None
            ),
            token_usage=usage,
            surface="mission",
        )
        credits = charge.credits_to_charge
        if run.status == MissionStatus.COMPLETED.value:
            credits = max(credits, mission_policy.base_fee_credits)
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
            raise _MissionStoreCore._version_conflict(run, expected)

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
        _MissionStoreCore._require_nonterminal(run)
        _MissionStoreCore._require_state_version(run, expected_state_version)
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

    @staticmethod
    def _prepare_snapshot_replacement(
        run: MissionRunRecord,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate agent-owned state against the current resource projection."""
        try:
            current_usage = resource_usage_from_snapshot(
                dict(run.snapshot_json or {})
            )
            if "resource_usage" in snapshot:
                supplied_usage = resource_usage_from_snapshot(snapshot)
                if supplied_usage != current_usage:
                    raise DataServiceValidationError(
                        "Mission resource_usage is DataService-owned",
                        detail={"mission_id": run.mission_id},
                    )
        except ValueError as exc:
            raise DataServiceValidationError(
                "Mission resource accounting contract is invalid",
                detail={"mission_id": run.mission_id, "reason": str(exc)},
            ) from exc
        return validate_mission_snapshot(
            snapshot_with_resource_usage(snapshot, current_usage)
        )

    @staticmethod
    def _install_prepared_snapshot(
        run: MissionRunRecord,
        snapshot: dict[str, Any],
    ) -> None:
        """Install prepared agent state while retaining newly projected usage."""
        current_usage = resource_usage_from_snapshot(dict(run.snapshot_json or {}))
        run.snapshot_json = validate_mission_snapshot(
            snapshot_with_resource_usage(snapshot, current_usage)
        )

    def _append_drafts(
        self,
        run: MissionRunRecord,
        drafts: list[MissionItemDraftPayload],
        *,
        now: datetime,
        execution_ledger_validated: bool = False,
    ) -> list[MissionItemRecord]:
        if not execution_ledger_validated and any(
            draft.item_type
            in {
                "model_call_started",
                "usage_receipt",
                "model_call_terminal",
                "subagent_progress",
            }
            for draft in drafts
        ):
            raise DataServiceValidationError(
                "Mission execution ledger items require the atomic append path",
                detail={"mission_id": run.mission_id},
            )
        try:
            budget = execution_budget_from_runtime_context(
                dict(run.runtime_context_json or {})
            )
            usage = resource_usage_from_snapshot(dict(run.snapshot_json or {}))
        except ValueError as exc:
            raise DataServiceValidationError(
                "Mission resource accounting contract is invalid",
                detail={"mission_id": run.mission_id, "reason": str(exc)},
            ) from exc
        projected_usage = usage
        for draft in drafts:
            current_usage = projected_usage
            delta = resource_delta_for_item(
                item_type=draft.item_type,
                payload_json=draft.payload_json,
            )
            next_usage = current_usage.add(delta)
            # Usage receipts describe work that has already happened. Persist the
            # exact receipt, then stop before the next dispatch if it crossed the
            # token threshold. Non-dispatch audit and terminal items must remain
            # writable after exhaustion so the Mission can stop durably.
            if draft.item_type == "model_call_started":
                pre_dispatch_exceeded = unavailable_budget_dimensions(
                    current_usage,
                    budget,
                    model_calls=1,
                )
            elif draft.item_type == "operation_claim":
                pre_dispatch_exceeded = unavailable_budget_dimensions(
                    current_usage,
                    budget,
                    tool_operations=1,
                )
            elif draft.item_type == "subagent_spawned":
                pre_dispatch_exceeded = unavailable_budget_dimensions(
                    current_usage,
                    budget,
                    model_calls=delta.subagent_jobs,
                    subagent_jobs=delta.subagent_jobs,
                )
            else:
                pre_dispatch_exceeded = ()
            if pre_dispatch_exceeded:
                raise DataServiceValidationError(
                    "Mission execution budget is exhausted",
                    detail={
                        "mission_id": run.mission_id,
                        "dimensions": list(pre_dispatch_exceeded),
                        "usage": current_usage.model_dump(mode="json"),
                        "budget": budget.model_dump(mode="json"),
                    },
                )
            projected_usage = next_usage

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
        run.snapshot_json = validate_mission_snapshot(
            snapshot_with_resource_usage(
                dict(run.snapshot_json or {}),
                projected_usage,
            )
        )
        return records

def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None

def _project_activity(
    run: MissionRunRecord,
    *,
    last_progress_at: datetime | None = None,
) -> MissionActivityPayload:
    snapshot = run.snapshot_json or {}
    if run.status == MissionStatus.WAITING.value:
        reason = _text(snapshot.get("waiting_reason"))
        return MissionActivityPayload(
            state="reviewing" if reason == "review" else "waiting",
            title=("等待你确认结果" if reason == "review" else "等待你的回应"),
            summary=_attention_default_summary(reason or "user_input"),
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if run.status == MissionStatus.COMPLETED.value:
        return MissionActivityPayload(
            state="completed",
            title="研究任务已完成",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if run.status == MissionStatus.FAILED.value:
        if snapshot.get("failure_reason") == "model_service_unavailable":
            return MissionActivityPayload(
                state="unavailable",
                title="模型服务暂时不可用",
                summary="已保留完成阶段和待确认内容，稍后可在对话中继续。",
                last_progress_at=last_progress_at,
                heartbeat_at=run.updated_at,
            )
        return MissionActivityPayload(
            state="stopped",
            title="研究任务未完整完成",
            summary="已保留当前进度和可用结果。",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if run.status == MissionStatus.CANCELLED.value:
        return MissionActivityPayload(
            state="stopped",
            title="研究任务已取消",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )

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
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if "replan_after_operation_failure" in actions:
        return MissionActivityPayload(
            state="recovering",
            title="当前步骤未完成，问津正在调整方案",
            summary="已保留可用结果，并会从当前阶段继续。",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if "repair_structured_decision" in actions or "retry_agent_step" in actions:
        return MissionActivityPayload(
            state="recovering",
            title="问津正在校正下一步",
            summary="任务进度已经保留，校正后会从当前阶段继续。",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if run.active_subagent_count > 0:
        return MissionActivityPayload(
            state="collaborating",
            title="研究成员正在协作",
            summary="已分派并行研究工作，结果会汇总回当前阶段。",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    if run.status == MissionStatus.CREATED.value:
        return MissionActivityPayload(
            state="starting",
            title="正在准备研究任务",
            last_progress_at=last_progress_at,
            heartbeat_at=run.updated_at,
        )
    return MissionActivityPayload(
        state="working",
        title="问津正在推进当前研究",
        last_progress_at=last_progress_at,
        heartbeat_at=run.updated_at,
    )


def _project_input_summary(run: MissionRunRecord) -> MissionInputSummaryPayload:
    raw_inputs = (run.snapshot_json or {}).get("mission_inputs")
    manifests = [item for item in raw_inputs if isinstance(item, dict)] if isinstance(raw_inputs, list) else []
    names = []
    for item in manifests:
        recovered = recover_legacy_zip_filename(
            str(item.get("member_path") or item.get("filename") or "未命名材料")
        )
        # Archive member paths are useful to the extractor, but the compact
        # Mission inventory should show the material's own name rather than
        # repeated archive/folder prefixes such as ``A题/A题/附件1.xlsx``.
        names.append(recovered.replace("\\", "/").rsplit("/", maxsplit=1)[-1])
    return MissionInputSummaryPayload(
        total=len(manifests),
        ready=len(manifests),
        failed=0,
        names=names,
    )


def _project_current_operation(
    run: MissionRunRecord,
    records: list[MissionItemRecord],
) -> MissionCurrentOperationPayload | None:
    snapshot = run.snapshot_json or {}
    inflight = snapshot.get("inflight_operation")
    by_seq = {record.seq: record for record in records}
    if isinstance(inflight, dict):
        kind = str(inflight.get("kind") or "")
        public_kind = kind if kind in {"tool", "subagent", "quality", "review"} else "planning"
        started = by_seq.get(int(inflight.get("call_item_seq") or 0))
        labels = {
            "tool": "正在运行研究工具",
            "subagent": "研究成员正在处理分派任务",
            "quality": "正在检查当前阶段质量",
            "review": "正在整理待确认成果",
            "planning": "正在规划下一步",
        }
        return MissionCurrentOperationPayload(
            kind=public_kind,
            label=(started.summary if started is not None and started.summary else labels[public_kind]),
            actor="研究成员" if public_kind == "subagent" else "问津",
            started_at=(started.created_at if started is not None else run.updated_at),
            attempt=max(int((snapshot.get("loop_guard") or {}).get("transient_failures") or 0), 1),
        )
    terminal_call_ids = {
        record.operation_id
        for record in records
        if record.item_type in {"usage_receipt", "model_call_terminal"}
        and record.operation_id
    }
    open_calls = [
        record
        for record in records
        if record.item_type == "model_call_started"
        and record.operation_id
        and record.operation_id not in terminal_call_ids
    ]
    if open_calls:
        started = open_calls[-1]
        is_subagent = bool((started.payload_json or {}).get("job_id"))
        return MissionCurrentOperationPayload(
            kind="model",
            label=("研究成员正在分析材料" if is_subagent else "问津正在分析并规划下一步"),
            actor=("研究成员" if is_subagent else "问津"),
            started_at=started.created_at,
        )
    return None


def _project_failure(
    run: MissionRunRecord,
    *,
    passed_stages: int,
    visible_artifact_count: int,
) -> MissionFailurePayload | None:
    if run.status != MissionStatus.FAILED.value:
        return None
    reason = str((run.snapshot_json or {}).get("failure_reason") or "repeated_failure")
    category = "runtime"
    recoverability = "continue_in_chat"
    summary = "任务在当前步骤未能继续，但此前已完成的内容仍然保留。"
    action = "可从已保存进度继续，让问津调整方案后完成剩余部分。"
    if reason == "model_service_unavailable":
        category = "model_service"
        recoverability = "retry_later"
        summary = "模型服务连续未响应，任务已在安全边界停止。"
        action = "稍后从已保存进度继续，无需重新上传材料。"
    elif reason == "model_usage_reconciliation_required":
        category = "usage_reconciliation"
        summary = "一次模型调用的用量状态无法确认，系统为避免重复计费已安全停止。"
        action = "从已保存进度继续；若再次出现，请检查模型服务和账务日志。"
    elif reason == "resource_budget_exhausted":
        category = "resource_budget"
        recoverability = "adjust_scope"
        summary = "本次任务已达到预设的运行资源上限。"
        action = "缩小目标或提高任务预算后，从已保存进度继续。"
    elif reason == "stage_execution_failure_budget_exhausted":
        category = "stage_execution"
        summary = "当前阶段多次尝试仍未满足完成条件，系统已停止重复执行。"
        action = "补充约束或调整任务要求后，从已保存进度继续。"
    preserved = (
        f"已保留 {passed_stages} 个已通过阶段、{run.evidence_count} 条来源与结果、"
        f"{visible_artifact_count} 个成果。"
    )
    return MissionFailurePayload(
        category=category,
        user_summary=summary,
        recoverability=recoverability,
        preserved_progress=preserved,
        recommended_action=action,
        failed_at=run.completed_at or run.updated_at,
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
    projected_item = item.model_dump(mode="python")
    if (
        record.preview_expires_at is not None
        and _aware(record.preview_expires_at) <= _aware(now)
    ):
        projected_item["preview_ref"] = None
    return MissionReviewViewItemPayload.model_validate(
        {
            **projected_item,
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
        "external_data": "收到材料前，相关查证与后续写作会暂停。",
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
    records: list[MissionItemRecord],
) -> tuple[str | None, list[MissionSubagentSummaryPayload]]:
    latest_operation_id = next(
        (
            record.operation_id
            for record in reversed(records)
            if record.item_type == "subagent_progress" and record.operation_id
        ),
        None,
    )
    progress_by_job: dict[str, MissionItemRecord] = {}
    public_summary_by_job: dict[str, str] = {}
    milestones_by_job: dict[str, list[MissionSubagentMilestonePayload]] = {}
    for record in records:
        if (
            record.item_type != "subagent_progress"
            or record.operation_id != latest_operation_id
        ):
            continue
        payload = dict(record.payload_json or {})
        job_id = _text(payload.get("job_id"))
        if not job_id:
            continue
        progress_by_job[job_id] = record
        public_summary = _text(payload.get("public_summary"))
        if public_summary:
            public_summary_by_job[job_id] = public_summary
        milestone_kind = _public_subagent_milestone_kind(payload)
        if public_summary and milestone_kind is not None:
            milestones_by_job.setdefault(job_id, []).append(
                MissionSubagentMilestonePayload(
                    kind=milestone_kind,
                    summary=_public_subagent_summary(public_summary)
                    or "研究成员已更新可查看进展。",
                    created_at=record.created_at,
                )
            )

    projected: list[MissionSubagentSummaryPayload] = []
    for index, (job_id, record) in enumerate(progress_by_job.items()):
        row = dict(record.payload_json or {})
        lifecycle_phase = _text(row.get("lifecycle_phase")) or "progress"
        raw_status = _text(row.get("status"))
        if lifecycle_phase != "terminal":
            raw_status = "working"
        elif not raw_status:
            raw_status = "completed" if record.phase == "completed" else "failed"
        if lifecycle_phase != "terminal" and run.status == "cancelled":
            raw_status = "cancelled"
        elif lifecycle_phase != "terminal" and run.status in {"completed", "failed"}:
            raw_status = "failed"
        status = {
            "pending": "queued",
            "queued": "queued",
            "running": "working",
            "working": "working",
            "completed": "done",
            "done": "done",
            "needs_input": "needs_input",
            "failed": "failed",
            "timed_out": "failed",
            "cancelled": "cancelled",
        }.get(raw_status, "working")
        projected.append(
            MissionSubagentSummaryPayload(
                subagent_id=job_id or f"member-{index + 1}",
                display_name=_text(row.get("display_name")) or f"研究成员 {index + 1}",
                role_label=_public_subagent_role(row.get("role_label")),
                status=status,
                summary=_public_subagent_summary(public_summary_by_job.get(job_id)),
                milestones=milestones_by_job.get(job_id, [])[-6:],
            )
        )
    return _subagent_team_summary(projected), projected


def _public_subagent_milestone_kind(
    payload: dict[str, Any],
) -> Literal["finding", "formula", "file", "figure", "checkpoint"] | None:
    if payload.get("status") == "milestone":
        value = _text(payload.get("progress_kind")) or "checkpoint"
        if value in {"finding", "formula", "file", "figure", "checkpoint"}:
            return value
        return "checkpoint"
    artifact_refs = payload.get("artifact_refs")
    if payload.get("status") == "completed" and isinstance(artifact_refs, list) and artifact_refs:
        return "file"
    return None


def _subagent_team_summary(
    members: list[MissionSubagentSummaryPayload],
) -> str | None:
    if not members:
        return None
    working = sum(member.status in {"queued", "working"} for member in members)
    milestones = sum(len(member.milestones) for member in members)
    if working:
        progress = f"，已有 {milestones} 条可查看进展" if milestones else ""
        return f"{working} 位研究成员正在推进{progress}。"
    done = sum(member.status == "done" for member in members)
    unfinished = len(members) - done
    if unfinished:
        return f"{len(members)} 位研究成员中 {done} 位已完成，{unfinished} 位保留了当前进度。"
    return f"{done} 位研究成员均已完成本轮协作。"


def _public_subagent_summary(value: object) -> str | None:
    summary = _text(value)
    if not summary:
        return None
    known_runtime_messages = {
        "Subagent exhausted its model-turn budget": "达到本轮分析步数上限，已保留可用进度。",
        "Subagent exhausted its tool-step budget": "达到本轮工具调用上限，已保留可用进度。",
        "Subagent exhausted its retries for structured model output": "结构化结果多次未通过校验，已保留可用进度。",
        "Subagent model step failed": "模型分析步骤未完成，已保留此前进度。",
    }
    known = known_runtime_messages.get(summary)
    if known is not None:
        return known
    if not re.search(r"[\u3400-\u9fff]", summary):
        return "研究成员已更新本轮进度。"
    return summary[:500]


def _public_subagent_role(value: object) -> str:
    label = _text(value)
    if not label:
        return "研究协作"
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", label):
        normalized = label.lower()
        if "audit" in normalized or "critic" in normalized:
            return "专项查证"
        return "专项研究"
    return label

def _project_evidence(record: MissionItemRecord) -> MissionEvidenceSummaryPayload:
    payload = record.payload_json or {}
    raw_metadata = payload.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    return MissionEvidenceSummaryPayload(
        item_id=record.id,
        seq=record.seq,
        title=_text(payload.get("title")) or record.summary or "研究来源",
        source_type=_text(payload.get("source_type")),
        source_label=(_text(payload.get("source_label")) or _text(payload.get("source")) or _text(metadata.get("publisher"))),
        summary=_text(payload.get("summary")) or record.summary,
        citation=_text(payload.get("citation")) or _text(payload.get("uri")),
        verified=payload.get("verified") is True,
    )

def _project_artifact(
    record: MissionReviewItemRecord,
    committed_review_ids: set[str],
    *,
    now: datetime,
) -> MissionArtifactSummaryPayload:
    preview = record.preview_json or {}
    materialization = preview.get("materialization")
    operation = (
        str(materialization.get("operation") or "")
        if isinstance(materialization, dict)
        else ""
    )
    committed = record.status == "committed" or record.review_item_id in committed_review_ids
    return MissionArtifactSummaryPayload(
        item_id=record.review_item_id,
        seq=record.source_item_seq or 0,
        title=record.title,
        kind=_text(preview.get("artifact_kind")) or record.target_kind,
        summary=record.summary,
        preview_available=bool(
            record.preview_ref
            and record.preview_expires_at is not None
            and _aware(record.preview_expires_at) > _aware(now)
        ),
        preview_expires_at=(
            record.preview_expires_at if record.preview_ref else None
        ),
        committed=committed,
        download_available=committed and operation == "assets.create_from_preview",
    )


def _artifact_projection_revision(
    rows: list[ArtifactProjectionRevisionRow],
) -> str:
    """Hash only the ordered values that can change the public artifact surface."""

    projection = []
    for row in rows:
        committed = (
            row.review_status == "committed" or row.commit_status == "committed"
        )
        projection.append(
            {
                "committed": committed,
                "download_available": committed
                and row.materialization_operation == "assets.create_from_preview",
                "item_id": row.review_item_id,
                "kind": row.artifact_kind or row.target_kind,
                "preview_expires_at": (
                    _aware(row.preview_expires_at).isoformat()
                    if row.preview_expires_at is not None
                    else None
                ),
                "preview_ref": row.preview_ref,
                "seq": row.source_item_seq,
                "summary": row.summary,
                "title": row.title,
            }
        )
    encoded = json.dumps(
        projection,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    '_MissionStoreCore',
    'TERMINAL_MISSION_STATUSES',
    'NONTERMINAL_MISSION_STATUSES',
    '_HISTORY_CURSOR_VERSION',
    '_MISSION_RECORD_CURSOR_VERSION',
    '_MISSION_VIEW_READ_ATTEMPTS',
    '_encode_history_cursor',
    '_decode_history_cursor',
    '_encode_record_cursor',
    '_decode_record_cursor',
    'MissionProjectionStaleError',
    '_create_request_matches',
    '_ALLOWED_STATUS_TRANSITIONS',
    '_REVIEW_TRANSITIONS',
    '_aware',
    '_operation_receipt_from_items',
    '_text',
    '_project_activity',
    '_review_selection_revision',
    '_project_review_view_item',
    '_commit_holds_review_preview',
    '_project_attention_request',
    '_project_attention_inputs',
    '_attention_title',
    '_attention_default_summary',
    '_attention_impact',
    '_project_stages',
    '_stage_contracts',
    '_project_stage_instance_ids',
    '_stage_projection_title',
    '_project_subagents',
    '_public_subagent_role',
    '_project_evidence',
    '_project_artifact',
    '_project_quality_highlights',
    '_canonical_preview',
    '_review_materialization_destination',
]

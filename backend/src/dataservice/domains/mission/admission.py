"""Atomic Mission creation and credit-reservation admission."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.policies import calculate_mission_estimate
from src.contracts.pricing_snapshot import (
    MissionPricingSnapshot,
    freeze_pricing_policy,
)
from src.database.models.credit_reservation import CreditReservationStatus
from src.dataservice.common.errors import (
    CreditOverdraftLimitError,
    DataServiceConflictError,
    DataServiceNotFoundError,
    DataServiceValidationError,
)
from src.dataservice.domains.credit.service import DataServiceCreditService
from src.dataservice.domains.pricing.contracts import (
    GlobalCreditPolicyConfig,
    MissionPricingPolicyConfig,
    ModelUsagePolicyConfig,
)
from src.dataservice.domains.pricing.resolver import CanonicalPricingResolver
from src.dataservice_client.contracts.mission import (
    MissionAppendResultPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionItemDraftPayload,
    MissionItemPhase,
    MissionPausePayload,
    MissionReservationReconcilePayload,
    MissionReservationReconcileResultPayload,
    MissionResumePayload,
    MissionStatus,
)

from .service import MissionStore


class MissionAdmissionService:
    """Create a Mission and resolve its financial admission in one UOW."""

    def __init__(self, session: AsyncSession) -> None:
        self._store = MissionStore(session, autocommit=False)
        self._credits = DataServiceCreditService(session, autocommit=False)
        self._pricing = CanonicalPricingResolver(session)

    async def admit(
        self,
        command: MissionCreatePayload,
    ) -> MissionCreateResultPayload:
        created = await self._store.create_run(command)
        if not created.created:
            return created

        policy = await self._pricing.resolve_mission(
            workspace_type=command.workspace_type,
            mission_policy_id=command.mission_policy_id,
        )
        mission_config = MissionPricingPolicyConfig.model_validate(
            policy.config_json or {}
        )
        model_policy = await self._pricing.resolve_model_usage(command.model_id)
        model_config = ModelUsagePolicyConfig.model_validate(
            model_policy.config_json or {}
        )
        global_policy = await self._pricing.resolve_global_credit()
        global_config = (
            GlobalCreditPolicyConfig.model_validate(
                global_policy.config_json or {}
            )
            if global_policy is not None
            else None
        )
        pricing_snapshot = MissionPricingSnapshot(
            mission_policy=freeze_pricing_policy(
                policy,
                config=mission_config,
            ),
            model_policy=freeze_pricing_policy(
                model_policy,
                config=model_config,
            ),
            global_policy=(
                freeze_pricing_policy(global_policy, config=global_config)
                if global_policy is not None and global_config is not None
                else None
            ),
        )
        pinned_pricing = pricing_snapshot.model_dump(mode="json")
        estimate = calculate_mission_estimate(
            mission_config
        ).max_charge_credits
        now = await self._store.repository.database_now()
        ttl_seconds = mission_config.reservation_ttl_seconds
        expires_at = now + timedelta(seconds=ttl_seconds)
        snapshot = dict(created.mission.snapshot_json)
        billing_base: dict[str, Any] = {
            "pricing_policy_id": str(policy.id),
            "pricing_policy_key": str(policy.policy_key),
            "estimated_credits": estimate,
            "reservation_ttl_seconds": ttl_seconds,
        }

        if estimate <= 0:
            snapshot["billing"] = {
                **billing_base,
                "state": "ready",
                "free_policy": True,
            }
            status = MissionStatus.PLANNING
            summary = "Mission admitted under the active free pricing policy"
            payload = {
                **billing_base,
                "free_policy": True,
                "pricing_snapshot": pinned_pricing,
            }
        else:
            try:
                reservation = await self._credits.create_reservation(
                    user_id=command.user_id,
                    reserved_credits=estimate,
                    idempotency_key=f"mission:{created.mission.mission_id}",
                    workspace_id=command.workspace_id,
                    mission_id=created.mission.mission_id,
                    expires_at=expires_at,
                    metadata={
                        "mission_policy_id": command.mission_policy_id,
                        "model_id": command.model_id,
                        "pricing_policy_id": str(policy.id),
                        "pricing_snapshot": pinned_pricing,
                    },
                )
            except CreditOverdraftLimitError:
                request_id = f"billing:{created.mission.mission_id}"
                snapshot.update(
                    {
                        "billing": {
                            **billing_base,
                            "state": "waiting",
                            "free_policy": False,
                        },
                        "waiting_reason": "budget",
                        "pending_request": {
                            "request_id": request_id,
                            "request_type": "budget_confirmation",
                            "required_credits": estimate,
                            "summary": "当前可用额度不足，补足额度后即可继续任务。",
                        },
                        "next_actions": None,
                    }
                )
                status = MissionStatus.WAITING
                summary = "Mission is waiting for sufficient credits"
                payload = {
                    **billing_base,
                    "request_id": request_id,
                    "pricing_snapshot": pinned_pricing,
                }
            else:
                snapshot["billing"] = {
                    **billing_base,
                    "state": "ready",
                    "free_policy": False,
                    "reservation_id": str(reservation.id),
                    "expires_at": expires_at.isoformat(),
                }
                status = MissionStatus.PLANNING
                summary = "Mission credits reserved"
                payload = {
                    **billing_base,
                    "reservation_id": str(reservation.id),
                    "expires_at": expires_at.isoformat(),
                    "pricing_snapshot": pinned_pricing,
                }

        admitted = await self._store.apply_initial_admission(
            created.mission.mission_id,
            status=status,
            snapshot_json=snapshot,
            item=MissionItemDraftPayload(
                item_type="mission_admitted",
                phase=MissionItemPhase.COMPLETED,
                producer="mission_admission",
                summary=summary,
                payload_json=payload,
            ),
        )
        return MissionCreateResultPayload(mission=admitted, created=True)

    async def resume(
        self,
        mission_id: str,
        command: MissionResumePayload,
    ) -> MissionAppendResultPayload:
        run = await self._store.repository.get_run(mission_id)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found")
        snapshot = dict(run.snapshot_json or {})
        if run.status != MissionStatus.WAITING.value or snapshot.get("waiting_reason") != "budget":
            return await self._store.resume_run(mission_id, command)

        pending_request = dict(snapshot.get("pending_request") or {})
        if pending_request.get("request_id") != command.request_id:
            raise DataServiceConflictError(
                "Resume request does not match the pending Mission request",
                detail={
                    "mission_id": mission_id,
                    "expected_request_id": pending_request.get("request_id"),
                    "actual_request_id": command.request_id,
                },
            )
        run = await self._store.repository.get_run(mission_id, for_update=True)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found")
        admission_items = await self._store.repository.list_items(
            mission_id=mission_id,
            item_type="mission_admitted",
            limit=1,
        )
        if not admission_items:
            raise DataServiceValidationError(
                "Budget-waiting Mission has no immutable admission receipt",
                detail={"mission_id": mission_id},
            )
        admission = dict(admission_items[0].payload_json or {})
        try:
            pricing_snapshot = MissionPricingSnapshot.model_validate(
                admission["pricing_snapshot"]
            )
        except (KeyError, ValueError) as exc:
            raise DataServiceValidationError(
                "Budget-waiting Mission has no valid pricing snapshot",
                detail={"mission_id": mission_id},
            ) from exc
        estimate = max(int(admission.get("estimated_credits") or 0), 0)
        if estimate <= 0:
            raise DataServiceValidationError(
                "Budget-waiting Mission has no positive credit estimate",
                detail={"mission_id": mission_id},
            )
        ttl_seconds = int(admission["reservation_ttl_seconds"])
        now = await self._store.repository.database_now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        metadata = {
            "mission_policy_id": run.mission_policy_id,
            "model_id": run.model_id,
            "pricing_policy_id": admission.get("pricing_policy_id"),
            "pricing_snapshot": pricing_snapshot.model_dump(mode="json"),
        }
        existing_reservation = (
            await self._credits.repository.get_mission_reservation_for_update(
                mission_id
            )
        )
        if existing_reservation is None:
            reservation = await self._credits.create_reservation(
                user_id=run.user_id,
                reserved_credits=estimate,
                idempotency_key=f"mission:{mission_id}",
                workspace_id=run.workspace_id,
                mission_id=mission_id,
                expires_at=expires_at,
                metadata=metadata,
            )
        elif existing_reservation.status in {
            CreditReservationStatus.EXPIRED,
            CreditReservationStatus.RELEASED,
        }:
            reservation = await self._credits.reactivate_reservation(
                str(existing_reservation.id),
                reserved_credits=estimate,
                expires_at=expires_at,
                metadata=metadata,
            )
        elif existing_reservation.status == CreditReservationStatus.RESERVED:
            reservation = existing_reservation
        else:
            raise DataServiceConflictError(
                "Settled Mission reservation cannot be resumed",
                detail={"mission_id": mission_id},
            )
        billing = {
            "pricing_policy_id": admission.get("pricing_policy_id"),
            "pricing_policy_key": admission.get("pricing_policy_key"),
            "estimated_credits": estimate,
            "reservation_ttl_seconds": ttl_seconds,
            "state": "ready",
            "free_policy": False,
            "reservation_id": str(reservation.id),
            "expires_at": expires_at.isoformat(),
        }
        return await self._store.resume_run(
            mission_id,
            command,
            snapshot_patch={"billing": billing},
        )

    async def reconcile_expired_reservations(
        self,
        command: MissionReservationReconcilePayload,
    ) -> MissionReservationReconcileResultPayload:
        now = command.now or await self._store.repository.database_now()
        candidates = (
            await self._credits.repository.list_expired_mission_reservation_refs(
                now=now,
                limit=command.limit,
            )
        )
        expired: list[str] = []
        settled: list[str] = []
        for reservation_id, mission_id in candidates:
            run = await self._store.repository.get_run(
                mission_id,
                for_update=True,
            )
            if run is None:
                await self._credits.expire_reservation(
                    reservation_id,
                    now=now,
                )
                continue
            if run.status in {"completed", "failed", "cancelled"}:
                await self._store.settle_terminal_mission(mission_id)
                settled.append(mission_id)
                continue
            reservation = await self._credits.expire_reservation(
                reservation_id,
                now=now,
            )
            if reservation.status != CreditReservationStatus.EXPIRED:
                continue
            snapshot = dict(run.snapshot_json or {})
            billing = dict(snapshot.get("billing") or {})
            billing.update(
                {
                    "state": "expired",
                    "reservation_id": reservation_id,
                    "expires_at": (
                        reservation.expires_at.isoformat()
                        if reservation.expires_at is not None
                        else None
                    ),
                }
            )
            expiry_key = int(reservation.expires_at.timestamp())
            await self._store.pause_run(
                mission_id,
                MissionPausePayload(
                    request_id=f"billing:{mission_id}:{expiry_key}",
                    reason="budget",
                    producer="mission_reservation_reconciler",
                    pending_request={
                        "request_type": "budget_confirmation",
                        "required_credits": int(reservation.reserved_credits or 0),
                        "summary": "任务占用额度已过期，重新确认额度后即可继续。",
                    },
                ),
                snapshot_patch={"billing": billing},
            )
            expired.append(mission_id)
        return MissionReservationReconcileResultPayload(
            expired_mission_ids=expired,
            settled_mission_ids=settled,
        )

__all__ = ["MissionAdmissionService"]

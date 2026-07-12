"""Durable Mission permission pause and idempotent resume runtime."""

from __future__ import annotations

from src.dataservice_client.contracts.mission import MissionPausePayload, MissionResumePayload
from src.dataservice_client.mission_client import MissionDataServiceClient
from src.review_commit_runtime.membership import (
    MembershipAuthorizer,
    require_owned_mission,
)

from .contracts import (
    PermissionContext,
    PermissionDecision,
    PermissionDisposition,
    PermissionEvaluation,
    PermissionGrant,
    PermissionRequestType,
    PermissionResolution,
)
from .policy import evaluate_permission


class PermissionRuntime:
    def __init__(
        self,
        *,
        missions: MissionDataServiceClient,
        membership: MembershipAuthorizer,
    ) -> None:
        self._missions = missions
        self._membership = membership

    async def evaluate_or_pause(
        self,
        context: PermissionContext,
        *,
        request_id: str,
        request_type: PermissionRequestType = PermissionRequestType.PERMISSION,
        prompt: str | None = None,
    ) -> PermissionEvaluation:
        evaluation = evaluate_permission(context)
        if evaluation.disposition != PermissionDisposition.ASK:
            return evaluation
        await self._missions.pause(
            context.mission_id,
            MissionPausePayload(
                request_id=request_id,
                reason=request_type.value,
                pending_request={
                    "request_id": request_id,
                    "request_type": request_type.value,
                    "prompt": prompt,
                    "permission_context": context.model_dump(mode="json"),
                },
                producer="permission_runtime",
            ),
        )
        return evaluation

    async def resolve(
        self,
        mission_id: str,
        *,
        request_id: str,
        decision: PermissionDecision,
        actor_user_id: str,
        input_json: dict | None = None,
    ) -> PermissionResolution:
        existing = await self._existing_resolution(
            mission_id,
            request_id=request_id,
            decision=decision,
            actor_user_id=actor_user_id,
        )
        if existing is not None:
            await require_owned_mission(
                self._missions,
                self._membership,
                mission_id=mission_id,
                actor_user_id=actor_user_id,
            )
            return existing
        run = await require_owned_mission(
            self._missions,
            self._membership,
            mission_id=mission_id,
            actor_user_id=actor_user_id,
        )
        pending = dict(run.snapshot_json.get("pending_request") or {})
        if pending.get("request_id") != request_id:
            raise ValueError("permission_request_mismatch")
        context = PermissionContext.model_validate(pending.get("permission_context") or {})
        if context.mission_id != mission_id:
            raise ValueError("permission_mission_mismatch")
        if decision == PermissionDecision.CANCEL_MISSION:
            raise ValueError("cancel_mission must use MissionRuntime.cancel")
        payload = {
            "request_id": request_id,
            "decision": decision.value,
            "actor_user_id": actor_user_id,
            "permission_context": context.model_dump(mode="json"),
            **dict(input_json or {}),
        }
        resumed = await self._missions.resume(
            mission_id,
            MissionResumePayload(
                request_id=request_id,
                input_json=payload,
                producer="permission_runtime",
            ),
        )
        grant = None
        if decision in {
            PermissionDecision.ALLOW_ONCE,
            PermissionDecision.ALLOW_FOR_MISSION,
        }:
            grant = PermissionGrant(
                request_id=request_id,
                mission_id=mission_id,
                decision=decision,
                tool_name=context.tool_name,
                operation=context.operation,
                network_profile=context.network_profile,
            )
        return PermissionResolution(
            request_id=request_id,
            decision=decision,
            resumed=resumed.mission.status.value == "planning",
            grant=grant,
            input_json=payload,
        )

    async def _existing_resolution(
        self,
        mission_id: str,
        *,
        request_id: str,
        decision: PermissionDecision,
        actor_user_id: str,
    ) -> PermissionResolution | None:
        items = await self._missions.list_items(
            mission_id,
            item_type="resume_input",
            limit=500,
        )
        existing = next(
            (item for item in items if item.operation_id == request_id),
            None,
        )
        if existing is None:
            return None
        payload = dict(existing.payload_json or {})
        if payload.get("decision") != decision.value or payload.get("actor_user_id") != actor_user_id:
            raise ValueError("permission_resolution_conflict")
        context = PermissionContext.model_validate(payload.get("permission_context") or {})
        grant = None
        if decision in {
            PermissionDecision.ALLOW_ONCE,
            PermissionDecision.ALLOW_FOR_MISSION,
        }:
            grant = PermissionGrant(
                request_id=request_id,
                mission_id=mission_id,
                decision=decision,
                tool_name=context.tool_name,
                operation=context.operation,
                network_profile=context.network_profile,
            )
        return PermissionResolution(
            request_id=request_id,
            decision=decision,
            resumed=True,
            grant=grant,
            input_json=payload,
        )

    @staticmethod
    def validate_network_grant(
        grant: PermissionGrant,
        *,
        mission_id: str,
        tool_name: str,
        operation: str,
        network_profile: str,
    ) -> None:
        if grant.mission_id != mission_id or grant.tool_name != tool_name or grant.operation != operation or grant.network_profile != network_profile:
            raise ValueError("sandbox_network_grant_scope_mismatch")


__all__ = ["PermissionRuntime"]

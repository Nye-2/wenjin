"""Resolve durable user permission decisions for paused Missions."""

from __future__ import annotations

from typing import Any, Protocol

from src.dataservice_client.mission_client import MissionDataServiceClient
from src.review_commit_runtime.membership import (
    MembershipAuthorizer,
    require_owned_mission,
)

from .contracts import (
    PermissionContext,
    PermissionDecision,
    PermissionGrant,
    PermissionResolution,
)


class PermissionMissionResumer(Protocol):
    async def resume(
        self,
        mission_id: str,
        *,
        request_id: str,
        input_json: dict[str, Any],
        producer: str = "workspace_agent",
    ) -> Any: ...


class PermissionResolutionService:
    def __init__(
        self,
        *,
        missions: MissionDataServiceClient,
        membership: MembershipAuthorizer,
        resumer: PermissionMissionResumer,
    ) -> None:
        self._missions = missions
        self._membership = membership
        self._resumer = resumer

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
        context = PermissionContext.model_validate(
            pending.get("permission_context") or {}
        )
        if context.mission_id != mission_id:
            raise ValueError("permission_mission_mismatch")
        if decision is PermissionDecision.CANCEL_MISSION:
            raise ValueError("cancel_mission must use MissionRuntime.cancel")
        payload = {
            "request_id": request_id,
            "decision": decision.value,
            "actor_user_id": actor_user_id,
            "permission_context": context.model_dump(mode="json"),
            **dict(input_json or {}),
        }
        resumed = await self._resumer.resume(
            mission_id,
            request_id=request_id,
            input_json=payload,
            producer="permission_runtime",
        )
        return PermissionResolution(
            request_id=request_id,
            decision=decision,
            resumed=resumed.status.value == "planning",
            grant=_permission_grant(
                request_id=request_id,
                context=context,
                decision=decision,
            ),
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
        if (
            payload.get("decision") != decision.value
            or payload.get("actor_user_id") != actor_user_id
        ):
            raise ValueError("permission_resolution_conflict")
        context = PermissionContext.model_validate(
            payload.get("permission_context") or {}
        )
        return PermissionResolution(
            request_id=request_id,
            decision=decision,
            resumed=True,
            grant=_permission_grant(
                request_id=request_id,
                context=context,
                decision=decision,
            ),
            input_json=payload,
        )


def _permission_grant(
    *,
    request_id: str,
    context: PermissionContext,
    decision: PermissionDecision,
) -> PermissionGrant | None:
    if decision not in {
        PermissionDecision.ALLOW_ONCE,
        PermissionDecision.ALLOW_FOR_MISSION,
    }:
        return None
    return PermissionGrant(
        request_id=request_id,
        mission_id=context.mission_id,
        decision=decision,
        tool_name=context.tool_name,
        operation=context.operation,
        network_profile=context.network_profile,
    )


__all__ = ["PermissionMissionResumer", "PermissionResolutionService"]

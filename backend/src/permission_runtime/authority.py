"""Server-owned permission authority derived from durable Mission receipts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from src.dataservice_client.contracts.mission import MissionItemPayload

from .contracts import PermissionContext, PermissionDecision, PermissionGrant


class PermissionItemReader(Protocol):
    async def list_items(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> list[MissionItemPayload]: ...


class PermissionAuthorizationStatus(StrEnum):
    MISSING = "missing"
    ALLOWED = "allowed"
    DENIED = "denied"


class PermissionAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: PermissionAuthorizationStatus
    request_id: str
    grant: PermissionGrant | None = None
    receipt_item_seq: int | None = None

    @property
    def receipt_ref(self) -> str | None:
        if self.receipt_item_seq is None:
            return None
        return f"mission-item:{self.receipt_item_seq}"


def permission_operation(
    operation_id: str,
    arguments: dict[str, Any],
) -> str:
    arguments_hash = hashlib.sha256(
        json.dumps(
            arguments,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:20]
    return f"{operation_id}:{arguments_hash}"


def permission_request_id(context: PermissionContext) -> str:
    digest = hashlib.sha256(
        context.model_dump_json(exclude_none=True).encode("utf-8")
    ).hexdigest()
    return f"permission-{digest[:40]}"


async def resolve_permission_authorization(
    reader: PermissionItemReader,
    context: PermissionContext,
) -> PermissionAuthorization:
    request_id = permission_request_id(context)
    items = await _list_permission_receipts(reader, context.mission_id)
    exact: MissionItemPayload | None = None
    mission_grant: MissionItemPayload | None = None
    for item in items:
        if item.producer != "permission_runtime":
            continue
        payload = dict(item.payload_json or {})
        try:
            receipt_context = PermissionContext.model_validate(
                payload.get("permission_context") or {}
            )
            decision = PermissionDecision(str(payload.get("decision") or ""))
        except (ValueError, TypeError):
            continue
        if item.operation_id == request_id:
            exact = item
        if (
            decision is PermissionDecision.ALLOW_FOR_MISSION
            and receipt_context.mission_id == context.mission_id
            and receipt_context.tool_name == context.tool_name
            and receipt_context.network_profile == context.network_profile
        ):
            mission_grant = item

    selected = exact or mission_grant
    if selected is None:
        return PermissionAuthorization(
            status=PermissionAuthorizationStatus.MISSING,
            request_id=request_id,
        )

    payload = dict(selected.payload_json or {})
    decision = PermissionDecision(str(payload["decision"]))
    if decision not in {
        PermissionDecision.ALLOW_ONCE,
        PermissionDecision.ALLOW_FOR_MISSION,
    }:
        return PermissionAuthorization(
            status=PermissionAuthorizationStatus.DENIED,
            request_id=request_id,
            receipt_item_seq=selected.seq,
        )
    selected_context = PermissionContext.model_validate(
        payload["permission_context"]
    )
    grant = PermissionGrant(
        request_id=selected.operation_id,
        mission_id=context.mission_id,
        decision=decision,
        tool_name=context.tool_name,
        operation=(
            context.operation
            if decision is PermissionDecision.ALLOW_ONCE
            else selected_context.operation
        ),
        network_profile=context.network_profile,
    )
    return PermissionAuthorization(
        status=PermissionAuthorizationStatus.ALLOWED,
        request_id=request_id,
        grant=grant,
        receipt_item_seq=selected.seq,
    )


async def _list_permission_receipts(
    reader: PermissionItemReader,
    mission_id: str,
) -> list[MissionItemPayload]:
    items: list[MissionItemPayload] = []
    after_seq = 0
    while True:
        batch = await reader.list_items(
            mission_id,
            after_seq=after_seq,
            limit=500,
            item_type="resume_input",
        )
        if not batch:
            return items
        items.extend(batch)
        after_seq = max(item.seq for item in batch)
        if len(batch) < 500:
            return items


__all__ = [
    "PermissionAuthorization",
    "PermissionAuthorizationStatus",
    "permission_operation",
    "permission_request_id",
    "resolve_permission_authorization",
]

"""Audit endpoints for DataService internal API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.dataservice.audit_api import AuditDataService
from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.audit import AuditLogCreatePayload

router = APIRouter(
    prefix="/internal/v1/audit",
    tags=["audit"],
    dependencies=[Depends(require_internal_token)],
)


def _audit_payload(record: Any) -> dict[str, Any]:
    return {
        "id": int(record.id),
        "action": record.action,
        "user_id": record.user_id,
        "workspace_id": record.workspace_id,
        "target_type": record.target_type,
        "target_id": record.target_id,
        "payload": record.payload or {},
        "ip_address": record.ip_address,
        "user_agent": record.user_agent,
        "created_at": record.created_at,
    }


@router.post("/logs")
async def create_audit_log(
    payload: AuditLogCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AuditDataService(
        uow.required_session,
        autocommit=False,
    ).log(
        action=payload.action,
        user_id=payload.user_id,
        workspace_id=payload.workspace_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        payload=payload.payload,
        ip=payload.ip,
        ua=payload.ua,
    )
    await uow.commit()
    return envelope_ok(_audit_payload(record))


@router.get("/logs")
async def query_audit_logs(
    workspace_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    records = await AuditDataService(
        uow.required_session,
        autocommit=False,
    ).query(
        workspace_id=workspace_id,
        user_id=user_id,
        since=since,
        limit=limit,
    )
    return envelope_ok([_audit_payload(record) for record in records])

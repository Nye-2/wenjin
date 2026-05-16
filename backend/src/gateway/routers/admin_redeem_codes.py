"""Admin endpoints for redeem codes."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from src.database import User, get_db_session
from src.gateway.auth_dependencies import get_current_admin
from src.services.credit_redeem_service import CreditRedeemService

router = APIRouter(prefix="/admin/redeem-codes", tags=["admin", "credits"])


async def _service():
    async with get_db_session() as db:
        yield CreditRedeemService(db)


def _to_dict(code) -> dict[str, Any]:
    return {
        "id": code.id, "code": code.code, "amount": code.amount,
        "max_uses": code.max_uses, "use_count": code.use_count,
        "per_user_limit": code.per_user_limit, "expires_at": code.expires_at,
        "valid_from": code.valid_from, "enabled": code.enabled,
        "batch_id": code.batch_id, "description": code.description,
        "created_at": code.created_at,
    }


@router.get("")
async def list_codes(
    batch_id: str | None = Query(None),
    enabled: bool | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: CreditRedeemService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    codes = await service.list_by_filter(
        batch_id=batch_id, enabled=enabled, keyword=keyword,
        limit=page_size, offset=(page - 1) * page_size,
    )
    return {"items": [_to_dict(c) for c in codes], "page": page}


@router.post("/batch")
async def batch_generate(
    payload: dict = Body(...),
    service: CreditRedeemService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        expires_at_raw = payload.get("expires_at")
        expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw else None
        codes = await service.batch_generate(
            amount=int(payload["amount"]),
            count=int(payload["count"]),
            max_uses=int(payload.get("max_uses", 1)),
            per_user_limit=int(payload.get("per_user_limit", 1)),
            expires_at=expires_at,
            description=payload.get("description"),
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "batch_id": codes[0].batch_id if codes else None,
        "items": [_to_dict(c) for c in codes],
    }


@router.post("/{code_id}/disable")
async def disable_code(
    code_id: str,
    service: CreditRedeemService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        code = await service.disable(code_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_dict(code)


@router.get("/export.csv")
async def export_csv(
    batch_id: str,
    service: CreditRedeemService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> Response:
    codes = await service.list_by_filter(batch_id=batch_id, limit=10000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["code", "amount", "expires_at", "max_uses", "per_user_limit", "batch_id"])
    for c in codes:
        writer.writerow([
            c.code, c.amount,
            c.expires_at.isoformat() if c.expires_at else "",
            c.max_uses, c.per_user_limit, c.batch_id or "",
        ])
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="redeem-codes-{batch_id}.csv"'},
    )

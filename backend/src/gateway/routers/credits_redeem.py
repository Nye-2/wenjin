"""User-facing redeem endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.services.credit_redeem_service import CreditRedeemService, RedeemError

router = APIRouter(prefix="/credits", tags=["credits"])


def _service() -> CreditRedeemService:
    return CreditRedeemService()


@router.post("/redeem")
async def redeem(
    payload: dict = Body(...),
    service: CreditRedeemService = Depends(_service),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "code required")
    try:
        txn = await service.redeem(code=code, user_id=user.id)
    except RedeemError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "amount": txn.amount,
        "balance_after": txn.balance_after,
        "transaction_id": txn.id,
    }

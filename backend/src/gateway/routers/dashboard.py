"""User/Admin dashboard router."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.database import AdminActionType, User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import (
    get_admin_dashboard_service,
    get_credit_service,
    get_release_gate_service,
    get_user_dashboard_service,
)
from src.services.admin_dashboard_service import AdminDashboardService
from src.services.credit_service import CreditService
from src.services.release_gate_service import ReleaseGateService
from src.services.user_dashboard_service import UserDashboardService

router = APIRouter(tags=["dashboard"])


class GrantCreditsRequest(BaseModel):
    """Admin grant credits request."""

    user_id: str
    amount: int = Field(..., gt=0)
    description: str = Field(default="管理员发放积分", max_length=500)


class DeductCreditsRequest(BaseModel):
    """Admin deduct credits request."""

    user_id: str
    amount: int = Field(..., gt=0)
    description: str = Field(default="管理员扣除积分", max_length=500)


class UpdateUserStatusRequest(BaseModel):
    """Admin update user status request."""

    is_active: bool


class UpdateUserRoleRequest(BaseModel):
    """Admin update user role request."""

    role: str = Field(pattern="^(user|admin)$")


def _require_admin(current_user: User) -> None:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/dashboard/me")
async def get_my_dashboard(
    current_user: User = Depends(get_current_user),
    dashboard_service: UserDashboardService = Depends(get_user_dashboard_service),
) -> dict[str, Any]:
    """Get user dashboard payload."""
    return await dashboard_service.get_dashboard(str(current_user.id))


@router.get("/dashboard/me/credits/history")
async def get_my_credit_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    transaction_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    credit_service: CreditService = Depends(get_credit_service),
) -> dict[str, Any]:
    """Get paginated credit transactions for current user."""
    offset = (page - 1) * page_size
    try:
        items, total = await credit_service.get_history(
            user_id=str(current_user.id),
            limit=page_size,
            offset=offset,
            transaction_type=transaction_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "transactions": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }


@router.get("/dashboard/me/credits/costs")
async def get_workflow_costs(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get configured workflow credit costs."""
    return {"costs": CreditService.get_public_workflow_costs()}


@router.get("/dashboard/admin")
async def get_admin_dashboard(
    current_user: User = Depends(get_current_user),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """Get admin dashboard payload."""
    _require_admin(current_user)
    return await dashboard_service.get_dashboard()


@router.get("/dashboard/admin/release-gate")
async def get_admin_release_gate(
    include_extended: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    release_gate_service: ReleaseGateService = Depends(get_release_gate_service),
) -> dict[str, Any]:
    """Run release gate checks and return Go/No-Go report (admin only)."""
    _require_admin(current_user)
    return await release_gate_service.run(include_extended=include_extended)


@router.get("/dashboard/admin/users")
async def list_admin_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    role: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """List users for admin table."""
    _require_admin(current_user)

    if role not in {None, "user", "admin"}:
        raise HTTPException(status_code=400, detail="Unsupported role filter")
    is_superuser = None if role is None else role == "admin"

    users, total = await dashboard_service.list_users(
        page=page,
        page_size=page_size,
        keyword=keyword,
        is_active=is_active,
        is_superuser=is_superuser,
    )
    return {
        "users": users,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }


@router.post("/dashboard/admin/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    request: UpdateUserStatusRequest,
    raw_request: Request,
    current_user: User = Depends(get_current_user),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """Update user enabled/disabled status."""
    _require_admin(current_user)
    if str(current_user.id) == user_id and not request.is_active:
        raise HTTPException(status_code=400, detail="Cannot disable your own account")

    try:
        updated_user = await dashboard_service.update_user_status(
            user_id=user_id,
            is_active=request.is_active,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400 if "last active admin" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc

    await dashboard_service.create_admin_log(
        admin_id=str(current_user.id),
        action=AdminActionType.USER_STATUS_CHANGE,
        target_user_id=user_id,
        details={"is_active": request.is_active},
        ip_address=raw_request.client.host if raw_request.client else None,
    )
    return {"success": True, "user": updated_user}


@router.post("/dashboard/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: UpdateUserRoleRequest,
    raw_request: Request,
    current_user: User = Depends(get_current_user),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """Update user role (user/admin)."""
    _require_admin(current_user)
    if str(current_user.id) == user_id and request.role == "user":
        raise HTTPException(status_code=400, detail="Cannot demote your own admin role")

    try:
        updated_user = await dashboard_service.update_user_role(
            user_id=user_id,
            role=request.role,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400 if ("Unsupported role" in detail or "last active admin" in detail) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    await dashboard_service.create_admin_log(
        admin_id=str(current_user.id),
        action=AdminActionType.USER_ROLE_CHANGE,
        target_user_id=user_id,
        details={"role": request.role},
        ip_address=raw_request.client.host if raw_request.client else None,
    )
    return {"success": True, "user": updated_user}


@router.post("/dashboard/admin/credits/grant")
async def grant_credits(
    request: GrantCreditsRequest,
    raw_request: Request,
    current_user: User = Depends(get_current_user),
    credit_service: CreditService = Depends(get_credit_service),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """Grant credits to a user."""
    _require_admin(current_user)

    try:
        tx = await credit_service.admin_grant(
            admin_id=str(current_user.id),
            target_user_id=request.user_id,
            amount=request.amount,
            description=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await dashboard_service.create_admin_log(
        admin_id=str(current_user.id),
        action=AdminActionType.CREDIT_GRANT,
        target_user_id=request.user_id,
        details={
            "amount": request.amount,
            "balance_after": int(tx.balance_after),
            "description": request.description,
        },
        ip_address=raw_request.client.host if raw_request.client else None,
    )
    return {
        "success": True,
        "transaction": {
            "id": str(tx.id),
            "amount": int(tx.amount),
            "balance_after": int(tx.balance_after),
        },
    }


@router.post("/dashboard/admin/credits/deduct")
async def deduct_credits(
    request: DeductCreditsRequest,
    raw_request: Request,
    current_user: User = Depends(get_current_user),
    credit_service: CreditService = Depends(get_credit_service),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """Deduct credits from a user."""
    _require_admin(current_user)

    try:
        tx = await credit_service.admin_deduct(
            admin_id=str(current_user.id),
            target_user_id=request.user_id,
            amount=request.amount,
            description=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await dashboard_service.create_admin_log(
        admin_id=str(current_user.id),
        action=AdminActionType.CREDIT_DEDUCT,
        target_user_id=request.user_id,
        details={
            "amount": request.amount,
            "actual_deducted": abs(int(tx.amount)),
            "balance_after": int(tx.balance_after),
            "description": request.description,
        },
        ip_address=raw_request.client.host if raw_request.client else None,
    )
    return {
        "success": True,
        "transaction": {
            "id": str(tx.id),
            "amount": int(tx.amount),
            "balance_after": int(tx.balance_after),
        },
    }


@router.get("/dashboard/admin/credits/history")
async def get_admin_credit_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    credit_service: CreditService = Depends(get_credit_service),
) -> dict[str, Any]:
    """Get credit transaction history across users (admin)."""
    _require_admin(current_user)
    offset = (page - 1) * page_size

    try:
        items, total = await credit_service.get_all_history(
            limit=page_size,
            offset=offset,
            user_id=user_id,
            transaction_type=transaction_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "transactions": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }


@router.get("/dashboard/admin/logs")
async def get_admin_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    target_user_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> dict[str, Any]:
    """Get admin audit logs."""
    _require_admin(current_user)
    try:
        items, total = await dashboard_service.list_admin_logs(
            page=page,
            page_size=page_size,
            action=action,
            target_user_id=target_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "logs": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }

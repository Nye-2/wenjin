"""Account endpoints for DataService internal API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from src.dataservice.account_api import AccountDataService
from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.account import (
    AccountRefreshTokenPayload,
    AccountUserCreatePayload,
    AccountUserRolePayload,
    AccountUserStatusPayload,
)

router = APIRouter(
    prefix="/internal/v1/account",
    tags=["account"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/users")
async def create_user(
    payload: AccountUserCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = AccountDataService(uow.required_session, autocommit=False)
    user = await service.create_user(
        email=payload.email,
        hashed_password=payload.hashed_password,
        name=payload.name,
        auto_commit=False,
    )
    await uow.commit()
    record = await service.get_user_record(str(user.id))
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/users/by-email")
async def get_auth_user_by_email(
    email: str = Query(),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).get_auth_user_by_email(email)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/users/{user_id}/auth")
async def get_auth_user_by_id(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).get_auth_user_by_id(user_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/users/{user_id}")
async def get_user_record(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).get_user_record(user_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/users/{user_id}/refresh-token")
async def update_refresh_token(
    user_id: str,
    payload: AccountRefreshTokenPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).update_refresh_token(
        user_id=user_id,
        refresh_token_hash=payload.refresh_token_hash,
        refresh_token_expires_at=payload.refresh_token_expires_at,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/users/{user_id}/last-login")
async def update_last_login(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).update_last_login(user_id)
    await uow.commit()
    if record is None:
        return envelope_ok(None)
    auth_record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).get_auth_user_by_id(user_id)
    return envelope_ok(auth_record.model_dump(mode="json") if auth_record else None)


@router.get("/admin-stats")
async def get_admin_stats(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).get_admin_stats()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/users")
async def list_users(
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    keyword: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    is_superuser: bool | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).list_users(
        page=page,
        page_size=page_size,
        keyword=keyword,
        is_active=is_active,
        is_superuser=is_superuser,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/admins/active-count")
async def count_active_admins(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    count = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).count_active_admins()
    return envelope_ok({"count": count})


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    payload: AccountUserStatusPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).update_user_status(user_id=user_id, is_active=payload.is_active)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: AccountUserRolePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).update_user_role(user_id=user_id, role=payload.role)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/growth")
async def aggregate_user_growth(
    since: datetime = Query(),
    granularity: str = Query(default="day"),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await AccountDataService(
        uow.required_session,
        autocommit=False,
    ).aggregate_user_growth(since=since, granularity=granularity)
    return envelope_ok(record.model_dump(mode="json"))

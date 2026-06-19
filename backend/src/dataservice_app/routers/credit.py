"""Credit endpoints for DataService internal API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.credit_api import CreditDataService, CreditGrantRuleType, CreditTransactionType
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditConsumptionCreatePayload,
    CreditGrantRuleCreatePayload,
    CreditGrantRuleUpdatePayload,
    CreditPeriodicGrantProcessPayload,
    CreditRedeemCodeCreatePayload,
    CreditRedeemPayload,
    CreditReferralCreatePayload,
    CreditRefundPayload,
    CreditReservationCreatePayload,
    CreditReservationReleasePayload,
    CreditReservationSettlePayload,
)

router = APIRouter(
    prefix="/internal/v1/credit",
    tags=["credit"],
    dependencies=[Depends(require_internal_token)],
)


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _rule_payload(rule: Any) -> dict[str, Any] | None:
    if rule is None:
        return None
    return {
        "id": str(rule.id),
        "name": rule.name,
        "rule_type": _enum_value(rule.rule_type),
        "enabled": bool(rule.enabled),
        "amount": int(rule.amount),
        "description": rule.description,
        "config": rule.config or {},
        "last_triggered_at": rule.last_triggered_at,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
        "created_by_admin_id": str(rule.created_by_admin_id) if rule.created_by_admin_id else None,
    }


def _transaction_payload(tx: Any) -> dict[str, Any] | None:
    if tx is None:
        return None
    return {
        "id": str(tx.id),
        "user_id": str(tx.user_id),
        "transaction_type": _enum_value(tx.transaction_type),
        "amount": int(tx.amount),
        "balance_after": int(tx.balance_after),
        "description": tx.description,
        "feature_id": tx.feature_id,
        "workspace_id": str(tx.workspace_id) if tx.workspace_id else None,
        "task_id": str(tx.task_id) if tx.task_id else None,
        "admin_id": str(tx.admin_id) if tx.admin_id else None,
        "metadata": tx.tx_metadata or {},
        "created_at": tx.created_at,
    }


def _reservation_payload(reservation: Any) -> dict[str, Any] | None:
    if reservation is None:
        return None
    return {
        "id": str(reservation.id),
        "user_id": str(reservation.user_id),
        "workspace_id": str(reservation.workspace_id) if reservation.workspace_id else None,
        "execution_id": reservation.execution_id,
        "node_id": reservation.node_id,
        "scope": _enum_value(reservation.scope),
        "status": _enum_value(reservation.status),
        "reserved_credits": int(reservation.reserved_credits),
        "settled_credits": int(reservation.settled_credits),
        "transaction_id": str(reservation.transaction_id) if reservation.transaction_id else None,
        "idempotency_key": reservation.idempotency_key,
        "expires_at": reservation.expires_at,
        "metadata": reservation.metadata_json or {},
        "created_at": reservation.created_at,
        "updated_at": reservation.updated_at,
    }


def _redeem_code_payload(code: Any) -> dict[str, Any] | None:
    if code is None:
        return None
    return {
        "id": str(code.id),
        "code": code.code,
        "amount": int(code.amount),
        "max_uses": int(code.max_uses),
        "use_count": int(code.use_count),
        "per_user_limit": int(code.per_user_limit),
        "expires_at": code.expires_at,
        "valid_from": code.valid_from,
        "enabled": bool(code.enabled),
        "batch_id": code.batch_id,
        "description": code.description,
        "created_at": code.created_at,
        "created_by_admin_id": str(code.created_by_admin_id) if code.created_by_admin_id else None,
    }


def _referral_payload(referral: Any) -> dict[str, Any] | None:
    if referral is None:
        return None
    return {
        "id": str(referral.id),
        "referrer_user_id": str(referral.referrer_user_id),
        "referee_user_id": str(referral.referee_user_id),
        "referrer_credited_at": referral.referrer_credited_at,
        "referee_credited_at": referral.referee_credited_at,
        "referee_first_task_at": referral.referee_first_task_at,
        "created_at": referral.created_at,
    }


@router.get("/grant-rules")
async def list_grant_rules(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    rules = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).list_grant_rules()
    return envelope_ok([_rule_payload(rule) for rule in rules])


@router.get("/grant-rules/{rule_id}")
async def get_grant_rule(
    rule_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    rule = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_grant_rule(rule_id)
    return envelope_ok(_rule_payload(rule))


@router.get("/active-grant-rules/{rule_type}")
async def get_active_grant_rule(
    rule_type: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    rule = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_active_grant_rule(CreditGrantRuleType(rule_type))
    return envelope_ok(_rule_payload(rule))


@router.post("/grant-rules")
async def create_grant_rule(
    payload: CreditGrantRuleCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    rule = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).create_grant_rule(
        name=payload.name,
        rule_type=CreditGrantRuleType(payload.rule_type),
        amount=payload.amount,
        config=payload.config,
        description=payload.description,
        admin_id=payload.admin_id,
    )
    await uow.commit()
    return envelope_ok(_rule_payload(rule))


@router.put("/grant-rules/{rule_id}")
async def update_grant_rule(
    rule_id: str,
    payload: CreditGrantRuleUpdatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    rule = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).update_grant_rule(
        rule_id=rule_id,
        name=payload.name,
        amount=payload.amount,
        config=payload.config,
        description=payload.description,
    )
    await uow.commit()
    return envelope_ok(_rule_payload(rule))


@router.post("/grant-rules/{rule_id}/toggle")
async def toggle_grant_rule(
    rule_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    rule = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).toggle_grant_rule(rule_id)
    await uow.commit()
    return envelope_ok(_rule_payload(rule))


@router.delete("/grant-rules/{rule_id}")
async def delete_grant_rule(
    rule_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    deleted = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).delete_grant_rule(rule_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted is not None})


@router.post("/users/{user_id}/registration-bonus")
async def apply_registration_bonus(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = CreditDataService(uow.required_session, autocommit=False)
    rule = await service.get_active_grant_rule(CreditGrantRuleType.REGISTRATION_BONUS)
    tx = None
    if rule is not None:
        tx = await service.apply_registration_bonus_from_rule(user_id=user_id, rule=rule)
        await uow.commit()
    return envelope_ok(_transaction_payload(tx))


@router.post("/periodic-grants/process")
async def process_periodic_grant_rules(
    payload: CreditPeriodicGrantProcessPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    summary = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).process_periodic_grant_rules(now=payload.now)
    await uow.commit()
    return envelope_ok(summary)


@router.get("/users/{user_id}/balance")
async def get_balance(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    balance = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_balance(user_id)
    return envelope_ok({"balance": balance})


@router.get("/users/{user_id}/consumed-tokens")
async def get_consumed_tokens(
    user_id: str,
    consume_type: str = Query(),
    metadata_type: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    consumed = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_consumed_tokens(
        user_id=user_id,
        consume_type=CreditTransactionType(consume_type),
        metadata_type=metadata_type,
    )
    return envelope_ok({"consumed_tokens": consumed})


@router.get("/users/{user_id}/summary")
async def get_credit_summary(
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    summary = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_credit_summary(user_id)
    return envelope_ok(summary)


@router.get("/history")
async def get_credit_history(
    user_id: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx_type = CreditTransactionType(transaction_type) if transaction_type else None
    transactions, total = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_credit_history(
        user_id=user_id,
        transaction_type=tx_type,
        limit=limit,
        offset=offset,
    )
    return envelope_ok(
        {
            "transactions": [_transaction_payload(tx) for tx in transactions],
            "total": total,
        }
    )


@router.get("/admin-summary")
async def get_admin_credit_summary(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    summary = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_admin_credit_summary()
    return envelope_ok(summary)


@router.get("/thread-token-usage")
async def get_thread_token_usage_summary(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    summary = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_thread_token_usage_summary()
    return envelope_ok(summary)


@router.get("/consumption-stats")
async def aggregate_credit_consumption_stats(
    since: datetime = Query(),
    granularity: str = Query(default="day"),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    summary = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).aggregate_credit_consumption_stats(since=since, granularity=granularity)
    return envelope_ok(summary)


@router.post("/consume")
async def record_consumption(
    payload: CreditConsumptionCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx, balance_before = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).record_consumption(
        user_id=payload.user_id,
        transaction_type=CreditTransactionType(payload.transaction_type),
        amount=payload.amount,
        description=payload.description,
        feature_id=payload.feature_id,
        workspace_id=payload.workspace_id,
        task_id=payload.task_id,
        metadata=payload.metadata,
    )
    await uow.commit()
    return envelope_ok({"transaction": _transaction_payload(tx), "balance_before": balance_before})


@router.post("/reservations")
async def create_reservation(
    payload: CreditReservationCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    reservation = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).create_reservation(
        user_id=payload.user_id,
        scope=payload.scope,
        reserved_credits=payload.reserved_credits,
        idempotency_key=payload.idempotency_key,
        workspace_id=payload.workspace_id,
        execution_id=payload.execution_id,
        node_id=payload.node_id,
        expires_at=payload.expires_at,
        metadata=payload.metadata,
    )
    response = _reservation_payload(reservation)
    await uow.commit()
    return envelope_ok(response)


@router.post("/reservations/{reservation_id}/settle")
async def settle_reservation(
    reservation_id: str,
    payload: CreditReservationSettlePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    reservation, tx = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).settle_reservation(
        reservation_id=reservation_id,
        settled_credits=payload.settled_credits,
        description=payload.description,
        transaction_type=CreditTransactionType(payload.transaction_type),
        feature_id=payload.feature_id,
        task_id=payload.task_id,
        metadata=payload.metadata,
    )
    response = {
        "reservation": _reservation_payload(reservation),
        "transaction": _transaction_payload(tx),
    }
    await uow.commit()
    return envelope_ok(response)


@router.post("/reservations/{reservation_id}/release")
async def release_reservation(
    reservation_id: str,
    payload: CreditReservationReleasePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    reservation = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).release_reservation(reservation_id, reason=payload.reason)
    response = _reservation_payload(reservation)
    await uow.commit()
    return envelope_ok(response)


@router.post("/refund")
async def refund_consumption(
    payload: CreditRefundPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).refund_consumption(
        user_id=payload.user_id,
        original_transaction_id=payload.original_transaction_id,
        reason=payload.reason,
        task_id=payload.task_id,
    )
    await uow.commit()
    return envelope_ok(_transaction_payload(tx))


@router.post("/admin-adjust")
async def admin_adjust(
    payload: CreditAdminAdjustPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).admin_adjust(
        admin_id=payload.admin_id,
        target_user_id=payload.target_user_id,
        amount=payload.amount,
        transaction_type=CreditTransactionType(payload.transaction_type),
        description=payload.description,
        metadata=payload.metadata,
    )
    await uow.commit()
    return envelope_ok(_transaction_payload(tx))


@router.post("/redeem-codes")
async def create_redeem_code(
    payload: CreditRedeemCodeCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    code = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).create_redeem_code(**payload.model_dump())
    await uow.commit()
    return envelope_ok(_redeem_code_payload(code))


@router.get("/redeem-codes")
async def list_redeem_codes(
    batch_id: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    codes = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).list_redeem_codes(
        batch_id=batch_id,
        enabled=enabled,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return envelope_ok([_redeem_code_payload(code) for code in codes])


@router.post("/redeem-codes/{code_id}/disable")
async def disable_redeem_code(
    code_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    code = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).disable_redeem_code(code_id)
    await uow.commit()
    return envelope_ok(_redeem_code_payload(code))


@router.post("/redeem")
async def redeem_code(
    payload: CreditRedeemPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).redeem_code(code=payload.code, user_id=payload.user_id)
    await uow.commit()
    return envelope_ok(_transaction_payload(tx))


@router.post("/referrals")
async def record_referral(
    payload: CreditReferralCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    referral = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).record_referral(
        referrer_user_id=payload.referrer_user_id,
        referee_user_id=payload.referee_user_id,
    )
    await uow.commit()
    return envelope_ok(_referral_payload(referral))


@router.get("/referrals/by-referee/{referee_user_id}")
async def get_referral_by_referee(
    referee_user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    referral = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).get_referral_by_referee(referee_user_id)
    return envelope_ok(_referral_payload(referral))


@router.post("/referrals/{referee_user_id}/apply-referee-signup")
async def apply_referee_signup_bonus(
    referee_user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).apply_referee_signup_bonus(referee_user_id=referee_user_id)
    await uow.commit()
    return envelope_ok(_transaction_payload(tx))


@router.post("/referrals/{referee_user_id}/apply-referrer-first-task")
async def apply_referrer_first_task_bonus(
    referee_user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    tx = await CreditDataService(
        uow.required_session,
        autocommit=False,
    ).apply_referrer_first_task_bonus(referee_user_id=referee_user_id)
    await uow.commit()
    return envelope_ok(_transaction_payload(tx))

"""Internal endpoints for atomic chat-turn billing."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.thread_turn_billing import ThreadTurnBillingService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnAuthorizePayload,
    ThreadTurnCompletePayload,
    ThreadTurnReconcilePayload,
    ThreadTurnReleaseByKeyPayload,
    ThreadTurnReleasePayload,
    ThreadTurnRollbackPayload,
)

router = APIRouter(
    prefix="/internal/v1/thread-turn-billings",
    tags=["thread-turn-billing"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/authorize")
async def authorize_thread_turn(
    command: ThreadTurnAuthorizePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await ThreadTurnBillingService(
        uow.required_session,
        autocommit=False,
    ).authorize(command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/reconcile-expired")
async def reconcile_expired_thread_turns(
    command: ThreadTurnReconcilePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await ThreadTurnBillingService(
        uow.required_session,
        autocommit=False,
    ).reconcile_expired(command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/release-by-idempotency-key")
async def release_thread_turn_by_idempotency_key(
    command: ThreadTurnReleaseByKeyPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await ThreadTurnBillingService(
        uow.required_session,
        autocommit=False,
    ).release_by_idempotency_key(command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/{billing_id}/complete")
async def complete_thread_turn(
    billing_id: str,
    command: ThreadTurnCompletePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await ThreadTurnBillingService(
        uow.required_session,
        autocommit=False,
    ).complete(billing_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/{billing_id}/release")
async def release_thread_turn(
    billing_id: str,
    command: ThreadTurnReleasePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await ThreadTurnBillingService(
        uow.required_session,
        autocommit=False,
    ).release(billing_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/{billing_id}/rollback")
async def rollback_thread_turn(
    billing_id: str,
    command: ThreadTurnRollbackPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await ThreadTurnBillingService(
        uow.required_session,
        autocommit=False,
    ).rollback(billing_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))

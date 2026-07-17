"""Periodic recovery for abandoned chat-turn authorizations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict, cast

from celery import shared_task

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnReconcilePayload,
)

THREAD_TURN_BILLING_RECONCILE_LIMIT = 200


class ThreadTurnBillingReconcileSummary(TypedDict):
    expired: int
    billing_ids: list[str]


async def reconcile_thread_turn_billings_async(
    *,
    limit: int = THREAD_TURN_BILLING_RECONCILE_LIMIT,
    dataservice: AsyncDataServiceClient | None = None,
) -> ThreadTurnBillingReconcileSummary:
    if dataservice is None:
        from src.dataservice_client.provider import dataservice_client

        async with dataservice_client() as configured_dataservice:
            return await reconcile_thread_turn_billings_async(
                limit=limit,
                dataservice=configured_dataservice,
            )

    result = await dataservice.thread_turn_billings.reconcile_expired(
        ThreadTurnReconcilePayload(limit=limit)
    )
    return {
        "expired": len(result.expired_billing_ids),
        "billing_ids": result.expired_billing_ids,
    }


def _reconcile_thread_turn_billings_entry(
    _task_self: Any,
    limit: int = THREAD_TURN_BILLING_RECONCILE_LIMIT,
) -> ThreadTurnBillingReconcileSummary:
    from src.task.worker import run_worker_coroutine

    runner = cast(
        Callable[
            [Awaitable[ThreadTurnBillingReconcileSummary]],
            ThreadTurnBillingReconcileSummary,
        ],
        run_worker_coroutine,
    )
    return runner(reconcile_thread_turn_billings_async(limit=limit))


reconcile_thread_turn_billings = shared_task(
    bind=True,
    name="src.task.tasks.reconcile_thread_turn_billings",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=45,
    time_limit=60,
)(_reconcile_thread_turn_billings_entry)


__all__ = [
    "THREAD_TURN_BILLING_RECONCILE_LIMIT",
    "ThreadTurnBillingReconcileSummary",
    "reconcile_thread_turn_billings",
    "reconcile_thread_turn_billings_async",
]

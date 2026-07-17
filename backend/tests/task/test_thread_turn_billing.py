from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.contracts.thread_turn_billing import (
    ThreadTurnReconcilePayload,
    ThreadTurnReconcileResultPayload,
)
from src.task.celery_app import celery_app
from src.task.tasks.thread_turn_billing import (
    THREAD_TURN_BILLING_RECONCILE_LIMIT,
    reconcile_thread_turn_billings,
    reconcile_thread_turn_billings_async,
)


@pytest.mark.asyncio
async def test_reconcile_expired_thread_turn_holds_through_dataservice() -> None:
    reconcile_expired = AsyncMock(
        return_value=ThreadTurnReconcileResultPayload(
            expired_billing_ids=["billing-1", "billing-2"]
        )
    )
    dataservice = SimpleNamespace(
        thread_turn_billings=SimpleNamespace(
            reconcile_expired=reconcile_expired,
        )
    )

    result = await reconcile_thread_turn_billings_async(
        limit=17,
        dataservice=dataservice,
    )

    assert result == {
        "expired": 2,
        "billing_ids": ["billing-1", "billing-2"],
    }
    reconcile_expired.assert_awaited_once_with(
        ThreadTurnReconcilePayload(limit=17)
    )


def test_thread_turn_reconciler_is_bounded_retryable_and_periodic() -> None:
    task_name = "src.task.tasks.reconcile_thread_turn_billings"

    assert reconcile_thread_turn_billings.name == task_name
    assert reconcile_thread_turn_billings.acks_late is True
    assert reconcile_thread_turn_billings.reject_on_worker_lost is True
    assert reconcile_thread_turn_billings.autoretry_for == (Exception,)
    assert reconcile_thread_turn_billings.retry_backoff is True
    assert reconcile_thread_turn_billings.retry_jitter is True
    assert reconcile_thread_turn_billings.max_retries == 3
    assert task_name in celery_app.tasks
    assert celery_app.conf.task_routes[task_name]["queue"] == "default"
    assert celery_app.conf.beat_schedule[
        "reconcile-expired-thread-turn-billings"
    ] == {
        "task": task_name,
        "schedule": 60.0,
    }
    assert THREAD_TURN_BILLING_RECONCILE_LIMIT == 200
    assert sum(
        entry["task"] == task_name
        for entry in celery_app.conf.beat_schedule.values()
    ) == 1

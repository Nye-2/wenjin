"""Tests for durable ChatTurnRun broker-intent reconciliation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.runtime.chat_turns import ChatTurnRunManager, ChatTurnRunStatus
from src.task.tasks.chat_turn_dispatch import (
    enqueue_chat_turn,
    reconcile_chat_turn_dispatches,
)


@pytest.mark.asyncio
async def test_reconciler_publishes_and_receipts_pending_intent() -> None:
    manager = ChatTurnRunManager()
    record = (
        await manager.create_or_reject(
            "thread-1",
            metadata={"_owner_id": "user-1"},
            request_idempotency_key="chat-turn:request-1",
            request_fingerprint="a" * 64,
            dispatch_payload={"message": "hello"},
        )
    ).record
    published: list[tuple[str, dict[str, object], str]] = []

    result = await reconcile_chat_turn_dispatches(
        manager,
        publish=lambda run_id, payload, actor_id: (
            published.append((run_id, payload, actor_id)) or "task-1"
        ),
    )

    assert result == {"published": 1, "skipped": 0, "invalid": 0, "failed": 0}
    assert published == [(record.run_id, {"message": "hello"}, "user-1")]
    assert record.worker_task_id == "task-1"
    assert await manager.list_pending_dispatches() == []


@pytest.mark.asyncio
async def test_reconciler_releases_failed_publication_for_next_pass() -> None:
    manager = ChatTurnRunManager()
    record = (
        await manager.create_or_reject(
            "thread-1",
            metadata={"_owner_id": "user-1"},
            dispatch_payload={"message": "hello"},
        )
    ).record

    def fail(_run_id: str, _payload: dict[str, object], _actor_id: str) -> str:
        raise RuntimeError("broker unavailable")

    failed = await reconcile_chat_turn_dispatches(manager, publish=fail)
    retried = await reconcile_chat_turn_dispatches(
        manager,
        publish=lambda _run_id, _payload, _actor_id: "task-retry",
    )

    assert failed["failed"] == 1
    assert retried["published"] == 1
    assert record.worker_task_id == "task-retry"


@pytest.mark.asyncio
async def test_reconciler_fails_closed_for_invalid_intent() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record

    result = await reconcile_chat_turn_dispatches(manager)

    assert result["invalid"] == 1
    assert record.status is ChatTurnRunStatus.error


def test_enqueue_uses_run_id_as_deterministic_celery_task_id(monkeypatch) -> None:
    import src.task.tasks.run as run_module

    calls: list[dict[str, object]] = []

    class _Task:
        def apply_async(self, **kwargs):  # noqa: ANN003, ANN201
            calls.append(dict(kwargs))
            return SimpleNamespace(id=kwargs["task_id"])

    monkeypatch.setattr(run_module, "process_chat_turn", _Task())

    task_id = enqueue_chat_turn("run-1", {"message": "hello"}, "user-1")

    assert task_id == "run-1"
    assert calls == [
        {
            "args": ["run-1", {"message": "hello"}, "user-1"],
            "queue": "default",
            "task_id": "run-1",
        }
    ]

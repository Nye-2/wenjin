"""Tests for short-lived ChatTurnRun lifecycle and concurrency semantics."""

from __future__ import annotations

import asyncio

import pytest

from src.runtime.chat_turns import (
    ChatTurnConflictError,
    ChatTurnExecutionRenewal,
    ChatTurnRunManager,
    ChatTurnRunStatus,
)


@pytest.mark.asyncio
async def test_create_or_reject_blocks_second_inflight_run():
    manager = ChatTurnRunManager()

    first = (
        await manager.create_or_reject("thread-1", multitask_strategy="reject")
    ).record
    assert await manager.transition_status(
        first.run_id,
        ChatTurnRunStatus.running,
        expected=(ChatTurnRunStatus.pending,),
    )

    with pytest.raises(ChatTurnConflictError):
        await manager.create_or_reject("thread-1", multitask_strategy="reject")


@pytest.mark.asyncio
async def test_stable_request_replays_one_transport_before_multitask_action():
    manager = ChatTurnRunManager()

    first = await manager.create_or_reject(
        "thread-1",
        multitask_strategy="interrupt",
        request_idempotency_key="chat-turn:key-1",
        request_fingerprint="a" * 64,
    )
    replay = await manager.create_or_reject(
        "thread-1",
        multitask_strategy="interrupt",
        request_idempotency_key="chat-turn:key-1",
        request_fingerprint="a" * 64,
    )

    assert first.created is True
    assert replay.created is False
    assert replay.record is first.record
    assert first.record.status is ChatTurnRunStatus.pending
    assert first.record.abort_event.is_set() is False


@pytest.mark.asyncio
async def test_stable_request_rejects_payload_drift():
    manager = ChatTurnRunManager()
    await manager.create_or_reject(
        "thread-1",
        request_idempotency_key="chat-turn:key-1",
        request_fingerprint="a" * 64,
    )

    with pytest.raises(ChatTurnConflictError, match="different payload"):
        await manager.create_or_reject(
            "thread-1",
            request_idempotency_key="chat-turn:key-1",
            request_fingerprint="b" * 64,
        )


@pytest.mark.asyncio
async def test_request_identity_is_actor_global_across_threads() -> None:
    manager = ChatTurnRunManager()
    first = await manager.create_or_reject(
        "thread-1",
        request_idempotency_key="chat-turn:key-1",
        request_fingerprint="a" * 64,
    )

    replay = await manager.create_or_reject(
        "thread-2",
        request_idempotency_key="chat-turn:key-1",
        request_fingerprint="a" * 64,
    )
    assert replay.created is False
    assert replay.record.run_id == first.record.run_id

    with pytest.raises(ChatTurnConflictError, match="different payload"):
        await manager.create_or_reject(
            "thread-2",
            request_idempotency_key="chat-turn:key-1",
            request_fingerprint="b" * 64,
        )


@pytest.mark.asyncio
async def test_interrupt_strategy_cancels_existing_run():
    manager = ChatTurnRunManager()

    first = (
        await manager.create_or_reject("thread-1", multitask_strategy="reject")
    ).record
    assert await manager.transition_status(
        first.run_id,
        ChatTurnRunStatus.running,
        expected=(ChatTurnRunStatus.pending,),
    )
    first.task = asyncio.create_task(asyncio.sleep(60))

    second = (
        await manager.create_or_reject(
            "thread-1",
            multitask_strategy="interrupt",
        )
    ).record

    assert first.abort_event.is_set()
    assert first.status == ChatTurnRunStatus.interrupted
    assert second.status == ChatTurnRunStatus.pending

    first.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first.task


@pytest.mark.asyncio
async def test_rollback_strategy_marks_existing_run_with_rollback_action():
    manager = ChatTurnRunManager()

    first = (
        await manager.create_or_reject("thread-1", multitask_strategy="reject")
    ).record
    assert await manager.transition_status(
        first.run_id,
        ChatTurnRunStatus.running,
        expected=(ChatTurnRunStatus.pending,),
    )
    first.task = asyncio.create_task(asyncio.sleep(60))

    second = (
        await manager.create_or_reject(
            "thread-1",
            multitask_strategy="rollback",
        )
    ).record

    assert first.abort_event.is_set()
    assert first.abort_action == "rollback"
    assert first.status == ChatTurnRunStatus.interrupted
    assert second.status == ChatTurnRunStatus.pending

    first.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first.task


@pytest.mark.asyncio
async def test_bind_thread_updates_record_thread_id():
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("placeholder-thread")).record

    await manager.bind_thread(record.run_id, "thread-real")

    latest = manager.get(record.run_id)
    assert latest is not None
    assert latest.thread_id == "thread-real"


@pytest.mark.asyncio
async def test_list_all_returns_runs_in_reverse_creation_order():
    manager = ChatTurnRunManager()
    first = (await manager.create_or_reject("thread-1")).record
    second = (await manager.create_or_reject("thread-2")).record

    records = await manager.list_all()

    assert [item.run_id for item in records] == [second.run_id, first.run_id]


def test_transport_uses_chat_turn_namespace_and_bounded_ttl() -> None:
    manager = ChatTurnRunManager(chat_turn_ttl_seconds=999999)

    assert manager._chat_turn_key("turn-1") == "runtime:chat_turns:turn-1"
    assert manager._chat_turn_ttl_seconds == 3600
    assert "dataservice" not in manager.__class__.__module__


@pytest.mark.asyncio
async def test_execution_claim_rejects_live_duplicate_and_recovers_stale_worker() -> None:
    manager = ChatTurnRunManager(execution_lease_seconds=0.05)
    record = (await manager.create_or_reject("thread-1")).record

    first_owner = await manager.claim_execution(record.run_id, wait_seconds=0)
    live_duplicate = await manager.claim_execution(record.run_id, wait_seconds=0)
    await asyncio.sleep(0.06)
    recovered_owner = await manager.claim_execution(record.run_id, wait_seconds=0)

    assert first_owner is not None
    assert live_duplicate is None
    assert recovered_owner is not None
    assert recovered_owner != first_owner

    assert (
        await manager.renew_execution_claim(record.run_id, first_owner)
        is ChatTurnExecutionRenewal.lost
    )
    assert (
        await manager.renew_execution_claim(record.run_id, recovered_owner)
        is ChatTurnExecutionRenewal.renewed
    )


@pytest.mark.asyncio
async def test_terminal_transition_is_execution_owner_fenced() -> None:
    manager = ChatTurnRunManager(execution_lease_seconds=0.05)
    record = (await manager.create_or_reject("thread-1")).record
    first_owner = await manager.claim_execution(record.run_id, wait_seconds=0)
    assert first_owner is not None
    await asyncio.sleep(0.06)
    recovered_owner = await manager.claim_execution(record.run_id, wait_seconds=0)
    assert recovered_owner is not None

    assert not await manager.transition_status(
        record.run_id,
        ChatTurnRunStatus.success,
        expected=(ChatTurnRunStatus.running,),
        expected_execution_owner=first_owner,
    )
    assert await manager.transition_status(
        record.run_id,
        ChatTurnRunStatus.success,
        expected=(ChatTurnRunStatus.running,),
        expected_execution_owner=recovered_owner,
    )

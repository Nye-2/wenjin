"""Tests for run manager lifecycle and concurrency semantics."""

from __future__ import annotations

import asyncio

import pytest

from src.runtime.runs import ConflictError, RunManager, RunStatus


@pytest.mark.asyncio
async def test_create_or_reject_blocks_second_inflight_run():
    manager = RunManager()

    first = await manager.create_or_reject("thread-1", multitask_strategy="reject")
    await manager.set_status(first.run_id, RunStatus.running)

    with pytest.raises(ConflictError):
        await manager.create_or_reject("thread-1", multitask_strategy="reject")


@pytest.mark.asyncio
async def test_interrupt_strategy_cancels_existing_run():
    manager = RunManager()

    first = await manager.create_or_reject("thread-1", multitask_strategy="reject")
    await manager.set_status(first.run_id, RunStatus.running)
    first.task = asyncio.create_task(asyncio.sleep(60))

    second = await manager.create_or_reject("thread-1", multitask_strategy="interrupt")

    assert first.abort_event.is_set()
    assert first.status == RunStatus.interrupted
    assert second.status == RunStatus.pending

    first.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first.task


@pytest.mark.asyncio
async def test_rollback_strategy_marks_existing_run_with_rollback_action():
    manager = RunManager()

    first = await manager.create_or_reject("thread-1", multitask_strategy="reject")
    await manager.set_status(first.run_id, RunStatus.running)
    first.task = asyncio.create_task(asyncio.sleep(60))

    second = await manager.create_or_reject("thread-1", multitask_strategy="rollback")

    assert first.abort_event.is_set()
    assert first.abort_action == "rollback"
    assert first.status == RunStatus.interrupted
    assert second.status == RunStatus.pending

    first.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first.task


@pytest.mark.asyncio
async def test_bind_thread_updates_record_thread_id():
    manager = RunManager()
    record = await manager.create_or_reject("placeholder-thread")

    await manager.bind_thread(record.run_id, "thread-real")

    latest = manager.get(record.run_id)
    assert latest is not None
    assert latest.thread_id == "thread-real"


@pytest.mark.asyncio
async def test_list_all_returns_runs_in_reverse_creation_order():
    manager = RunManager()
    first = await manager.create_or_reject("thread-1")
    second = await manager.create_or_reject("thread-2")

    records = await manager.list_all()

    assert [item.run_id for item in records] == [second.run_id, first.run_id]

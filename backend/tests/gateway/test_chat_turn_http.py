"""Tests for shared run HTTP helper semantics."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.gateway.services.chat_turn_http import (
    await_chat_turn_task,
    cancel_chat_turn_with_http_response,
    get_chat_turn_or_404,
    maybe_cancel_chat_turn_then_wait,
)
from src.runtime.chat_turns import ChatTurnRunManager, ChatTurnRunStatus
from src.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge


@pytest.mark.asyncio
async def test_get_run_or_404_enforces_optional_thread_scope() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record

    resolved = await get_chat_turn_or_404(manager, record.run_id)
    assert resolved.run_id == record.run_id

    with pytest.raises(HTTPException) as scoped_exc:
        await get_chat_turn_or_404(manager, record.run_id, thread_id="thread-2")
    assert scoped_exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_run_with_wait_returns_204_and_interrupts_task() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record
    assert await manager.transition_status(
        record.run_id,
        ChatTurnRunStatus.running,
        expected=(ChatTurnRunStatus.pending,),
    )
    record.task = asyncio.create_task(asyncio.sleep(60))

    response = await cancel_chat_turn_with_http_response(
        run_manager=manager,
        record=record,
        action="interrupt",
        wait=True,
    )

    assert response.status_code == 204
    assert record.status == ChatTurnRunStatus.interrupted


@pytest.mark.asyncio
async def test_cancel_run_raises_409_for_non_cancellable_run() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record
    assert await manager.transition_status(
        record.run_id,
        ChatTurnRunStatus.success,
        expected=(ChatTurnRunStatus.pending,),
    )

    with pytest.raises(HTTPException) as exc:
        await cancel_chat_turn_with_http_response(
            run_manager=manager,
            record=record,
            action="rollback",
            wait=False,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_maybe_cancel_then_wait_returns_none_without_action() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record

    response = await maybe_cancel_chat_turn_then_wait(
        run_manager=manager,
        record=record,
        action=None,
        wait=True,
    )

    assert response is None


@pytest.mark.asyncio
async def test_await_run_task_polls_status_when_task_handle_missing() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record
    record.task = None

    async def _finish() -> None:
        await asyncio.sleep(0.05)
        assert await manager.transition_status(
            record.run_id,
            ChatTurnRunStatus.success,
            expected=(ChatTurnRunStatus.pending,),
        )

    asyncio.create_task(_finish())
    latest = await await_chat_turn_task(
        record,
        run_manager=manager,
        timeout_seconds=1.0,
        poll_interval_seconds=0.01,
    )

    assert latest.status == ChatTurnRunStatus.success


@pytest.mark.asyncio
async def test_await_run_task_uses_stream_events_when_bridge_provided() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record
    record.task = None

    class EndAfterSuccessBridge(StreamBridge):
        async def publish(self, run_id: str, event: str, data) -> None:
            _ = run_id, event, data

        async def publish_end(self, run_id: str) -> None:
            _ = run_id

        async def subscribe(
            self,
            run_id: str,
            *,
            last_event_id: str | None = None,
            heartbeat_interval: float = 15.0,
        ):
            _ = run_id, last_event_id, heartbeat_interval
            yield HEARTBEAT_SENTINEL
            assert await manager.transition_status(
                record.run_id,
                ChatTurnRunStatus.success,
                expected=(ChatTurnRunStatus.pending,),
            )
            yield END_SENTINEL

    latest = await await_chat_turn_task(
        record,
        run_manager=manager,
        bridge=EndAfterSuccessBridge(),
        timeout_seconds=1.0,
        poll_interval_seconds=0.01,
    )

    assert latest.status == ChatTurnRunStatus.success


@pytest.mark.asyncio
async def test_await_run_task_stream_timeout_returns_504() -> None:
    manager = ChatTurnRunManager()
    record = (await manager.create_or_reject("thread-1")).record
    record.task = None

    class IdleBridge(StreamBridge):
        async def publish(self, run_id: str, event: str, data) -> None:
            _ = run_id, event, data

        async def publish_end(self, run_id: str) -> None:
            _ = run_id

        async def subscribe(
            self,
            run_id: str,
            *,
            last_event_id: str | None = None,
            heartbeat_interval: float = 15.0,
        ):
            _ = run_id, last_event_id, heartbeat_interval
            while True:
                yield HEARTBEAT_SENTINEL
                await asyncio.sleep(0)

    with pytest.raises(HTTPException) as exc_info:
        await await_chat_turn_task(
            record,
            run_manager=manager,
            bridge=IdleBridge(),
            timeout_seconds=1.0,
            poll_interval_seconds=0.01,
        )

    assert exc_info.value.status_code == 504

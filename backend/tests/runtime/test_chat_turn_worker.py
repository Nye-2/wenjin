"""Tests for run worker orchestration behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.application.handlers.thread_turn_handler import ThreadStreamDelta
from src.application.results import PreparedThreadTurn, ThreadTurnRequest
from src.runtime.chat_turns import ChatTurnRunManager, ChatTurnRunStatus, run_chat_turn
from src.runtime.stream_bridge import END_SENTINEL, MemoryStreamBridge


@dataclass
class _CancelledStreamRun:
    close_called: bool = False

    async def _iterate(self):
        if False:
            yield ThreadStreamDelta(kind="content", text="")

    def __aiter__(self):
        return self._iterate()

    async def wait_completed(self):  # noqa: ANN201
        raise asyncio.CancelledError()

    async def aclose(self) -> None:
        self.close_called = True


class _CancelledHandler:
    def __init__(self, stream_run: _CancelledStreamRun) -> None:
        self._stream_run = stream_run
        self.interruptions: list[bool] = []

    async def prepare_turn(self, request: ThreadTurnRequest, *, actor_id: str):  # noqa: ARG002
        thread = SimpleNamespace(
            id=request.thread_id or "thread-1",
            workspace_id=request.workspace_id or "ws-1",
            skill=None,
        )
        return PreparedThreadTurn(request=request, thread=thread)

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str):  # noqa: ARG002
        return self._stream_run

    async def handle_run_interruption(
        self,
        prepared: PreparedThreadTurn,  # noqa: ARG002
        *,
        rollback: bool,
    ) -> None:
        self.interruptions.append(rollback)


@dataclass
class _TimeoutStreamRun:
    async def _iterate(self):
        if False:
            yield ThreadStreamDelta(kind="content", text="")

    def __aiter__(self):
        return self._iterate()

    async def wait_completed(self):  # noqa: ANN201
        raise TimeoutError("upstream stream timeout")


class _TimeoutHandler:
    def __init__(self, stream_run: _TimeoutStreamRun) -> None:
        self._stream_run = stream_run
        self.interruptions: list[bool] = []

    async def prepare_turn(self, request: ThreadTurnRequest, *, actor_id: str):  # noqa: ARG002
        thread = SimpleNamespace(
            id=request.thread_id or "thread-1",
            workspace_id=request.workspace_id or "ws-1",
            skill=None,
        )
        return PreparedThreadTurn(request=request, thread=thread)

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str):  # noqa: ARG002
        return self._stream_run

    async def handle_run_interruption(
        self,
        prepared: PreparedThreadTurn,  # noqa: ARG002
        *,
        rollback: bool,
    ) -> None:
        self.interruptions.append(rollback)


@dataclass
class _AbortAwareStreamRun:
    async def _iterate(self):
        yield ThreadStreamDelta(kind="content", text="hello")

    def __aiter__(self):
        return self._iterate()

    async def wait_completed(self):  # noqa: ANN201
        return SimpleNamespace(
            assistant_message={
                "role": "assistant",
                "content": "hello",
            }
        )

    async def aclose(self) -> None:
        return None


class _AbortAwareHandler:
    def __init__(self, stream_run: _AbortAwareStreamRun) -> None:
        self._stream_run = stream_run
        self.interruptions: list[bool] = []

    async def prepare_turn(self, request: ThreadTurnRequest, *, actor_id: str):  # noqa: ARG002
        thread = SimpleNamespace(
            id=request.thread_id or "thread-1",
            workspace_id=request.workspace_id or "ws-1",
            skill=None,
        )
        return PreparedThreadTurn(request=request, thread=thread)

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str):  # noqa: ARG002
        return self._stream_run

    async def handle_run_interruption(
        self,
        prepared: PreparedThreadTurn,  # noqa: ARG002
        *,
        rollback: bool,
    ) -> None:
        self.interruptions.append(rollback)


@pytest.mark.asyncio
async def test_run_thread_turn_swallows_cancelled_error_and_marks_interrupted():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")
    stream_run = _CancelledStreamRun()
    handler = _CancelledHandler(stream_run)

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
    )

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()) as set_thread_status:
        await run_chat_turn(
            bridge,
            manager,
            record,
            handler=handler,  # type: ignore[arg-type]
            request=request,
            actor_id="user-1",
        )

    latest = await manager.get_or_load(record.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.interrupted
    assert stream_run.close_called is True
    assert handler.interruptions == [False]
    set_thread_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_thread_turn_reports_timeout_as_timeout_error_message():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")
    stream_run = _TimeoutStreamRun()
    handler = _TimeoutHandler(stream_run)

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
    )

    await run_chat_turn(
        bridge,
        manager,
        record,
        handler=handler,  # type: ignore[arg-type]
        request=request,
        actor_id="user-1",
    )

    latest = await manager.get_or_load(record.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.error
    assert latest.error is not None
    assert "timeout" in latest.error.lower()

    error_messages: list[str] = []
    async for item in bridge.subscribe(record.run_id):
        if item is END_SENTINEL:
            break
        if item.event == "error":
            payload = item.data if isinstance(item.data, dict) else {}
            error_messages.append(str(payload.get("error") or ""))

    assert "AI 响应超时，请稍后重试。" in error_messages
    assert handler.interruptions == []


@pytest.mark.asyncio
async def test_run_thread_turn_does_not_start_after_preflight_interrupt():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")
    stream_run = _AbortAwareStreamRun()
    handler = _AbortAwareHandler(stream_run)

    await manager.cancel(record.run_id, action="rollback")

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
    )

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()) as set_thread_status:
        await run_chat_turn(
            bridge,
            manager,
            record,
            handler=handler,  # type: ignore[arg-type]
            request=request,
            actor_id="user-1",
        )

    latest = await manager.get_or_load(record.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.interrupted
    assert handler.interruptions == []
    set_thread_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_thread_turn_skip_idle_status_when_other_run_is_active():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    first = await manager.create_or_reject("thread-1")
    await manager.set_status(first.run_id, ChatTurnRunStatus.running)
    second = await manager.create_or_reject("thread-1", multitask_strategy="interrupt")
    stream_run = _AbortAwareStreamRun()
    handler = _AbortAwareHandler(stream_run)

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
    )

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()) as set_thread_status:
        await run_chat_turn(
            bridge,
            manager,
            first,
            handler=handler,  # type: ignore[arg-type]
            request=request,
            actor_id="user-1",
        )

    latest_first = await manager.get_or_load(first.run_id, refresh=True)
    latest_second = await manager.get_or_load(second.run_id, refresh=True)
    assert latest_first is not None
    assert latest_second is not None
    assert latest_first.status == ChatTurnRunStatus.interrupted
    assert latest_second.status in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running)
    set_thread_status.assert_not_awaited()

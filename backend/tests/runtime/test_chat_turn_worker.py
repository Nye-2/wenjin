"""Tests for run worker orchestration behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.handlers.thread_turn_handler import (
    ThreadStreamDelta,
    ThreadTurnHandler,
)
from src.application.results import PreparedThreadTurn, ThreadTurnRequest
from src.contracts.billing import ThreadTurnBillingStatus
from src.runtime.chat_turns import (
    ChatTurnExecutionRenewal,
    ChatTurnRunManager,
    ChatTurnRunStatus,
    run_chat_turn,
)
from src.runtime.chat_turns.schemas import chat_turn_idempotency_key
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


class _FailMetadataBridge(MemoryStreamBridge):
    async def publish(self, run_id: str, event: str, data) -> None:  # noqa: ANN001
        if event == "metadata":
            raise RuntimeError("metadata publish failed")
        await super().publish(run_id, event, data)


class _LeaseBlockingStreamRun:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.close_called = False

    async def _iterate(self):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()
        if False:  # pragma: no cover
            yield ThreadStreamDelta(kind="content", text="")

    def __aiter__(self):
        return self._iterate()

    async def wait_completed(self):  # noqa: ANN201
        raise AssertionError("lost lease must cancel the stream")

    async def aclose(self) -> None:
        self.close_called = True


def _billing_handler(
    *,
    status: ThreadTurnBillingStatus,
) -> tuple[ThreadTurnHandler, SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        user_id="user-1",
        model="gpt-5.6-terra",
        message_count=0,
    )
    assistant = None
    if status == ThreadTurnBillingStatus.SETTLED:
        assistant = SimpleNamespace(
            id="assistant-1",
            role="assistant",
            content="replayed answer",
            sequence_index=1,
            timestamp=datetime(2026, 7, 17, tzinfo=UTC),
            metadata_json={"billing": {"credits_charged": 2}},
            blocks=[
                SimpleNamespace(
                    payload_json={"kind": "text", "content": "replayed answer"}
                )
            ],
        )
    authorization = SimpleNamespace(
        billing=SimpleNamespace(
            id="billing-1",
            status=status,
            user_message_id="user-message-1",
        ),
        user_message=(
            SimpleNamespace(id="user-message-1")
            if status == ThreadTurnBillingStatus.AUTHORIZED
            else None
        ),
        assistant_message=assistant,
    )
    thread_service = SimpleNamespace(
        get_or_create_thread=AsyncMock(return_value=thread),
        list_thread_messages=AsyncMock(return_value=[]),
        set_title_if_empty=AsyncMock(),
    )
    billing_gateway = SimpleNamespace(
        authorize=AsyncMock(return_value=authorization),
        complete=AsyncMock(),
        release=AsyncMock(),
        rollback=AsyncMock(),
    )
    handler = ThreadTurnHandler(
        thread_service=thread_service,
        billing_gateway=billing_gateway,
    )
    return handler, thread, thread_service, billing_gateway


@pytest.mark.asyncio
async def test_run_thread_turn_swallows_cancelled_error_and_marks_interrupted():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = (await manager.create_or_reject("thread-1")).record
    stream_run = _CancelledStreamRun()
    handler = _CancelledHandler(stream_run)

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
        turn_idempotency_key="test-cancelled-turn",
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
    record = (await manager.create_or_reject("thread-1")).record
    stream_run = _TimeoutStreamRun()
    handler = _TimeoutHandler(stream_run)

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
        turn_idempotency_key="test-timeout-turn",
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
async def test_run_thread_turn_fails_closed_without_stable_request_identity():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = (await manager.create_or_reject("thread-1")).record
    handler = SimpleNamespace(prepare_turn=AsyncMock())

    await run_chat_turn(
        bridge,
        manager,
        record,
        handler=handler,  # type: ignore[arg-type]
        request=ThreadTurnRequest(
            message="hello",
            workspace_id="ws-1",
            thread_id="thread-1",
        ),
        actor_id="user-1",
    )

    latest = await manager.get_or_load(record.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.error
    assert latest.error == "Chat turn is missing its stable request identity"
    handler.prepare_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_execution_lease_fences_old_worker_without_ending_stream() -> None:
    manager = ChatTurnRunManager(execution_lease_seconds=0.06)
    bridge = MemoryStreamBridge()
    record = (await manager.create_or_reject("thread-1")).record
    stream_run = _LeaseBlockingStreamRun()
    handler = _CancelledHandler(stream_run)  # type: ignore[arg-type]
    original_renew = manager.renew_execution_claim

    async def lose_claim(run_id: str, owner: str) -> ChatTurnExecutionRenewal:
        latest = manager.get(run_id)
        assert latest is not None
        latest.execution_owner = "replacement-worker"
        return ChatTurnExecutionRenewal.lost

    manager.renew_execution_claim = lose_claim  # type: ignore[method-assign]
    try:
        await run_chat_turn(
            bridge,
            manager,
            record,
            handler=handler,  # type: ignore[arg-type]
            request=ThreadTurnRequest(
                message="hello",
                workspace_id="ws-1",
                thread_id="thread-1",
                turn_idempotency_key="chat-turn:lease-loss",
            ),
            actor_id="user-1",
        )
    finally:
        manager.renew_execution_claim = original_renew  # type: ignore[method-assign]

    latest = manager.get(record.run_id)
    assert latest is not None
    assert latest.status is ChatTurnRunStatus.running
    assert latest.execution_owner == "replacement-worker"
    assert stream_run.started.is_set()
    assert stream_run.cancelled.is_set()
    assert stream_run.close_called is True
    assert handler.interruptions == []
    assert bridge._streams[record.run_id].ended is False


@pytest.mark.asyncio
async def test_execution_lease_unavailability_retries_without_terminal_effects() -> None:
    manager = ChatTurnRunManager(execution_lease_seconds=0.06)
    bridge = MemoryStreamBridge()
    record = (await manager.create_or_reject("thread-1")).record
    stream_run = _LeaseBlockingStreamRun()
    handler = _CancelledHandler(stream_run)  # type: ignore[arg-type]
    original_renew = manager.renew_execution_claim

    async def fail_renewal(
        run_id: str,
        owner: str,
    ) -> ChatTurnExecutionRenewal:
        _ = run_id, owner
        return ChatTurnExecutionRenewal.retryable

    manager.renew_execution_claim = fail_renewal  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="Execution lease unavailable"):
            await run_chat_turn(
                bridge,
                manager,
                record,
                handler=handler,  # type: ignore[arg-type]
                request=ThreadTurnRequest(
                    message="hello",
                    workspace_id="ws-1",
                    thread_id="thread-1",
                    turn_idempotency_key="chat-turn:lease-unavailable",
                ),
                actor_id="user-1",
            )
    finally:
        manager.renew_execution_claim = original_renew  # type: ignore[method-assign]

    latest = manager.get(record.run_id)
    assert latest is not None
    assert latest.status is ChatTurnRunStatus.running
    assert latest.execution_owner is None
    assert stream_run.started.is_set()
    assert stream_run.cancelled.is_set()
    assert stream_run.close_called is True
    assert handler.interruptions == []
    assert bridge._streams[record.run_id].ended is False


@pytest.mark.asyncio
async def test_run_thread_turn_does_not_start_after_preflight_interrupt():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = (await manager.create_or_reject("thread-1")).record
    stream_run = _AbortAwareStreamRun()
    handler = _AbortAwareHandler(stream_run)

    await manager.cancel(record.run_id, action="rollback")

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
        turn_idempotency_key="test-preflight-interrupt",
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
    first = (await manager.create_or_reject("thread-1")).record
    assert await manager.transition_status(
        first.run_id,
        ChatTurnRunStatus.running,
        expected=(ChatTurnRunStatus.pending,),
    )
    second = (
        await manager.create_or_reject(
            "thread-1",
            multitask_strategy="interrupt",
        )
    ).record
    stream_run = _AbortAwareStreamRun()
    handler = _AbortAwareHandler(stream_run)

    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
        turn_idempotency_key="test-concurrent-interrupt",
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


@pytest.mark.asyncio
async def test_metadata_publish_failure_releases_authorization() -> None:
    manager = ChatTurnRunManager()
    bridge = _FailMetadataBridge()
    record = (await manager.create_or_reject("thread-1")).record
    handler, _, _, billing_gateway = _billing_handler(
        status=ThreadTurnBillingStatus.AUTHORIZED
    )
    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
        turn_idempotency_key=chat_turn_idempotency_key(
            "request-metadata-failure",
            actor_id="user-1",
        ),
    )

    with patch(
        "src.application.handlers.thread_turn_handler.set_thread_status",
        new_callable=AsyncMock,
    ):
        await run_chat_turn(
            bridge,
            manager,
            record,
            handler=handler,
            request=request,
            actor_id="user-1",
        )

    latest = await manager.get_or_load(record.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.error
    billing_gateway.authorize.assert_awaited_once_with(
        thread=handler.thread_service.get_or_create_thread.return_value,
        content="hello",
        metadata=None,
        idempotency_key=chat_turn_idempotency_key(
            "request-metadata-failure",
            actor_id="user-1",
        ),
    )
    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn transport failed",
    )
    billing_gateway.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_loss_replay_recovers_settled_turn_without_provider_or_charge() -> None:
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = (await manager.create_or_reject("thread-1")).record
    assert await manager.transition_status(
        record.run_id,
        ChatTurnRunStatus.running,
        expected=(ChatTurnRunStatus.pending,),
    )
    handler, thread, thread_service, billing_gateway = _billing_handler(
        status=ThreadTurnBillingStatus.SETTLED
    )
    request = ThreadTurnRequest(
        message="hello",
        workspace_id="ws-1",
        thread_id="thread-1",
        metadata={
            "source": "test",
        },
        turn_idempotency_key=chat_turn_idempotency_key(
            "request-replay-1",
            actor_id="user-1",
        ),
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ),
        patch(
            "src.application.handlers.thread_turn_handler.stream_thread_response",
            new_callable=MagicMock,
        ) as provider_stream,
    ):
        await run_chat_turn(
            bridge,
            manager,
            record,
            handler=handler,
            request=request,
            actor_id="user-1",
        )

    latest = await manager.get_or_load(record.run_id, refresh=True)
    assert latest is not None
    assert latest.status == ChatTurnRunStatus.success
    billing_gateway.authorize.assert_awaited_once_with(
        thread=thread,
        content="hello",
        metadata={"source": "test"},
        idempotency_key=chat_turn_idempotency_key(
            "request-replay-1",
            actor_id="user-1",
        ),
    )
    provider_stream.assert_not_called()
    thread_service.list_thread_messages.assert_not_awaited()
    billing_gateway.complete.assert_not_awaited()
    billing_gateway.release.assert_not_awaited()

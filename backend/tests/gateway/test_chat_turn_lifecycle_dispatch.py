"""Tests for run lifecycle dispatch mode selection."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.application.results import ThreadTurnRequest
from src.gateway.services.chat_turn_lifecycle import launch_chat_turn, sse_consumer
from src.runtime.chat_turns import ChatTurnDisconnectMode, ChatTurnRunManager, ChatTurnRunRecord, ChatTurnRunStatus
from src.runtime.stream_bridge import END_SENTINEL, StreamBridge


class FakeBridge(StreamBridge):
    def __init__(self) -> None:
        self.events: list[tuple[str, str, Any]] = []

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        self.events.append((run_id, event, data))

    async def publish_end(self, run_id: str) -> None:
        self.events.append((run_id, "__end__", None))

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ):
        if False:  # pragma: no cover
            yield run_id, last_event_id, heartbeat_interval

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        return None


@dataclass
class _DummyHandler:
    async def preflight_stream_turn(self, request: ThreadTurnRequest, *, actor_id: str) -> None:
        _ = request, actor_id


class _DummyExecuteRunTask:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def apply_async(self, *, args: list[Any], queue: str):
        self.calls.append({"args": list(args), "queue": queue})
        return SimpleNamespace(id="celery-task-1")


@dataclass
class _FakeRequest:
    headers: dict[str, str]

    async def is_disconnected(self) -> bool:
        return False


async def _launch_for_test(
    *,
    manager: ChatTurnRunManager,
    bridge: FakeBridge,
    handler: _DummyHandler,
) -> None:
    await launch_chat_turn(
        handler=handler,  # type: ignore[arg-type]
        run_manager=manager,
        bridge=bridge,
        actor_id="user-1",
        run_thread_id="thread-1",
        turn_request=ThreadTurnRequest(message="hello", thread_id="thread-1"),
        assistant_id="thread",
        metadata={},
        kwargs={},
        on_disconnect=ChatTurnDisconnectMode.cancel.value,
        multitask_strategy="reject",
    )


@pytest.mark.asyncio
async def test_launch_thread_run_dispatches_to_celery_worker(monkeypatch):
    import src.gateway.services.chat_turn_lifecycle as run_lifecycle_module
    import src.task.tasks as task_module

    manager = ChatTurnRunManager()
    bridge = FakeBridge()
    handler = _DummyHandler()
    dummy_task = _DummyExecuteRunTask()
    scheduled: list[Any] = []

    def _fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return SimpleNamespace()

    monkeypatch.setattr(run_lifecycle_module.celery_settings, "enabled", True)
    monkeypatch.setattr(run_lifecycle_module.redis_settings, "enabled", True)
    monkeypatch.setattr(task_module, "process_chat_turn", dummy_task)
    monkeypatch.setattr(run_lifecycle_module.asyncio, "create_task", _fake_create_task)

    record = await launch_chat_turn(
        handler=handler,  # type: ignore[arg-type]
        run_manager=manager,
        bridge=bridge,
        actor_id="user-1",
        run_thread_id="thread-1",
        turn_request=ThreadTurnRequest(message="hello", thread_id="thread-1"),
        assistant_id="thread",
        metadata={},
        kwargs={},
        on_disconnect=ChatTurnDisconnectMode.cancel.value,
        multitask_strategy="reject",
    )

    assert record.task is None
    assert len(dummy_task.calls) == 1
    assert dummy_task.calls[0]["queue"] == "default"
    assert dummy_task.calls[0]["args"][0] == record.run_id
    assert any(event == "run_queued" for _, event, _ in bridge.events)
    assert record.metadata.get("dispatch_mode") == "celery_worker"
    assert record.metadata.get("worker_task_id") == "celery-task-1"
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_launch_thread_run_fails_when_celery_disabled(monkeypatch):
    import src.gateway.services.chat_turn_lifecycle as run_lifecycle_module

    manager = ChatTurnRunManager()
    bridge = FakeBridge()
    handler = _DummyHandler()

    monkeypatch.setattr(run_lifecycle_module.celery_settings, "enabled", False)
    monkeypatch.setattr(run_lifecycle_module.redis_settings, "enabled", True)

    with pytest.raises(HTTPException) as exc_info:
        await _launch_for_test(
            manager=manager,
            bridge=bridge,
            handler=handler,
        )

    assert exc_info.value.status_code == 503
    records = await manager.list_all()
    assert records
    assert records[0].status == ChatTurnRunStatus.error
    assert any(event == "error" for _, event, _ in bridge.events)
    assert any(event == "__end__" for _, event, _ in bridge.events)


@pytest.mark.asyncio
async def test_launch_thread_run_fails_when_redis_disabled(monkeypatch):
    import src.gateway.services.chat_turn_lifecycle as run_lifecycle_module

    manager = ChatTurnRunManager()
    bridge = FakeBridge()
    handler = _DummyHandler()

    monkeypatch.setattr(run_lifecycle_module.celery_settings, "enabled", True)
    monkeypatch.setattr(run_lifecycle_module.redis_settings, "enabled", False)

    with pytest.raises(HTTPException) as exc_info:
        await _launch_for_test(
            manager=manager,
            bridge=bridge,
            handler=handler,
        )

    assert exc_info.value.status_code == 503
    records = await manager.list_all()
    assert records
    assert records[0].status == ChatTurnRunStatus.error
    assert any(event == "error" for _, event, _ in bridge.events)
    assert any(event == "__end__" for _, event, _ in bridge.events)


@pytest.mark.asyncio
async def test_sse_consumer_does_not_cancel_after_end_with_stale_record_state():
    class EndOnlyBridge(StreamBridge):
        async def publish(self, run_id: str, event: str, data: Any) -> None:
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
            yield END_SENTINEL

        async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
            _ = run_id, delay

    record = ChatTurnRunRecord(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=ChatTurnRunStatus.pending,
        on_disconnect=ChatTurnDisconnectMode.cancel,
    )
    manager = SimpleNamespace(
        cancel=AsyncMock(return_value=True),
        get_or_load=AsyncMock(return_value=record),
    )
    request = _FakeRequest(headers={})
    bridge = EndOnlyBridge()

    frames = []
    async for frame in sse_consumer(
        bridge=bridge,
        record=record,
        request=request,  # type: ignore[arg-type]
        run_manager=manager,  # type: ignore[arg-type]
    ):
        frames.append(frame)

    assert frames and frames[-1].startswith("event: end")
    manager.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_sse_consumer_emits_error_frame_and_skips_cancel_on_subscription_failure():
    class FailingBridge(StreamBridge):
        async def publish(self, run_id: str, event: str, data: Any) -> None:
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
            raise RuntimeError("redis timeout")
            if False:  # pragma: no cover
                yield None

        async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
            _ = run_id, delay

    record = ChatTurnRunRecord(
        run_id="run-2",
        thread_id="thread-1",
        assistant_id=None,
        status=ChatTurnRunStatus.pending,
        on_disconnect=ChatTurnDisconnectMode.cancel,
    )
    manager = SimpleNamespace(
        cancel=AsyncMock(return_value=True),
        get_or_load=AsyncMock(return_value=record),
    )
    request = _FakeRequest(headers={})
    bridge = FailingBridge()

    frames = []
    async for frame in sse_consumer(
        bridge=bridge,
        record=record,
        request=request,  # type: ignore[arg-type]
        run_manager=manager,  # type: ignore[arg-type]
    ):
        frames.append(frame)

    assert frames and any(frame.startswith("event: error") for frame in frames)
    manager.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_sse_consumer_disconnect_grace_skips_cancel_after_run_completes(monkeypatch):
    import src.gateway.services.chat_turn_lifecycle as run_lifecycle_module

    class ContentBridge(StreamBridge):
        async def publish(self, run_id: str, event: str, data: Any) -> None:
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
            yield SimpleNamespace(id="1-0", event="content", data={"type": "content", "content": "hi"})

        async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
            _ = run_id, delay

    class DisconnectingRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self._calls = 0

        async def is_disconnected(self) -> bool:
            self._calls += 1
            return self._calls >= 2

    running = ChatTurnRunRecord(
        run_id="run-3",
        thread_id="thread-1",
        assistant_id=None,
        status=ChatTurnRunStatus.running,
        on_disconnect=ChatTurnDisconnectMode.cancel,
    )
    succeeded = ChatTurnRunRecord(
        run_id="run-3",
        thread_id="thread-1",
        assistant_id=None,
        status=ChatTurnRunStatus.success,
        on_disconnect=ChatTurnDisconnectMode.cancel,
    )
    manager = SimpleNamespace(
        cancel=AsyncMock(return_value=True),
        get_or_load=AsyncMock(side_effect=[running, succeeded]),
    )
    request = DisconnectingRequest()
    bridge = ContentBridge()

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        run_lifecycle_module.settings,
        "runtime_disconnect_cancel_grace_seconds",
        0.2,
    )
    monkeypatch.setattr(run_lifecycle_module.asyncio, "sleep", _fake_sleep)

    frames = []
    async for frame in sse_consumer(
        bridge=bridge,
        record=running,
        request=request,  # type: ignore[arg-type]
        run_manager=manager,  # type: ignore[arg-type]
    ):
        frames.append(frame)

    assert frames and any(frame.startswith("event: content") for frame in frames)
    assert sleep_calls == [0.2]
    manager.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_sse_consumer_disconnect_grace_cancels_when_still_running(monkeypatch):
    import src.gateway.services.chat_turn_lifecycle as run_lifecycle_module

    class ContentBridge(StreamBridge):
        async def publish(self, run_id: str, event: str, data: Any) -> None:
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
            yield SimpleNamespace(id="1-0", event="content", data={"type": "content", "content": "hi"})

        async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
            _ = run_id, delay

    class DisconnectingRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self._calls = 0

        async def is_disconnected(self) -> bool:
            self._calls += 1
            return self._calls >= 2

    running = ChatTurnRunRecord(
        run_id="run-4",
        thread_id="thread-1",
        assistant_id=None,
        status=ChatTurnRunStatus.running,
        on_disconnect=ChatTurnDisconnectMode.cancel,
    )
    manager = SimpleNamespace(
        cancel=AsyncMock(return_value=True),
        get_or_load=AsyncMock(side_effect=[running, running]),
    )
    request = DisconnectingRequest()
    bridge = ContentBridge()

    async def _fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(
        run_lifecycle_module.settings,
        "runtime_disconnect_cancel_grace_seconds",
        0.1,
    )
    monkeypatch.setattr(run_lifecycle_module.asyncio, "sleep", _fake_sleep)

    async for _ in sse_consumer(
        bridge=bridge,
        record=running,
        request=request,  # type: ignore[arg-type]
        run_manager=manager,  # type: ignore[arg-type]
    ):
        pass

    manager.cancel.assert_awaited_once_with("run-4")

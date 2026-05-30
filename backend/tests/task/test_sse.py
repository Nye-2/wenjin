"""Tests for task SSE stream lifecycle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.academic.cache.redis_client import redis_client
from src.task.sse import TaskEventStreamUnavailable, create_task_sse_stream


class _FailingPubSub:
    def __init__(self) -> None:
        self.close = AsyncMock()
        self.unsubscribe = AsyncMock()

    async def subscribe(self, _channel: str) -> None:
        raise RuntimeError("Too many connections")


class _IdlePubSub:
    def __init__(self) -> None:
        self.subscribe = AsyncMock()
        self.unsubscribe = AsyncMock()
        self.close = AsyncMock()
        self.get_message = AsyncMock(return_value=None)


class _ClientContext:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


@pytest.mark.asyncio
async def test_create_task_sse_stream_closes_pubsub_on_subscribe_failure(monkeypatch):
    pubsub = _FailingPubSub()
    create_pubsub = AsyncMock(return_value=pubsub)

    monkeypatch.setattr(redis_client, "create_pubsub", create_pubsub)

    with pytest.raises(TaskEventStreamUnavailable):
        await create_task_sse_stream("task-1")

    create_pubsub.assert_awaited_once()
    pubsub.close.assert_awaited_once()
    pubsub.unsubscribe.assert_not_called()


@pytest.mark.asyncio
async def test_create_task_sse_stream_wraps_pubsub_creation_failure(monkeypatch):
    create_pubsub = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    monkeypatch.setattr(redis_client, "create_pubsub", create_pubsub)

    with pytest.raises(TaskEventStreamUnavailable):
        await create_task_sse_stream("task-create-fail")

    create_pubsub.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_task_sse_stream_falls_back_to_dataservice_snapshot_and_closes_on_terminal_state(monkeypatch):
    task_id = "task-2"
    pubsub = _IdlePubSub()
    create_pubsub = AsyncMock(return_value=pubsub)
    monkeypatch.setattr(redis_client, "create_pubsub", create_pubsub)

    now = datetime.now(UTC)
    mock_store = AsyncMock()
    mock_store.get_task_state = AsyncMock(return_value=None)
    mock_store.get_task_record = AsyncMock(
        return_value=SimpleNamespace(
            id=task_id,
            status="success",
            progress=100,
            message="已完成",
            runtime_state={"current_phase": "finalize"},
            result={"ok": True},
            error=None,
            completed_at=now,
            started_at=now,
            created_at=now,
        )
    )
    dataservice = AsyncMock()

    with (
        patch(
            "src.dataservice_client.provider.dataservice_client",
            return_value=_ClientContext(dataservice),
        ) as dataservice_client,
        patch("src.task.store.TaskStore", return_value=mock_store),
    ):
        stream = await create_task_sse_stream(task_id)
        event = await anext(stream)
        payload = json.loads(event.removeprefix("data: ").strip())

        assert payload["task_id"] == task_id
        assert payload["status"] == "success"
        assert payload["current_step"] == "finalize"
        assert payload["result"] == {"ok": True}

        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    create_pubsub.assert_awaited_once()
    dataservice_client.assert_called_once()
    pubsub.subscribe.assert_awaited_once_with(f"task_progress:{task_id}")
    pubsub.get_message.assert_not_awaited()
    pubsub.unsubscribe.assert_awaited_once_with(f"task_progress:{task_id}")
    pubsub.close.assert_awaited_once()
    mock_store.get_task_state.assert_awaited_once_with(task_id)
    mock_store.get_task_record.assert_awaited_once_with(task_id)


@pytest.mark.asyncio
async def test_create_task_sse_stream_injects_task_id_for_pubsub_payload(monkeypatch):
    task_id = "task-3"
    pubsub = _IdlePubSub()
    pubsub.get_message = AsyncMock(
        side_effect=[
            {
                "type": "message",
                "data": json.dumps({"status": "success", "progress": 100}),
            }
        ]
    )
    create_pubsub = AsyncMock(return_value=pubsub)
    monkeypatch.setattr(redis_client, "create_pubsub", create_pubsub)

    mock_store = AsyncMock()
    mock_store.get_task_state = AsyncMock(return_value=None)
    mock_store.get_task_record = AsyncMock(return_value=None)
    dataservice = AsyncMock()

    with (
        patch(
            "src.dataservice_client.provider.dataservice_client",
            return_value=_ClientContext(dataservice),
        ),
        patch("src.task.store.TaskStore", return_value=mock_store),
    ):
        stream = await create_task_sse_stream(task_id)
        event = await anext(stream)
        payload = json.loads(event.removeprefix("data: ").strip())

        assert payload["task_id"] == task_id
        assert payload["status"] == "success"
        assert payload["progress"] == 100

        with pytest.raises(StopAsyncIteration):
            await anext(stream)

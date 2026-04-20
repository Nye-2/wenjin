"""Tests for workspace event stream lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import src.workspace_events as workspace_events
from src.workspace_events import (
    WorkspaceEventStreamUnavailable,
    stream_workspace_events,
)


class _FailingPubSub:
    def __init__(self) -> None:
        self.close = AsyncMock()
        self.unsubscribe = AsyncMock()

    async def subscribe(self, _channel: str) -> None:
        raise RuntimeError("Too many connections")


@pytest.mark.asyncio
async def test_stream_workspace_events_closes_pubsub_on_subscribe_failure(monkeypatch):
    pubsub = _FailingPubSub()
    create_pubsub = AsyncMock(return_value=pubsub)

    monkeypatch.setattr(workspace_events.redis_client, "create_pubsub", create_pubsub)

    with pytest.raises(WorkspaceEventStreamUnavailable):
        await stream_workspace_events("ws-1")

    create_pubsub.assert_awaited_once()
    pubsub.close.assert_awaited_once()
    pubsub.unsubscribe.assert_not_called()


@pytest.mark.asyncio
async def test_stream_workspace_events_wraps_pubsub_initialization_failure(monkeypatch):
    create_pubsub = AsyncMock(side_effect=RuntimeError("Redis unavailable"))

    monkeypatch.setattr(workspace_events.redis_client, "create_pubsub", create_pubsub)

    with pytest.raises(WorkspaceEventStreamUnavailable):
        await stream_workspace_events("ws-1")

    create_pubsub.assert_awaited_once()


class _RuntimeFailingPubSub:
    def __init__(self) -> None:
        self.close = AsyncMock()
        self.unsubscribe = AsyncMock()
        self._calls = 0

    async def subscribe(self, _channel: str) -> None:
        return None

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool = False,
        timeout: float = 0.0,
    ):
        self._calls += 1
        if self._calls == 1:
            return {"type": "message", "data": '{"type":"workspace.refresh"}'}
        raise RuntimeError("Redis connection dropped")


class _PlainTextRuntimeFailingPubSub:
    def __init__(self) -> None:
        self.close = AsyncMock()
        self.unsubscribe = AsyncMock()
        self._calls = 0

    async def subscribe(self, _channel: str) -> None:
        return None

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool = False,
        timeout: float = 0.0,
    ):
        self._calls += 1
        if self._calls == 1:
            return {"type": "message", "data": "workspace:raw:ping"}
        raise RuntimeError("Redis connection dropped")


@pytest.mark.asyncio
async def test_stream_workspace_events_runtime_failure_ends_stream_cleanly(monkeypatch):
    pubsub = _RuntimeFailingPubSub()
    create_pubsub = AsyncMock(return_value=pubsub)

    monkeypatch.setattr(workspace_events.redis_client, "create_pubsub", create_pubsub)

    stream = await stream_workspace_events("ws-1")
    events: list[str] = []
    async for item in stream:
        events.append(item)

    assert len(events) == 2
    assert events[0].startswith('data: {"type": "workspace.ready", "workspace_id": "ws-1"')
    assert events[1] == 'data: {"type": "workspace.refresh"}\n\n'
    pubsub.unsubscribe.assert_awaited_once_with("workspace:ws-1:events")
    pubsub.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_workspace_events_encodes_plain_text_messages(monkeypatch):
    pubsub = _PlainTextRuntimeFailingPubSub()
    create_pubsub = AsyncMock(return_value=pubsub)

    monkeypatch.setattr(workspace_events.redis_client, "create_pubsub", create_pubsub)

    stream = await stream_workspace_events("ws-1")
    events: list[str] = []
    async for item in stream:
        events.append(item)

    assert len(events) == 2
    assert events[0].startswith('data: {"type": "workspace.ready", "workspace_id": "ws-1"')
    assert events[1] == 'data: "workspace:raw:ping"\n\n'
    pubsub.unsubscribe.assert_awaited_once_with("workspace:ws-1:events")
    pubsub.close.assert_awaited_once()

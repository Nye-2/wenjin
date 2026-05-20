"""Tests for EventBus using mocked Redis pub/sub."""

import json
from unittest.mock import AsyncMock

import pytest

from src.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_returns_count():
    """publish() returns the subscriber count from Redis PUBLISH."""
    redis = AsyncMock()
    redis.publish = AsyncMock(return_value=3)

    bus = EventBus(redis)
    count = await bus.publish("channel-1", {"event": "test"})

    assert count == 3
    redis.publish.assert_called_once_with("channel-1", json.dumps({"event": "test"}))


@pytest.mark.asyncio
async def test_subscribe_registers_handler():
    """subscribe() populates the handler list for the channel."""
    redis = AsyncMock()
    bus = EventBus(redis)

    async def handler(event):
        pass

    bus.subscribe("my-channel", handler)

    assert "my-channel" in bus._handlers
    assert handler in bus._handlers["my-channel"]
    assert len(bus._handlers["my-channel"]) == 1

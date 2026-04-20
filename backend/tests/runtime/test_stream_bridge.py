"""Tests for in-memory stream bridge behavior."""

from __future__ import annotations

import pytest

from src.runtime.stream_bridge import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    MemoryStreamBridge,
)


@pytest.mark.asyncio
async def test_memory_stream_bridge_replays_from_last_event_id():
    bridge = MemoryStreamBridge(queue_maxsize=16)
    run_id = "run-1"

    await bridge.publish(run_id, "content", {"n": 1})
    await bridge.publish(run_id, "content", {"n": 2})
    await bridge.publish_end(run_id)

    consumed = []
    async for item in bridge.subscribe(run_id):
        consumed.append(item)

    assert len(consumed) == 3
    assert consumed[0].data == {"n": 1}
    assert consumed[1].data == {"n": 2}
    assert consumed[2] is END_SENTINEL

    replayed = []
    async for item in bridge.subscribe(run_id, last_event_id=consumed[0].id):
        replayed.append(item)

    assert len(replayed) == 2
    assert replayed[0].data == {"n": 2}
    assert replayed[1] is END_SENTINEL


@pytest.mark.asyncio
async def test_memory_stream_bridge_emits_heartbeat_for_idle_subscriber():
    bridge = MemoryStreamBridge(queue_maxsize=4)
    run_id = "run-heartbeat"

    subscriber = bridge.subscribe(run_id, heartbeat_interval=0.01)
    heartbeat = await anext(subscriber)
    assert heartbeat is HEARTBEAT_SENTINEL

    await bridge.publish_end(run_id)
    end = await anext(subscriber)
    assert end is END_SENTINEL

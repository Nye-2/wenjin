"""In-process stream bridge with bounded replay buffer."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .base import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge, StreamEvent

logger = logging.getLogger(__name__)


@dataclass
class _RunStream:
    events: list[StreamEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    ended: bool = False
    start_offset: int = 0


class MemoryStreamBridge(StreamBridge):
    """In-memory event bridge with Last-Event-ID replay support."""

    def __init__(self, *, queue_maxsize: int = 512) -> None:
        self._maxsize = max(1, int(queue_maxsize))
        self._streams: dict[str, _RunStream] = {}
        self._counters: dict[str, int] = {}

    def _get_or_create_stream(self, run_id: str) -> _RunStream:
        if run_id not in self._streams:
            self._streams[run_id] = _RunStream()
            self._counters[run_id] = 0
        return self._streams[run_id]

    def _next_id(self, run_id: str) -> str:
        self._counters[run_id] = self._counters.get(run_id, 0) + 1
        timestamp_ms = int(time.time() * 1000)
        sequence = self._counters[run_id] - 1
        return f"{timestamp_ms}-{sequence}"

    def _resolve_start_offset(self, stream: _RunStream, last_event_id: str | None) -> int:
        if last_event_id is None:
            return stream.start_offset
        for index, item in enumerate(stream.events):
            if item.id == last_event_id:
                return stream.start_offset + index + 1
        if stream.events:
            logger.warning(
                "last_event_id=%s not found in retained stream; replaying earliest buffered event",
                last_event_id,
            )
        return stream.start_offset

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        stream = self._get_or_create_stream(run_id)
        item = StreamEvent(id=self._next_id(run_id), event=event, data=data)
        async with stream.condition:
            stream.events.append(item)
            if len(stream.events) > self._maxsize:
                overflow = len(stream.events) - self._maxsize
                del stream.events[:overflow]
                stream.start_offset += overflow
            stream.condition.notify_all()

    async def publish_end(self, run_id: str) -> None:
        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            stream.ended = True
            stream.condition.notify_all()

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            next_offset = self._resolve_start_offset(stream, last_event_id)

        while True:
            async with stream.condition:
                if next_offset < stream.start_offset:
                    logger.warning(
                        "subscriber lagged beyond retained buffer for run=%s; resetting offset=%s",
                        run_id,
                        stream.start_offset,
                    )
                    next_offset = stream.start_offset

                local_index = next_offset - stream.start_offset
                if 0 <= local_index < len(stream.events):
                    item = stream.events[local_index]
                    next_offset += 1
                elif stream.ended:
                    item = END_SENTINEL
                else:
                    try:
                        await asyncio.wait_for(
                            stream.condition.wait(),
                            timeout=heartbeat_interval,
                        )
                    except TimeoutError:
                        item = HEARTBEAT_SENTINEL
                    else:
                        continue

            if item is END_SENTINEL:
                yield END_SENTINEL
                return
            yield item

    async def close(self) -> None:
        self._streams.clear()
        self._counters.clear()

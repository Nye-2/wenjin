"""Abstract stream bridge protocol for run-stream fanout."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """Single stream event frame used by SSE consumers."""

    id: str
    event: str
    data: Any


HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)


class StreamBridge(abc.ABC):
    """Producer/consumer bridge for run stream events."""

    @abc.abstractmethod
    async def publish(self, run_id: str, event: str, data: Any) -> None:
        """Publish one event for ``run_id``."""

    @abc.abstractmethod
    async def publish_end(self, run_id: str) -> None:
        """Signal that ``run_id`` has finished producing events."""

    @abc.abstractmethod
    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        """Subscribe to events for ``run_id`` with optional replay."""

    async def close(self) -> None:
        """Release backend resources (default no-op)."""
        return None

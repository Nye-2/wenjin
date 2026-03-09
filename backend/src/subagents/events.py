"""SSE event streaming for subagent execution."""

import queue
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Iterator


class SubagentEventType(Enum):
    """Event types for subagent execution."""
    STARTED = "started"
    RUNNING = "running"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentEvent:
    """A single event from subagent execution."""
    type: SubagentEventType
    task_id: str
    subagent_type: str
    message: str
    data: dict[str, Any] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventStream:
    """Thread-safe event stream for SSE."""

    def __init__(self):
        self._queue: queue.Queue[SubagentEvent | None] = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()

    def push(self, event: SubagentEvent) -> None:
        """Push an event to the stream."""
        with self._lock:
            if not self._closed:
                self._queue.put(event)

    def close(self) -> None:
        """Close the stream, signaling no more events."""
        with self._lock:
            self._closed = True
            self._queue.put(None)

    @property
    def is_closed(self) -> bool:
        """Check if the stream is closed."""
        with self._lock:
            return self._closed

    def iterate(self, timeout: float = 30.0) -> Iterator[SubagentEvent]:
        """Iterate over events until stream is closed or timeout.

        Yields:
            SubagentEvent instances

        Raises:
            TimeoutError: If no event received within timeout
        """
        while True:
            try:
                event = self._queue.get(timeout=timeout)
                if event is None:
                    break
                yield event
            except queue.Empty:
                with self._lock:
                    if self._closed:
                        break
                raise TimeoutError("Event stream timeout")


def create_event_stream() -> EventStream:
    """Factory function to create an event stream."""
    return EventStream()

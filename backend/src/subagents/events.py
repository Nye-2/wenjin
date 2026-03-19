"""SSE event streaming for subagent execution."""

import asyncio
import json
import queue
import threading
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import SubagentEvent as SubagentEventFromModels


class SubagentEventType(Enum):
    """Event types for subagent execution.

    Note: This enum is kept for backward compatibility with the sync EventStream.
    For the async SubagentEventStream, use string event types.
    """
    STARTED = "started"
    RUNNING = "running"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentEvent:
    """Legacy SubagentEvent for backward compatibility with executor.py.

    Note: For new code, use SubagentEvent from models.py instead.
    """
    type: SubagentEventType
    task_id: str
    subagent_type: str
    message: str
    thread_id: str | None = None
    data: dict[str, Any] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_sse(self) -> str:
        """Convert event to SSE-formatted string.

        Returns:
            SSE-formatted string with event type and JSON data
        """
        event_data = {
            "type": self.type.value,
            "task_id": self.task_id,
            "subagent_type": self.subagent_type,
            "message": self.message,
            "thread_id": self.thread_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        json_data = json.dumps(event_data)
        return f"event: {self.type.value}\ndata: {json_data}\n\n"


class EventStream:
    """Thread-safe event stream for SSE (legacy sync version).

    Note: This class is kept for backward compatibility.
    For new async code, use SubagentEventStream instead.
    """

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
            except queue.Empty as exc:
                with self._lock:
                    if self._closed:
                        break
                raise TimeoutError("Event stream timeout") from exc


def create_event_stream() -> EventStream:
    """Factory function to create an event stream."""
    return EventStream()


class SubagentEventStream:
    """Async event stream supporting thread-based subscriptions for SSE.

    This class provides a pub/sub pattern where:
    - Publishers call publish() to send events
    - Subscribers call subscribe() to receive events filtered by thread_id
    - Global subscribers (thread_id=None) receive all events

    Uses SubagentEvent from models.py which has:
    - event_type: str
    - task_id: str
    - thread_id: str
    - data: dict[str, Any]
    - timestamp: datetime
    - to_sse() method for SSE formatting
    """

    if TYPE_CHECKING:
        from .models import SubagentEvent as SubagentEventFromModels
    else:
        SubagentEvent = SubagentEvent  # Legacy class

    def __init__(self, max_queue_size: int = 100):
        """Initialize the event stream.

        Args:
            max_queue_size: Maximum events per subscriber queue (backpressure)
        """
        self._max_queue_size = max_queue_size
        self._subscribers: dict[str, asyncio.Queue[SubagentEventFromModels | None]] = {}
        self._lock = asyncio.Lock()

    @property
    def max_queue_size(self) -> int:
        """Maximum queue size per subscriber."""
        return self._max_queue_size

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self._subscribers)

    async def subscribe(
        self, thread_id: str | None = None
    ) -> AsyncIterator[str]:
        """Subscribe to events, optionally filtered by thread_id.

        Args:
            thread_id: If specified, only receive events for this thread.
                       If None, receive all events (global subscriber).

        Yields:
            SSE-formatted event strings
        """
        key = f"thread:{thread_id}" if thread_id else "global"
        queue: asyncio.Queue[SubagentEventFromModels | None] = asyncio.Queue(
            maxsize=self._max_queue_size
        )

        async with self._lock:
            self._subscribers[key] = queue

        try:
            while True:
                event = await queue.get()
                if event is None:
                    # Shutdown signal
                    break
                yield event.to_sse()
        finally:
            async with self._lock:
                self._subscribers.pop(key, None)

    async def publish(self, event: "SubagentEvent") -> None:
        """Publish an event to relevant subscribers.

        Sends to:
        - Thread-specific subscribers (if event has thread_id)
        - Global subscribers (always)

        Uses put_nowait for non-blocking behavior. Drops events if queue is full.

        Args:
            event: The event to publish (SubagentEventFromModels or SubagentEvent)
        """
        async with self._lock:
            subscribers_copy = dict(self._subscribers)

        # Collect target queues
        target_keys = ["global"]
        thread_id = getattr(event, "thread_id", None)
        if thread_id:
            target_keys.append(f"thread:{thread_id}")

        for key in target_keys:
            if key in subscribers_copy:
                queue = subscribers_copy[key]
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop event on backpressure (queue full)
                    pass

    async def close(self) -> None:
        """Close the stream, signaling shutdown to all subscribers.

        Sends None to all subscriber queues to signal end of stream.
        """
        async with self._lock:
            subscribers_copy = dict(self._subscribers)

        for subscriber_queue in subscribers_copy.values():
            try:
                subscriber_queue.put_nowait(None)
            except asyncio.QueueFull:
                # Clear queue and try again if full
                while not subscriber_queue.empty():
                    try:
                        subscriber_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                try:
                    subscriber_queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

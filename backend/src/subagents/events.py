"""Async SSE event streaming for subagent execution."""

import asyncio
from collections.abc import AsyncIterator

from .models import SubagentEvent


class SubagentEventStream:
    """Async event stream supporting thread-based subscriptions for SSE."""

    def __init__(self, max_queue_size: int = 100):
        self._max_queue_size = max_queue_size
        self._subscribers: dict[str, list[asyncio.Queue[SubagentEvent | None]]] = {}
        self._lock = asyncio.Lock()

    @property
    def max_queue_size(self) -> int:
        """Maximum queue size per subscriber."""
        return self._max_queue_size

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return sum(len(queues) for queues in self._subscribers.values())

    async def subscribe(self, thread_id: str | None = None) -> AsyncIterator[str]:
        """Subscribe to events, optionally filtered by thread_id."""
        key = f"thread:{thread_id}" if thread_id else "global"
        queue: asyncio.Queue[SubagentEvent | None] = asyncio.Queue(
            maxsize=self._max_queue_size
        )

        async with self._lock:
            self._subscribers.setdefault(key, []).append(queue)

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event.to_sse()
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(key)
                if subscribers is not None and queue in subscribers:
                    subscribers.remove(queue)
                if subscribers is not None and not subscribers:
                    self._subscribers.pop(key, None)

    async def publish(self, event: SubagentEvent) -> None:
        """Publish an event to global and matching thread subscribers."""
        async with self._lock:
            subscribers_copy = {
                key: list(queues)
                for key, queues in self._subscribers.items()
            }

        target_keys = ["global"]
        if event.thread_id:
            target_keys.append(f"thread:{event.thread_id}")

        for key in target_keys:
            for queue in subscribers_copy.get(key, ()):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def close(self) -> None:
        """Close the stream, signaling shutdown to all subscribers."""
        async with self._lock:
            subscribers_copy = [
                queue
                for queues in self._subscribers.values()
                for queue in queues
            ]

        for subscriber_queue in subscribers_copy:
            try:
                subscriber_queue.put_nowait(None)
            except asyncio.QueueFull:
                while not subscriber_queue.empty():
                    try:
                        subscriber_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                try:
                    subscriber_queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

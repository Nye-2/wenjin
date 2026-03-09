"""Memory update queue with debouncing."""

import threading
from collections import defaultdict


class MemoryQueue:
    """Debounced queue for batching memory updates per thread."""

    def __init__(self, debounce_seconds: float = 30.0):
        self._debounce = debounce_seconds
        self._pending: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def enqueue(self, thread_id: str, messages: list, callback=None) -> None:
        """Add messages to update queue for a thread."""
        with self._lock:
            self._pending[thread_id].extend(messages)

            # Reset debounce timer
            if thread_id in self._timers:
                self._timers[thread_id].cancel()

            if callback:
                timer = threading.Timer(self._debounce, callback, args=(thread_id, self._pending[thread_id]))
                self._timers[thread_id] = timer
                timer.start()

    def flush(self, thread_id: str) -> list:
        """Get and clear pending messages for a thread."""
        with self._lock:
            messages = self._pending.pop(thread_id, [])
            if thread_id in self._timers:
                self._timers[thread_id].cancel()
                del self._timers[thread_id]
            return messages

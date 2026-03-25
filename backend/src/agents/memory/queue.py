"""Memory update queue with debouncing."""

import asyncio
import inspect
import threading
from collections import defaultdict


class MemoryQueue:
    """Debounced queue for batching memory updates per thread."""

    def __init__(self, debounce_seconds: float = 30.0, default_callback=None):
        self._debounce = debounce_seconds
        self._pending: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self._callbacks: dict[str, object] = {}
        self._default_callback = default_callback

    @property
    def debounce_seconds(self) -> float:
        """Expose the active debounce interval."""
        return self._debounce

    def _resolve_callback(self, thread_id: str, callback):
        if callback is not None:
            self._callbacks[thread_id] = callback
            return callback
        return self._callbacks.get(thread_id) or self._default_callback

    def _deliver(self, thread_id: str, callback) -> None:
        messages = self.flush(thread_id)
        if not messages:
            return
        result = callback(thread_id, messages)
        if inspect.isawaitable(result):
            asyncio.run(result)

    def enqueue(self, thread_id: str, messages: list, callback=None) -> None:
        """Add messages to update queue for a thread."""
        with self._lock:
            self._pending[thread_id].extend(messages)
            resolved_callback = self._resolve_callback(thread_id, callback)

            # Reset debounce timer
            if thread_id in self._timers:
                self._timers[thread_id].cancel()

            if resolved_callback:
                timer = threading.Timer(
                    self._debounce,
                    self._deliver,
                    args=(thread_id, resolved_callback),
                )
                timer.daemon = True
                self._timers[thread_id] = timer
                timer.start()

    def flush(self, thread_id: str) -> list:
        """Get and clear pending messages for a thread."""
        with self._lock:
            messages = self._pending.pop(thread_id, [])
            if thread_id in self._timers:
                self._timers[thread_id].cancel()
                del self._timers[thread_id]
            self._callbacks.pop(thread_id, None)
            return messages


_DEFAULT_QUEUE: MemoryQueue | None = None
_DEFAULT_QUEUE_DEBOUNCE: float | None = None
_DEFAULT_QUEUE_LOCK = threading.Lock()


def _resolve_configured_debounce() -> float:
    try:
        from src.config.config_loader import get_app_config

        memory_config = getattr(get_app_config(), "memory", None)
        if memory_config is not None:
            return max(1.0, float(getattr(memory_config, "debounce_seconds", 30) or 30))
    except Exception:
        pass
    return 30.0


def get_default_memory_queue() -> MemoryQueue:
    """Return the process-wide default memory queue using app config."""
    global _DEFAULT_QUEUE
    global _DEFAULT_QUEUE_DEBOUNCE

    debounce_seconds = _resolve_configured_debounce()
    with _DEFAULT_QUEUE_LOCK:
        if (
            _DEFAULT_QUEUE is None
            or _DEFAULT_QUEUE_DEBOUNCE != debounce_seconds
        ):
            _DEFAULT_QUEUE = MemoryQueue(debounce_seconds=debounce_seconds)
            _DEFAULT_QUEUE_DEBOUNCE = debounce_seconds
        return _DEFAULT_QUEUE


def reset_default_memory_queue() -> None:
    """Reset the cached default queue, primarily for tests."""
    global _DEFAULT_QUEUE
    global _DEFAULT_QUEUE_DEBOUNCE

    with _DEFAULT_QUEUE_LOCK:
        _DEFAULT_QUEUE = None
        _DEFAULT_QUEUE_DEBOUNCE = None

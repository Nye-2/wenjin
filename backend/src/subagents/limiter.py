"""Concurrency limiters for subagent system.

Provides two levels of concurrency control:
- ConcurrencyLimiter: Simple semaphore-based limiter
- DualLayerLimiter: Combined global + per-thread limiting
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ConcurrencyLimiter:
    """Simple concurrency limiter using asyncio.Semaphore.

    Controls the maximum number of concurrent operations.
    """

    def __init__(self, max_concurrent: int):
        """Initialize the limiter.

        Args:
            max_concurrent: Maximum number of concurrent acquires.
                           Set to 0 for no slots available.
        """
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None
        self._active_count = 0
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        """Maximum concurrent operations allowed."""
        return self._max_concurrent

    @property
    def active_count(self) -> int:
        """Current number of active operations."""
        return self._active_count

    @property
    def available_slots(self) -> int:
        """Number of available slots."""
        return max(0, self._max_concurrent - self._active_count)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        """Acquire a slot asynchronously.

        Yields control while holding the slot.
        Releases the slot when exiting the context.
        """
        if self._semaphore is not None:
            async with self._semaphore:
                async with self._lock:
                    self._active_count += 1
                try:
                    yield
                finally:
                    async with self._lock:
                        self._active_count -= 1
        else:
            # No semaphore means max_concurrent is 0, no slots available
            # But we still yield to allow the code to run
            yield


class DualLayerLimiter:
    """Two-layer concurrency limiter with global and per-thread limits.

    Provides:
    - Global limit: Maximum total concurrent subagents across all threads
    - Per-thread limit: Maximum concurrent subagents within each thread
    """

    def __init__(self, global_max: int, per_thread_max: int):
        """Initialize the dual-layer limiter.

        Args:
            global_max: Maximum concurrent subagents globally.
            per_thread_max: Maximum concurrent subagents per thread.
        """
        self._global_max = global_max
        self._per_thread_max = per_thread_max
        self._global = ConcurrencyLimiter(global_max)
        self._thread_limiters: dict[str, ConcurrencyLimiter] = {}
        self._lock = asyncio.Lock()

    @property
    def global_max(self) -> int:
        """Maximum concurrent operations globally."""
        return self._global_max

    @property
    def per_thread_max(self) -> int:
        """Maximum concurrent operations per thread."""
        return self._per_thread_max

    @property
    def active_global_count(self) -> int:
        """Current global active count."""
        return self._global.active_count

    async def _get_thread_limiter(self, thread_id: str) -> ConcurrencyLimiter:
        """Get or create a limiter for the given thread.

        Args:
            thread_id: The thread identifier.

        Returns:
            The ConcurrencyLimiter for the thread.
        """
        async with self._lock:
            if thread_id not in self._thread_limiters:
                self._thread_limiters[thread_id] = ConcurrencyLimiter(self._per_thread_max)
            return self._thread_limiters[thread_id]

    def get_thread_active_count(self, thread_id: str) -> int:
        """Get the active count for a specific thread.

        Args:
            thread_id: The thread identifier.

        Returns:
            The active count for the thread, or 0 if thread not found.
        """
        limiter = self._thread_limiters.get(thread_id)
        return limiter.active_count if limiter else 0

    async def cleanup_thread(self, thread_id: str) -> None:
        """Remove the thread limiter when thread is cleaned up.

        Args:
            thread_id: The thread identifier to clean up.
        """
        async with self._lock:
            if thread_id in self._thread_limiters:
                del self._thread_limiters[thread_id]

    @asynccontextmanager
    async def acquire(self, thread_id: str) -> AsyncIterator[None]:
        """Acquire both global and thread-specific slots.

        Acquires global slot first, then thread-specific slot.
        Releases both slots when exiting the context.

        Args:
            thread_id: The thread identifier for per-thread limiting.

        Yields:
            None
        """
        # Acquire global slot first
        async with self._global.acquire():
            # Then acquire thread-specific slot
            thread_limiter = await self._get_thread_limiter(thread_id)
            async with thread_limiter.acquire():
                yield

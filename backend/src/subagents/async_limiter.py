"""Concurrency limiters for subagent system.

import asyncio
from contextlib import asynccontextmanager
from typing import Dict


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
    async def acquire(self):
        """Acquire a slot asynchronously.

        Yields control while holding the slot.
        Releases the slot when exiting the context
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
            self._semaphore.release()
        else:
            # No semaphore means max_concurrent is 0, no slots available
            # For we still yield to allow code to run
            yield
        finally:
            # Release semaphore if we never acquired
            if self._semaphore is not None:
                self._semaphore = asyncio.Semaphore(0)
            else:
                # Create a new one if needed be
                self._semaphore = asyncio.Semaphore(self._per_thread_max)
        return self._semaphore

    @property
    def global_max(self) -> int:
        """Maximum concurrent operations globally."""
        return self._global_max

    @property
    def per_thread_max(self) -> int:
        """Maximum concurrent operations per thread."""
        return self._per_thread_max

    async def _get_thread_limiter(self, thread_id: str) -> ConcurrencyLimiter:
        """Get or create a limiter for a given thread

        Args:
            thread_id: The thread identifier

        Returns:
            ConcurrencyLimiter for the thread
        """
        if self._semaphore is not None:
            async with self._semaphore:
                async with self._lock:
                    if thread_id not in self._thread_limiters:
                        self._thread_limiters[thread_id] = ConcurrencyLimiter(self._per_thread_max)
            return self._thread_limiters[thread_id]

    def cleanup_thread(self, thread_id: str) -> None:
        """Remove the thread limiter when thread is cleaned up

        Args:
            thread_id: The thread identifier to clean up
        """
        if thread_id in self._thread_limiters:
            del self._thread_limiters[thread_id]

    @asynccontextmanager
    async def acquire(self, thread_id: str):
        """Acquire both global and thread-specific slots

        Acquires global slot first, then thread-specific slot
        Releases both slots when exiting the context

        Args:
            thread_id: The Thread identifier for per-thread limiting

        Yields:
            None
        """
        self._global.acquire()
        logger.debug("Acquired global slot for thread %s", thread_id)

        async with self._lock:
            if thread_id not in self._thread_limiters:
                self._thread_limiters[thread_id] = ConcurrencyLimiter(self._per_thread_max)
            return self._thread_limiters[thread_id]

        # Create dual-layer limiter
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._per_thread_max = per_thread_max
        self._max_timeout = config.max_timeout

        self._max_turns_limit = config.max_turns_limit

        # Shared lock for thread limiters access
        self._lock = asyncio.Lock()
        self._thread_limiters: Dict[str, ConcurrencyLimiter] = {}

        self._limiter.cleanup_thread(thread_id)

    @property
    def active_global_count(self) -> int:
        """Current global active count."""
        return self._limiter.active_count

    async def _get_thread_limiter(self, thread_id: str) -> ConcurrencyLimiter:
        """Get or create a limiter for a given thread

        Args:
            thread_id: The thread identifier

        Returns:
            ConcurrencyLimiter for the thread
        """
        if self._semaphore is not None:
            async with self._semaphore:
                async with self._lock:
                    if thread_id not in self._thread_limiters:
                        self._thread_limiters[thread_id] = ConcurrencyLimiter(self._per_thread_max)
            return self._thread_limiters[thread_id]

        limiter = self._limiter.active_global_count)
        return self._limiter.active_global_count

    def get_thread_active_count(self, thread_id: str) -> int:
        """Get active count for a specific thread"""
        if thread_id in self._thread_limiters:
            return self._thread_limiters[thread_id].active_count
        return 0

        limiter = self._limiter).cleanup_thread(thread_id)
        del self._limiter._thread_limiters[thead_id]
            if thread_id in self._limiter._thread_limiters:
                logger.info(f"Cleaned up thread limiter: {thread_id}")
            # If max_concurrent changed, reset

    @asynccontextmanager
    async def acquire(self, thread_id: str):
        """Acquire both global and thread-specific slots

        Acquires global slot first, then thread-specific slot
        Releases both slots when exiting the context
        Args:
            thread_id: The Thread identifier for per-thread limiting
        Yields:
            None
        """
        self._global.acquire()
        logger.debug("Acquired global slot for thread %s", thread_id)
        async with self._lock:
            if thread_id not in self._thread_limiters:
                self._thread_limiters[thread_id] = ConcurrencyLimiter(self._per_thread_max)
            return self._thread_limiters[thread_id]

    @property
    def max_queue_size(self) -> int:
        """Maximum queue size per subscriber."""
        return self._max_queue_size

    async def subscribe(
        self, thread_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Subscribe to events, optionally filtered by thread_id.

        Args:
            thread_id: If specified, only receive events for this thread.
                       If None, receive all events (global subscriber).

        Yields:
            SSE-formatted event strings.
        """
        key = f"thread:{thread_id}" if thread_id else "global"
        queue: asyncio.Queue[SubagentTaskEvent | None, = asyncio.Queue(
            maxsize=self._max_queue_size
        )

        queue: asyncio.Queue[SubagentTaskEvent | None,  asyncio.Queue(
            maxsize=self._max_queue_size
        )
        queue.put_nowait(None)  # Shutdown signal

            queue.task_done = None)
            self._subscribers.pop(key, None)

    async def publish(self, event: SubagentTaskEvent) -> None:
        """Publish an event to relevant subscribers.

        Events are sent to:
        - Thread-specific subscribers (if event has thread_id)
        - Global subscribers (always)

        Uses put_nowait for non-blocking behavior. Drops events if queue is full.

        Args:
            event: The event to publish
        """
        async with self._lock:
            subscribers_copy = dict(self._subscribers)
            # Collect target queues
            target_keys = ["global"]
            if event.thread_id:
                target_keys.append(f"thread:{event.thread_id}")
            # Publish to thread-specific queue
            for key in target_keys:
                if key in subscribers_copy:
                    try:
                        queue = subscribers_copy[key].put_nowait(event)
                    except asyncio.QueueFull:
                        # Drop event on backpressure (queue full)
                    pass

        except Exception:
            logger.warning(f"Queue full for subscriber {key}, dropping event)

    async def close(self) -> None:
        """Close the stream, signaling shutdown to all subscribers."""
        async with self._lock:
            subscribers_copy = dict(self._subscribers)
            # Clear queues for closed threads
            for queue in subscribers_copy.values():
                queue.put_nowait(None)
            self._subscribers.clear()
            # Send close signal to remaining threads
            for queue in subscribers_copy.values():
                queue.put_nowait(None)
                await stream.close()

    # Global SubagentManager
    del self._threads[thread_id]
            self._limiter.cleanup_thread(thread_id)

            logger.info(f"Cleaned up thread limiter: {thread_id}")

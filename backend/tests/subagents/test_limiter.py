"""Tests for concurrency limiters."""

import asyncio

import pytest

from src.subagents.limiter import ConcurrencyLimiter, DualLayerLimiter


class TestConcurrencyLimiter:
    """Tests for ConcurrencyLimiter."""

    def test_init(self):
        """Should initialize with max_concurrent."""
        limiter = ConcurrencyLimiter(max_concurrent=5)
        assert limiter.max_concurrent == 5
        assert limiter.active_count == 0
        assert limiter.available_slots == 5

    def test_max_concurrent_zero(self):
        """Should allow max_concurrent of 0 (unlimited by acquire always succeeding immediately)."""
        limiter = ConcurrencyLimiter(max_concurrent=0)
        assert limiter.max_concurrent == 0
        # available_slots should be 0 when max is 0
        assert limiter.available_slots == 0

    @pytest.mark.asyncio
    async def test_acquire_releases_slot(self):
        """acquire should acquire and release a slot."""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        async with limiter.acquire():
            assert limiter.active_count == 1
            assert limiter.available_slots == 1

        assert limiter.active_count == 0
        assert limiter.available_slots == 2

    @pytest.mark.asyncio
    async def test_concurrent_acquires(self):
        """Multiple concurrent acquires should be limited."""
        limiter = ConcurrencyLimiter(max_concurrent=2)
        acquired_count = 0
        max_observed = 0

        async def acquire_task(delay: float):
            nonlocal acquired_count, max_observed
            async with limiter.acquire():
                acquired_count += 1
                max_observed = max(max_observed, limiter.active_count)
                await asyncio.sleep(delay)
                acquired_count -= 1

        # Start 4 tasks with max_concurrent=2
        tasks = [acquire_task(0.1) for _ in range(4)]
        await asyncio.gather(*tasks)

        assert max_observed == 2
        assert limiter.active_count == 0

    @pytest.mark.asyncio
    async def test_acquire_blocks_when_full(self):
        """acquire should block when no slots available."""
        limiter = ConcurrencyLimiter(max_concurrent=1)
        order = []

        async def task1():
            async with limiter.acquire():
                order.append("task1_start")
                await asyncio.sleep(0.1)
                order.append("task1_end")

        async def task2():
            async with limiter.acquire():
                order.append("task2_start")

        # Run both tasks concurrently
        await asyncio.gather(task1(), task2())

        # task2 should start only after task1 ends
        assert order == ["task1_start", "task1_end", "task2_start"]

    @pytest.mark.asyncio
    async def test_acquire_exception_releases_slot(self):
        """Slot should be released even if exception occurs."""
        limiter = ConcurrencyLimiter(max_concurrent=1)

        with pytest.raises(ValueError):
            async with limiter.acquire():
                raise ValueError("test error")

        assert limiter.active_count == 0
        assert limiter.available_slots == 1


class TestDualLayerLimiter:
    """Tests for DualLayerLimiter."""

    def test_init(self):
        """Should initialize with global and per-thread limits."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)
        assert limiter.global_max == 10
        assert limiter.per_thread_max == 3
        assert limiter.active_global_count == 0

    @pytest.mark.asyncio
    async def test_acquire_single_thread(self):
        """Should work with a single thread_id."""
        limiter = DualLayerLimiter(global_max=5, per_thread_max=2)

        async with limiter.acquire("thread-1"):
            assert limiter.active_global_count == 1
            assert limiter.get_thread_active_count("thread-1") == 1

        assert limiter.active_global_count == 0
        assert limiter.get_thread_active_count("thread-1") == 0

    @pytest.mark.asyncio
    async def test_acquire_multiple_threads(self):
        """Should track per-thread counts independently."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)

        async with limiter.acquire("thread-1"):
            async with limiter.acquire("thread-2"):
                assert limiter.active_global_count == 2
                assert limiter.get_thread_active_count("thread-1") == 1
                assert limiter.get_thread_active_count("thread-2") == 1

        assert limiter.active_global_count == 0

    @pytest.mark.asyncio
    async def test_per_thread_limit_blocks(self):
        """Should block when per-thread limit is reached."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=2)
        order = []

        async def task(thread_id: str, delay: float):
            async with limiter.acquire(thread_id):
                order.append(f"{thread_id}_start")
                await asyncio.sleep(delay)
                order.append(f"{thread_id}_end")

        # Start 3 tasks for same thread with per_thread_max=2
        tasks = [
            task("thread-1", 0.1),
            task("thread-1", 0.1),
            task("thread-1", 0.1),
        ]
        await asyncio.gather(*tasks)

        # Third task should wait until one of first two completes
        # Check that at most 2 were active at any time for thread-1
        assert limiter.get_thread_active_count("thread-1") == 0

    @pytest.mark.asyncio
    async def test_global_limit_blocks(self):
        """Should block when global limit is reached."""
        limiter = DualLayerLimiter(global_max=2, per_thread_max=10)
        max_global_observed = 0

        async def task(thread_id: str):
            nonlocal max_global_observed
            async with limiter.acquire(thread_id):
                max_global_observed = max(max_global_observed, limiter.active_global_count)
                await asyncio.sleep(0.1)

        # Start 4 tasks across different threads with global_max=2
        tasks = [task(f"thread-{i}") for i in range(4)]
        await asyncio.gather(*tasks)

        assert max_global_observed == 2
        assert limiter.active_global_count == 0

    @pytest.mark.asyncio
    async def test_acquire_order_global_then_thread(self):
        """Should acquire global slot first, then thread slot.

        This is verified by checking that when global is exhausted,
        thread-level slots are not acquired.
        """
        limiter = DualLayerLimiter(global_max=1, per_thread_max=2)

        # Use a flag to verify ordering behavior
        acquired_both = []

        async def task(thread_id: str, delay: float):
            async with limiter.acquire(thread_id):
                acquired_both.append(thread_id)
                await asyncio.sleep(delay)

        # Start two tasks - first should get the global slot,
        # second should wait for global slot
        task1 = asyncio.create_task(task("t1", 0.1))
        task2 = asyncio.create_task(task("t1", 0.1))

        # Wait a bit for task1 to acquire
        await asyncio.sleep(0.05)

        # task1 should have acquired, task2 should be waiting on global
        assert limiter.active_global_count == 1
        assert len(acquired_both) == 1

        # Wait for both to complete
        await asyncio.gather(task1, task2)

        assert len(acquired_both) == 2
        assert limiter.active_global_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_thread(self):
        """Should remove thread limiter on cleanup."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)

        # Use a thread
        async with limiter.acquire("thread-1"):
            pass

        # Thread limiter should exist
        assert limiter.get_thread_active_count("thread-1") == 0

        # Cleanup thread
        await limiter.cleanup_thread("thread-1")

        # After cleanup, count should be 0 (limiter removed)
        assert limiter.get_thread_active_count("thread-1") == 0

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_thread(self):
        """cleanup_thread should not raise for unknown threads."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)

        # Should not raise
        await limiter.cleanup_thread("unknown-thread")

    @pytest.mark.asyncio
    async def test_concurrent_access_safety(self):
        """Should handle concurrent access safely."""
        limiter = DualLayerLimiter(global_max=5, per_thread_max=2)

        async def worker(thread_id: str, num_tasks: int):
            for _ in range(num_tasks):
                async with limiter.acquire(thread_id):
                    await asyncio.sleep(0.01)

        # Create workers for multiple threads
        tasks = []
        for i in range(3):
            tasks.extend([worker(f"thread-{i}", 3) for _ in range(2)])

        await asyncio.gather(*tasks)

        # All counts should be 0 after completion
        assert limiter.active_global_count == 0

    @pytest.mark.asyncio
    async def test_get_thread_active_count_unknown_thread(self):
        """get_thread_active_count should return 0 for unknown threads."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)

        assert limiter.get_thread_active_count("unknown") == 0

    @pytest.mark.asyncio
    async def test_exception_releases_both_slots(self):
        """Both slots should be released on exception."""
        limiter = DualLayerLimiter(global_max=5, per_thread_max=2)

        with pytest.raises(ValueError):
            async with limiter.acquire("thread-1"):
                raise ValueError("test error")

        assert limiter.active_global_count == 0
        assert limiter.get_thread_active_count("thread-1") == 0

    @pytest.mark.asyncio
    async def test_acquire_context_manager_is_async(self):
        """acquire should be an async context manager."""
        limiter = ConcurrencyLimiter(max_concurrent=1)

        # Should not raise
        async with limiter.acquire():
            pass

    @pytest.mark.asyncio
    async def test_dual_layer_acquire_context_manager_is_async(self):
        """DualLayerLimiter.acquire should be an async context manager."""
        limiter = DualLayerLimiter(global_max=1, per_thread_max=1)

        # Should not raise
        async with limiter.acquire("thread-1"):
            pass

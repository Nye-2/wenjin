"""Tests for SSE event streaming."""

import asyncio
import threading
import time
from datetime import datetime

import pytest

from src.subagents.events import (
    EventStream,
    SubagentEventStream,
    SubagentEventType,
    create_event_stream,
)
from src.subagents.models import SubagentEvent


class TestSubagentEventFromModels:
    """Tests for SubagentEvent from models.py."""

    def test_event_creation(self):
        event = SubagentEvent(
            event_type="started",
            task_id="test-123",
            thread_id="thread-456",
            data={"message": "Task started"},
            timestamp=datetime.now(),
        )
        assert event.event_type == "started"
        assert event.task_id == "test-123"
        assert event.thread_id == "thread-456"
        assert event.data == {"message": "Task started"}

    def test_to_sse_format(self):
        event = SubagentEvent(
            event_type="completed",
            task_id="task-123",
            thread_id="thread-456",
            data={"result": "success", "output": "Done"},
            timestamp=datetime(2026, 3, 10, 12, 0, 0),
        )
        sse = event.to_sse()
        assert sse.startswith("event: completed\n")
        assert "data:" in sse
        assert '"event_type": "completed"' in sse
        assert '"task_id": "task-123"' in sse
        assert '"thread_id": "thread-456"' in sse
        assert sse.endswith("\n\n")

    def test_to_dict(self):
        event = SubagentEvent(
            event_type="progress",
            task_id="task-789",
            thread_id="thread-abc",
            data={"percent": 50},
            timestamp=datetime(2026, 3, 10, 12, 30, 0),
        )
        d = event.to_dict()
        assert d["event_type"] == "progress"
        assert d["task_id"] == "task-789"
        assert d["thread_id"] == "thread-abc"
        assert d["data"] == {"percent": 50}
        assert "2026-03-10" in d["timestamp"]


class TestSubagentEventType:
    """Tests for the legacy SubagentEventType enum."""

    def test_event_types(self):
        assert SubagentEventType.STARTED.value == "started"
        assert SubagentEventType.RUNNING.value == "running"
        assert SubagentEventType.COMPLETED.value == "completed"
        assert SubagentEventType.FAILED.value == "failed"
        assert SubagentEventType.TIMED_OUT.value == "timed_out"


class TestEventStream:
    """Tests for the legacy sync EventStream."""

    def test_push_and_iterate(self):
        stream = EventStream()
        event = SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="thread-1",
            data={"msg": "Started"},
            timestamp=datetime.now(),
        )
        stream.push(event)
        stream.close()
        events = list(stream.iterate())
        assert len(events) == 1
        assert events[0].task_id == "t1"

    def test_close(self):
        stream = EventStream()
        stream.close()
        assert stream.is_closed

    def test_timeout_raises_timeout_error(self):
        """Test that iterate raises TimeoutError when no events arrive."""
        stream = EventStream()
        with pytest.raises(TimeoutError, match="Event stream timeout"):
            list(stream.iterate(timeout=0.1))

    def test_timeout_returns_after_close(self):
        """Test that iterate returns gracefully when stream is closed."""
        stream = EventStream()
        # Close in background after short delay
        def close_after_delay():
            time.sleep(0.05)
            stream.close()

        threading.Thread(target=close_after_delay, daemon=True).start()
        events = list(stream.iterate(timeout=1.0))
        assert events == []

    def test_push_to_closed_stream_does_nothing(self):
        """Test that pushing to a closed stream is a no-op."""
        stream = EventStream()
        stream.close()
        assert stream.is_closed
        # Push should be ignored
        event = SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="thread-1",
            data={},
            timestamp=datetime.now(),
        )
        stream.push(event)
        # Iterate should return empty (only the None sentinel was consumed)
        events = list(stream.iterate(timeout=0.1))
        assert events == []

    def test_thread_safety_concurrent_push(self):
        """Test that concurrent pushes are handled safely."""
        stream = EventStream()
        num_threads = 10
        barrier = threading.Barrier(num_threads)

        def push_event(thread_id):
            barrier.wait()
            stream.push(SubagentEvent(
                event_type="progress",
                task_id=f"t{thread_id}",
                thread_id=f"thread-{thread_id}",
                data={"msg": f"Event {thread_id}"},
                timestamp=datetime.now(),
            ))

        threads = [
            threading.Thread(target=push_event, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stream.close()
        events = list(stream.iterate())
        assert len(events) == num_threads


class TestCreateEventStream:
    """Tests for the factory function."""

    def test_factory(self):
        stream = create_event_stream()
        assert stream is not None
        assert hasattr(stream, "push")
        assert hasattr(stream, "iterate")


class TestSubagentEventStream:
    """Tests for the async SubagentEventStream."""

    def test_init_default_queue_size(self):
        stream = SubagentEventStream()
        assert stream.max_queue_size == 100

    def test_init_custom_queue_size(self):
        stream = SubagentEventStream(max_queue_size=50)
        assert stream.max_queue_size == 50

    def test_subscriber_count_initial(self):
        stream = SubagentEventStream()
        assert stream.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_creates_subscriber(self):
        stream = SubagentEventStream()

        async def collect_events():
            events = []
            async for sse in stream.subscribe(thread_id="test-thread"):
                events.append(sse)
                if len(events) >= 1:
                    break
            return events

        # Start subscription task
        task = asyncio.create_task(collect_events())

        # Give subscription time to register
        await asyncio.sleep(0.01)
        assert stream.subscriber_count == 1

        # Publish and close
        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="test-thread",
            data={"msg": "Started"},
            timestamp=datetime.now(),
        ))
        await stream.close()

        events = await task
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_thread_specific_filtering(self):
        """Test that subscribers only receive events for their thread."""
        stream = SubagentEventStream()

        thread1_events: list[str] = []
        thread2_events: list[str] = []
        global_events: list[str] = []

        async def subscribe_thread(thread_id, events_list):
            async for sse in stream.subscribe(thread_id=thread_id):
                events_list.append(sse)
                if len(events_list) >= 1:
                    break

        async def subscribe_global(events_list):
            async for sse in stream.subscribe(thread_id=None):
                events_list.append(sse)
                if len(events_list) >= 2:
                    break

        # Start subscriptions
        task1 = asyncio.create_task(subscribe_thread("thread-1", thread1_events))
        task2 = asyncio.create_task(subscribe_thread("thread-2", thread2_events))
        task_global = asyncio.create_task(subscribe_global(global_events))

        # Wait for subscriptions to register
        await asyncio.sleep(0.05)

        # Publish events for different threads
        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="thread-1",
            data={"msg": "Thread 1 event"},
            timestamp=datetime.now(),
        ))
        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t2",
            thread_id="thread-2",
            data={"msg": "Thread 2 event"},
            timestamp=datetime.now(),
        ))

        await stream.close()

        await asyncio.gather(task1, task2, task_global)

        # Thread 1 should only get thread-1 event
        assert len(thread1_events) == 1
        assert "Thread 1 event" in thread1_events[0]

        # Thread 2 should only get thread-2 event
        assert len(thread2_events) == 1
        assert "Thread 2 event" in thread2_events[0]

        # Global should get both events
        assert len(global_events) == 2

    @pytest.mark.asyncio
    async def test_global_subscriber_receives_all(self):
        """Test that global subscribers receive all events."""
        stream = SubagentEventStream()

        received_events: list[str] = []

        async def global_subscribe():
            async for sse in stream.subscribe(thread_id=None):
                received_events.append(sse)
                if len(received_events) >= 3:
                    break

        task = asyncio.create_task(global_subscribe())
        await asyncio.sleep(0.01)

        # Publish events with different thread_ids
        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="thread-a",
            data={"msg": "With thread A"},
            timestamp=datetime.now(),
        ))
        await stream.publish(SubagentEvent(
            event_type="progress",
            task_id="t2",
            thread_id="thread-b",
            data={"msg": "With thread B"},
            timestamp=datetime.now(),
        ))
        await stream.publish(SubagentEvent(
            event_type="completed",
            task_id="t3",
            thread_id="thread-c",
            data={"msg": "With thread C"},
            timestamp=datetime.now(),
        ))

        await stream.close()
        await task

        assert len(received_events) == 3

    @pytest.mark.asyncio
    async def test_publish_to_thread_and_global(self):
        """Test that events go to both thread-specific and global subscribers."""
        stream = SubagentEventStream()

        thread_events: list[str] = []
        global_events: list[str] = []

        async def sub_thread():
            async for sse in stream.subscribe(thread_id="my-thread"):
                thread_events.append(sse)
                break

        async def sub_global():
            async for sse in stream.subscribe(thread_id=None):
                global_events.append(sse)
                break

        task_t = asyncio.create_task(sub_thread())
        task_g = asyncio.create_task(sub_global())
        await asyncio.sleep(0.01)

        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="my-thread",
            data={"msg": "Test"},
            timestamp=datetime.now(),
        ))

        await asyncio.gather(task_t, task_g)

        # Both should receive the same event
        assert len(thread_events) == 1
        assert len(global_events) == 1
        assert "Test" in thread_events[0]
        assert "Test" in global_events[0]

    @pytest.mark.asyncio
    async def test_close_sends_none_to_all_subscribers(self):
        """Test that close() signals shutdown to all subscribers."""
        stream = SubagentEventStream()

        completed = []

        async def subscriber(name):
            async for _sse in stream.subscribe(thread_id=name):
                pass  # Should exit when None is received
            completed.append(name)

        task1 = asyncio.create_task(subscriber("thread-1"))
        task2 = asyncio.create_task(subscriber("thread-2"))
        task_global = asyncio.create_task(subscriber(None))

        await asyncio.sleep(0.01)
        await stream.close()

        await asyncio.gather(task1, task2, task_global)

        assert "thread-1" in completed
        assert "thread-2" in completed
        assert None in completed

    @pytest.mark.asyncio
    async def test_backpressure_drops_events(self):
        """Test that events are dropped when queue is full without blocking publisher."""
        stream = SubagentEventStream(max_queue_size=2)

        # First, manually add a subscriber queue to test the behavior
        key = "thread:test"
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        async with stream._lock:
            stream._subscribers[key] = queue

        # Fill the queue
        for i in range(2):
            await stream.publish(SubagentEvent(
                event_type="progress",
                task_id=f"t{i}",
                thread_id="test",
                data={"msg": f"Event {i}"},
                timestamp=datetime.now(),
            ))

        # Verify queue is full
        assert queue.full()

        # This should NOT block - it should drop the event
        await stream.publish(SubagentEvent(
            event_type="progress",
            task_id="overflow",
            thread_id="test",
            data={"msg": "Should be dropped"},
            timestamp=datetime.now(),
        ))

        # Queue should still have only 2 items (overflow was dropped)
        assert queue.qsize() == 2

        # Clean up
        await stream.close()

    @pytest.mark.asyncio
    async def test_subscriber_cleanup_on_exit(self):
        """Test that subscribers are removed from dict when they exit."""
        stream = SubagentEventStream()

        async def subscribe_and_exit():
            async for _sse in stream.subscribe(thread_id="test"):
                break  # Exit immediately

        task = asyncio.create_task(subscribe_and_exit())
        await asyncio.sleep(0.01)
        assert stream.subscriber_count == 1

        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="test",
            data={"msg": "Test"},
            timestamp=datetime.now(),
        ))

        await task
        await asyncio.sleep(0.01)

        # Subscriber should be cleaned up
        assert stream.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_sse_format_output(self):
        """Test that subscribe yields properly formatted SSE strings."""
        stream = SubagentEventStream()

        sse_strings: list[str] = []

        async def collect():
            async for sse in stream.subscribe(thread_id="test"):
                sse_strings.append(sse)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        event = SubagentEvent(
            event_type="completed",
            task_id="task-123",
            thread_id="test",
            data={"key": "value"},
            timestamp=datetime.now(),
        )
        await stream.publish(event)

        await task

        assert len(sse_strings) == 1
        sse = sse_strings[0]
        assert sse.startswith("event: completed\ndata:")
        assert sse.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_event_without_matching_subscriber(self):
        """Test that publishing to non-existent thread doesn't fail."""
        stream = SubagentEventStream()

        # This should not raise an error
        await stream.publish(SubagentEvent(
            event_type="started",
            task_id="t1",
            thread_id="non-existent-thread",
            data={},
            timestamp=datetime.now(),
        ))

        assert stream.subscriber_count == 0

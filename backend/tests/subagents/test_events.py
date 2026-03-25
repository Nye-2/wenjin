"""Tests for async subagent SSE streaming."""

import asyncio
from datetime import datetime

import pytest

from src.subagents.events import SubagentEventStream
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
        data = event.to_dict()
        assert data["event_type"] == "progress"
        assert data["task_id"] == "task-789"
        assert data["thread_id"] == "thread-abc"
        assert data["data"] == {"percent": 50}
        assert "2026-03-10" in data["timestamp"]


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

        task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)
        assert stream.subscriber_count == 1

        await stream.publish(
            SubagentEvent(
                event_type="started",
                task_id="t1",
                thread_id="test-thread",
                data={"msg": "Started"},
                timestamp=datetime.now(),
            )
        )
        await stream.close()

        events = await task
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_thread_specific_filtering(self):
        """Subscribers only receive events for their thread plus global events."""
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

        task1 = asyncio.create_task(subscribe_thread("thread-1", thread1_events))
        task2 = asyncio.create_task(subscribe_thread("thread-2", thread2_events))
        task_global = asyncio.create_task(subscribe_global(global_events))

        await asyncio.sleep(0.05)

        await stream.publish(
            SubagentEvent(
                event_type="started",
                task_id="t1",
                thread_id="thread-1",
                data={"msg": "Thread 1 event"},
                timestamp=datetime.now(),
            )
        )
        await stream.publish(
            SubagentEvent(
                event_type="started",
                task_id="t2",
                thread_id="thread-2",
                data={"msg": "Thread 2 event"},
                timestamp=datetime.now(),
            )
        )
        await stream.close()

        await asyncio.gather(task1, task2, task_global)

        assert len(thread1_events) == 1
        assert '"thread_id": "thread-1"' in thread1_events[0]
        assert len(thread2_events) == 1
        assert '"thread_id": "thread-2"' in thread2_events[0]
        assert len(global_events) == 2

    @pytest.mark.asyncio
    async def test_multiple_subscribers_can_share_same_thread(self):
        stream = SubagentEventStream()
        subscriber_a: list[str] = []
        subscriber_b: list[str] = []

        async def _subscribe(bucket: list[str]):
            async for sse in stream.subscribe(thread_id="thread-1"):
                bucket.append(sse)
                if len(bucket) >= 1:
                    break

        task_a = asyncio.create_task(_subscribe(subscriber_a))
        task_b = asyncio.create_task(_subscribe(subscriber_b))

        await asyncio.sleep(0.05)
        assert stream.subscriber_count == 2

        await stream.publish(
            SubagentEvent(
                event_type="started",
                task_id="t1",
                thread_id="thread-1",
                data={"msg": "Shared event"},
                timestamp=datetime.now(),
            )
        )
        await stream.close()
        await asyncio.gather(task_a, task_b)

        assert len(subscriber_a) == 1
        assert len(subscriber_b) == 1

    @pytest.mark.asyncio
    async def test_close_drops_old_events_when_queue_is_full(self):
        stream = SubagentEventStream(max_queue_size=2)

        queue_ready = asyncio.Event()
        release_consumer = asyncio.Event()
        collected: list[str] = []

        async def slow_subscriber():
            async for sse in stream.subscribe(thread_id="thread-1"):
                queue_ready.set()
                await release_consumer.wait()
                collected.append(sse)

        task = asyncio.create_task(slow_subscriber())
        await asyncio.sleep(0.05)

        for index in range(3):
            await stream.publish(
                SubagentEvent(
                    event_type="progress",
                    task_id=f"t{index}",
                    thread_id="thread-1",
                    data={"index": index},
                    timestamp=datetime.now(),
                )
            )

        await queue_ready.wait()
        await stream.close()
        release_consumer.set()
        await task

        assert len(collected) <= 2

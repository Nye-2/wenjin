"""Tests for SSE event streaming."""

import threading
import time

import pytest
from src.subagents.events import (
    SubagentEvent,
    SubagentEventType,
    EventStream,
    create_event_stream,
)


class TestSubagentEvent:
    def test_event_types(self):
        assert SubagentEventType.STARTED.value == "started"
        assert SubagentEventType.RUNNING.value == "running"
        assert SubagentEventType.COMPLETED.value == "completed"
        assert SubagentEventType.FAILED.value == "failed"
        assert SubagentEventType.TIMED_OUT.value == "timed_out"

    def test_event_creation(self):
        event = SubagentEvent(
            type=SubagentEventType.STARTED,
            task_id="test-123",
            subagent_type="scout",
            message="Task started",
        )
        assert event.type == SubagentEventType.STARTED
        assert event.task_id == "test-123"
        assert event.data is None


class TestEventStream:
    def test_push_and_iterate(self):
        stream = EventStream()
        stream.push(SubagentEvent(
            type=SubagentEventType.STARTED,
            task_id="t1",
            subagent_type="scout",
            message="Started",
        ))
        stream.close()  # Close stream to signal end of events
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
        stream.push(SubagentEvent(
            type=SubagentEventType.STARTED,
            task_id="t1",
            subagent_type="scout",
            message="Should be ignored",
        ))
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
                type=SubagentEventType.PROGRESS,
                task_id=f"t{thread_id}",
                subagent_type="test",
                message=f"Event {thread_id}",
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
    def test_factory(self):
        stream = create_event_stream()
        assert stream is not None
        assert hasattr(stream, "push")
        assert hasattr(stream, "iterate")

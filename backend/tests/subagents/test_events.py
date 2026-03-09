"""Tests for SSE event streaming."""

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


class TestCreateEventStream:
    def test_factory(self):
        stream = create_event_stream()
        assert stream is not None
        assert hasattr(stream, "push")
        assert hasattr(stream, "iterate")

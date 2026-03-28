"""Tests for SSE heartbeat in chat streaming."""

import pytest


class TestHeartbeatEvent:
    def test_heartbeat_event_format(self):
        """Heartbeat must be an SSE comment (starts with colon)."""
        from src.gateway.routers.chat_streaming import stream_heartbeat_event

        heartbeat = stream_heartbeat_event()
        assert heartbeat.startswith(":")
        assert heartbeat.endswith("\n\n")
        assert "heartbeat" in heartbeat

    def test_heartbeat_is_not_data_event(self):
        """Heartbeat must NOT be a data event — should not trigger onmessage handlers."""
        from src.gateway.routers.chat_streaming import stream_heartbeat_event

        heartbeat = stream_heartbeat_event()
        assert not heartbeat.startswith("data:")

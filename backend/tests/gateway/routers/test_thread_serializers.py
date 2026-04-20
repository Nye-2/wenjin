"""Tests for thread serializer helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from src.gateway.routers.thread_serializers import thread_messages_to_response


def test_thread_messages_to_response_normalizes_non_string_content():
    payload = [
        {
            "role": "assistant",
            "content": {"answer": 42},
            "timestamp": datetime(2026, 4, 13, tzinfo=UTC),
            "blocks": [{"type": "text", "content": "hello"}],
            "metadata": {"cost": {"tokens": 10}},
        }
    ]

    messages = thread_messages_to_response(payload)

    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "{'answer': 42}"
    assert messages[0].blocks == [{"type": "text", "content": "hello"}]
    assert messages[0].metadata == {"cost": {"tokens": 10}}

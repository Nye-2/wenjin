"""Tests for thread workspace event helpers."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.thread_events import (
    publish_thread_deleted,
    publish_thread_updated,
    serialize_thread_summary,
    set_thread_status,
)


def _make_thread():
    return SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        title="Main thread",
        model="gpt-4o",
        message_count=2,
        last_message_preview="latest response",
        last_message_role="assistant",
        workspace=SimpleNamespace(type="thesis"),
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "latest response"},
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_thread_with_usage():
    return SimpleNamespace(
        id="thread-usage",
        workspace_id="ws-1",
        title="Usage thread",
        model="gpt-4o",
        message_count=2,
        last_message_preview="latest response",
        last_message_role="assistant",
        workspace=SimpleNamespace(type="thesis"),
        messages=[
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "latest response",
                "metadata": {
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 4,
                        "total_tokens": 16,
                    },
                    "billing": {
                        "token_usage": {
                            "input_tokens": 12,
                            "output_tokens": 4,
                            "total_tokens": 16,
                        }
                    },
                },
            },
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_serialize_thread_summary_includes_preview() -> None:
    summary = serialize_thread_summary(_make_thread())

    assert summary["id"] == "thread-1"
    assert summary["message_count"] == 2
    assert summary["last_message_role"] == "assistant"
    assert summary["last_message_preview"] == "latest response"


def test_serialize_thread_summary_uses_stored_denormalized_fields() -> None:
    thread = _make_thread()
    thread.messages = []
    summary = serialize_thread_summary(thread)

    assert summary["message_count"] == 2
    assert summary["last_message_role"] == "assistant"
    assert summary["last_message_preview"] == "latest response"


def test_serialize_thread_summary_includes_token_usage() -> None:
    summary = serialize_thread_summary(_make_thread_with_usage())

    assert summary["last_message_token_usage"] == {
        "input_tokens": 12,
        "output_tokens": 4,
        "total_tokens": 16,
    }
    assert summary["thread_token_usage"] == {
        "input_tokens": 12,
        "output_tokens": 4,
        "total_tokens": 16,
    }


@pytest.mark.asyncio
async def test_publish_thread_updated_does_not_duplicate_mission_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_workspace_event = AsyncMock()
    monkeypatch.setattr(
        "src.services.thread_events.publish_workspace_event",
        publish_workspace_event,
    )

    await publish_thread_updated(_make_thread())

    publish_workspace_event.assert_awaited_once()
    payload = publish_workspace_event.await_args.args[2]
    assert payload["thread"]["id"] == "thread-1"
    assert "activity" not in payload


@pytest.mark.asyncio
async def test_publish_thread_updated_keeps_usage_on_thread_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_workspace_event = AsyncMock()
    monkeypatch.setattr(
        "src.services.thread_events.publish_workspace_event",
        publish_workspace_event,
    )

    await publish_thread_updated(_make_thread_with_usage())

    payload = publish_workspace_event.await_args.args[2]
    assert payload["thread"]["thread_token_usage"]["total_tokens"] == 16
    assert "activity" not in payload


@pytest.mark.asyncio
async def test_publish_thread_deleted_does_not_address_mission_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_workspace_event = AsyncMock()
    monkeypatch.setattr(
        "src.services.thread_events.publish_workspace_event",
        publish_workspace_event,
    )

    await publish_thread_deleted("ws-1", "thread-9")

    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "thread.deleted",
        {"thread_id": "thread-9"},
    )


@pytest.mark.asyncio
async def test_set_thread_status_updates_redis_and_publishes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_redis = MagicMock()
    mock_redis._client = MagicMock()
    mock_redis.set_agent_status = AsyncMock()
    publish_workspace_event = AsyncMock()

    monkeypatch.setattr("src.academic.cache.redis_client.redis_client", mock_redis)
    monkeypatch.setattr("src.services.thread_events.publish_workspace_event", publish_workspace_event)
    monkeypatch.setattr("src.config.redis_settings.enabled", True)

    await set_thread_status(
        "ws-1",
        "thread-1",
        status="running",
        subagent_count=0,
    )

    mock_redis.set_agent_status.assert_awaited_once_with(
        "thread-1",
        "running",
        subagent_count=0,
    )
    publish_workspace_event.assert_awaited_once()
    payload = publish_workspace_event.await_args.args[2]
    assert payload["thread"]["thread_id"] == "thread-1"
    assert payload["thread"]["subagent_count"] == 0

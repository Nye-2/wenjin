"""Tests for chat thread workspace event helpers."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.chat_thread_events import (
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
        skill="deep-research",
        workspace=SimpleNamespace(type="thesis"),
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "latest response"},
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_serialize_thread_summary_includes_preview() -> None:
    summary = serialize_thread_summary(_make_thread())

    assert summary["id"] == "thread-1"
    assert summary["skill_name"] == "深度调研"
    assert summary["message_count"] == 2
    assert summary["last_message_role"] == "assistant"
    assert summary["last_message_preview"] == "latest response"


@pytest.mark.asyncio
async def test_publish_thread_updated_includes_canonical_activity_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_workspace_event = AsyncMock()
    monkeypatch.setattr(
        "src.services.chat_thread_events.publish_workspace_event",
        publish_workspace_event,
    )

    await publish_thread_updated(_make_thread())

    publish_workspace_event.assert_awaited_once()
    payload = publish_workspace_event.await_args.args[2]
    assert payload["thread"]["id"] == "thread-1"
    assert payload["thread"]["skill_name"] == "深度调研"
    assert payload["activity"]["id"] == "chat:thread-1"
    assert payload["activity"]["kind"] == "chat_thread"
    assert payload["activity"]["skill_name"] == "深度调研"
    assert payload["activity"]["metadata"]["skill"] == "deep-research"
    assert payload["activity"]["metadata"]["skill_name"] == "深度调研"
    assert payload["activity"]["summary"] == "latest response"
    assert "T" in payload["activity"]["occurred_at"]


@pytest.mark.asyncio
async def test_publish_thread_deleted_includes_activity_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_workspace_event = AsyncMock()
    monkeypatch.setattr(
        "src.services.chat_thread_events.publish_workspace_event",
        publish_workspace_event,
    )

    await publish_thread_deleted("ws-1", "thread-9")

    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "thread.deleted",
        {"thread_id": "thread-9", "activity_id": "chat:thread-9"},
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
    monkeypatch.setattr("src.services.chat_thread_events.publish_workspace_event", publish_workspace_event)
    monkeypatch.setattr("src.config.redis_settings.enabled", True)

    await set_thread_status(
        "ws-1",
        "thread-1",
        status="running",
        skill="deep-research",
        skill_name="深度调研",
        subagent_count=0,
    )

    mock_redis.set_agent_status.assert_awaited_once_with(
        "thread-1",
        "running",
        skill="deep-research",
        skill_name="深度调研",
        subagent_count=0,
        clear_skill=False,
    )
    publish_workspace_event.assert_awaited_once()
    payload = publish_workspace_event.await_args.args[2]
    assert payload["thread"]["thread_id"] == "thread-1"
    assert payload["thread"]["current_skill"] == "deep-research"
    assert payload["thread"]["current_skill_name"] == "深度调研"

"""Tests for task-to-chat result write-back."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.task.tasks.base import _append_task_chat_message


class _FakeChatThreadService:
    def __init__(self, db, thread):
        self._thread = thread
        self.add_message = AsyncMock()

    async def get_by_id(self, thread_id: str):
        if self._thread and self._thread.id == thread_id:
            return self._thread
        return None


@pytest.mark.asyncio
async def test_append_task_chat_message_writes_completion_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1")
    service = _FakeChatThreadService(object(), thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.chat_thread_service.ChatThreadService",
        lambda db: service,
    )
    monkeypatch.setattr(
        "src.services.chat_thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _append_task_chat_message(
        db=object(),
        task_id="task-1",
        task_type="workspace_feature",
        payload={
            "thread_id": "thread-1",
            "feature_id": "framework_outline",
            "params": {"topic": "LLM planning"},
        },
        result={
            "data": {"sections": [{"title": "Intro"}, {"title": "Method"}]},
            "artifacts": [{"id": "artifact-1", "title": "LLM Framework"}],
        },
    )

    service.add_message.assert_awaited_once()
    kwargs = service.add_message.await_args.kwargs
    assert kwargs["role"] == "assistant"
    assert kwargs["metadata"]["orchestration"]["status"] == "completed"
    assert kwargs["metadata"]["orchestration"]["feature_id"] == "framework_outline"
    publish_thread_updated.assert_awaited_once_with(thread)


@pytest.mark.asyncio
async def test_append_task_chat_message_writes_failure_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = SimpleNamespace(id="thread-2", workspace_id="ws-1")
    service = _FakeChatThreadService(object(), thread)
    publish_thread_updated = AsyncMock()

    monkeypatch.setattr(
        "src.services.chat_thread_service.ChatThreadService",
        lambda db: service,
    )
    monkeypatch.setattr(
        "src.services.chat_thread_events.publish_thread_updated",
        publish_thread_updated,
    )

    await _append_task_chat_message(
        db=object(),
        task_id="task-2",
        task_type="workspace_feature",
        payload={
            "thread_id": "thread-2",
            "feature_id": "peer_review",
            "params": {"paper_title": "Agent Paper"},
        },
        error="tool timeout",
    )

    service.add_message.assert_awaited_once()
    kwargs = service.add_message.await_args.kwargs
    assert kwargs["role"] == "assistant"
    assert kwargs["metadata"]["orchestration"]["status"] == "failed"
    assert kwargs["metadata"]["orchestration"]["error"] == "tool timeout"
    publish_thread_updated.assert_awaited_once_with(thread)

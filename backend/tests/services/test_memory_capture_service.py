"""Tests for canonical memory capture ingress."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.services.memory_capture_service import MemoryCaptureService


@pytest.mark.asyncio
async def test_capture_messages_dispatches_to_celery_when_enabled():
    queue = MagicMock()
    service = MemoryCaptureService(queue=queue)

    with patch("src.config.celery_settings", SimpleNamespace(enabled=True)), patch(
        "src.task.tasks.memory.capture_memory.apply_async"
    ) as apply_async:
        await service.capture_messages(
            thread_id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            messages=[
                HumanMessage(content="请记住我偏好 IEEE"),
                AIMessage(content="已记录。"),
            ],
            source="test",
        )

    apply_async.assert_called_once()
    payload = apply_async.call_args.kwargs["args"][0]
    assert payload["user_id"] == "user-1"
    assert payload["workspace_id"] == "ws-1"
    assert payload["source"] == "test"
    assert "IEEE" in payload["conversation_text"]
    queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_capture_messages_falls_back_to_debounced_queue_when_celery_disabled():
    queue = MagicMock()
    service = MemoryCaptureService(queue=queue)

    with patch("src.config.celery_settings", SimpleNamespace(enabled=False)):
        await service.capture_messages(
            thread_id="thread-1",
            user_id="user-1",
            workspace_id="ws-1",
            messages=[
                HumanMessage(content="请记住我偏好简洁回答"),
                AIMessage(content="已记录。"),
            ],
            source="test",
        )

    queue.enqueue.assert_called_once()
    assert queue.enqueue.call_args.args[0] == "thread-1"
    assert "callback" in queue.enqueue.call_args.kwargs


@pytest.mark.asyncio
async def test_persist_conversation_skips_blank_text():
    service = MemoryCaptureService(queue=MagicMock())

    with patch(
        "src.services.memory_capture_service.extract_and_persist_knowledge",
        new=AsyncMock(),
    ) as persist:
        count = await service.persist_conversation(
            user_id="user-1",
            conversation_text="   ",
            workspace_context="ws-1",
            source="test",
        )

    assert count == 0
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_conversation_adds_stable_capture_hash_to_source():
    service = MemoryCaptureService(queue=MagicMock())

    with patch(
        "src.services.memory_capture_service.extract_and_persist_knowledge",
        new=AsyncMock(return_value=1),
    ) as persist:
        count = await service.persist_conversation(
            user_id="user-1",
            conversation_text="user: remember IEEE",
            workspace_context="ws-1",
            source="test",
        )

    assert count == 1
    source = persist.await_args.kwargs["source"]
    assert source.startswith("test#")
    assert len(source) <= 100

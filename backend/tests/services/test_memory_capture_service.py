"""Tests for retired cross-workspace memory capture ingress."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.services.memory_capture_service import MemoryCaptureService


@pytest.mark.asyncio
async def test_capture_messages_is_noop():
    queue = MagicMock()
    service = MemoryCaptureService(queue=queue)

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

    queue.enqueue.assert_not_called()


def test_enqueue_messages_is_noop():
    queue = MagicMock()
    service = MemoryCaptureService(queue=queue)

    service.enqueue_messages(
        thread_id="thread-1",
        user_id="user-1",
        workspace_id="ws-1",
        messages=[{"role": "user", "content": "hello"}],
    )

    queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_persist_conversation_returns_zero():
    service = MemoryCaptureService(queue=MagicMock())

    count = await service.persist_conversation(
        user_id="user-1",
        conversation_text="user: remember IEEE",
        workspace_context="ws-1",
        source="test",
    )

    assert count == 0

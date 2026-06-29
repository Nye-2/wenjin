"""Tests for memory capture helpers."""

from __future__ import annotations

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.memory.capture import (
    enqueue_memory_capture,
    select_incremental_capture_messages,
)


def test_select_incremental_capture_messages_keeps_latest_turn_pair():
    messages = [
        HumanMessage(content="用户问题 1"),
        AIMessage(content="助手回答 1"),
        HumanMessage(content="用户问题 2"),
        AIMessage(content="助手回答 2"),
    ]

    selected = select_incremental_capture_messages(messages)

    assert len(selected) == 2
    assert isinstance(selected[0], HumanMessage)
    assert isinstance(selected[1], AIMessage)
    assert selected[0].content == "用户问题 2"
    assert selected[1].content == "助手回答 2"


def test_select_incremental_capture_messages_supports_dict_roles():
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]

    selected = select_incremental_capture_messages(messages)

    assert selected == [
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]


def test_enqueue_memory_capture_is_retired_and_does_not_enqueue_jobs():
    queue = MagicMock()
    queue.enqueue = MagicMock()

    enqueue_memory_capture(
        thread_id="thread-1",
        user_id="user-1",
        workspace_id="ws-1",
        messages=[
            HumanMessage(content="旧问题"),
            AIMessage(content="旧回答"),
            HumanMessage(content="新问题"),
            AIMessage(content="新回答"),
        ],
        source="test",
        queue=queue,
    )

    queue.enqueue.assert_not_called()

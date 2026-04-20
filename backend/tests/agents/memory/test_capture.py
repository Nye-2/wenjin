"""Tests for memory capture helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


@pytest.mark.asyncio
async def test_enqueue_memory_capture_uses_configured_context_window():
    queue = MagicMock()
    queue.enqueue = MagicMock()

    with patch(
        "src.agents.memory.capture.extract_and_persist_knowledge",
        AsyncMock(),
    ) as mock_persist, patch(
        "src.config.config_loader.get_app_config",
        return_value=SimpleNamespace(memory=SimpleNamespace(max_context_turns=1)),
    ):
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

        callback = queue.enqueue.call_args.kwargs["callback"]
        await callback(
            "thread-1",
            [
                HumanMessage(content="旧问题"),
                AIMessage(content="旧回答"),
                HumanMessage(content="新问题"),
                AIMessage(content="新回答"),
            ],
        )

    persisted_text = mock_persist.await_args.args[1]
    assert "旧问题" not in persisted_text
    assert "旧回答" not in persisted_text
    assert "新问题" in persisted_text
    assert "新回答" in persisted_text

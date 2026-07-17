"""Tests for run wait view projections."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.gateway.services.chat_turn_views import build_chat_turn_wait_payload
from src.runtime.chat_turns import ChatTurnRunManager


@pytest.mark.asyncio
async def test_build_wait_payload_reads_thread_messages_from_projection() -> None:
    run_manager = ChatTurnRunManager()
    record = (await run_manager.create_or_reject("thread-1")).record
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        title="Thread",
        model="test-model",
        skill=None,
        messages=[{"role": "user", "content": "raw bridge"}],
    )
    thread_service = SimpleNamespace(
        get_thread=AsyncMock(return_value=thread),
        list_thread_messages=AsyncMock(return_value=[{"role": "user", "content": "canonical projection"}]),
    )

    payload = await build_chat_turn_wait_payload(
        record=record,
        actor_id="user-1",
        handler=SimpleNamespace(thread_service=thread_service),
        run_manager=run_manager,
    )

    assert payload["values"]["messages"][0]["content"] == "canonical projection"
    thread_service.list_thread_messages.assert_awaited_once_with(thread)

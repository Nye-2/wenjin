"""Spec §5.2 — SSE emits per-block 'block' events; legacy 'assistant_message' is gone.

Each AgentBlock in the assistant message is published as a separate
{"type":"block","message_id":...,"block":{...}} event so the frontend can
render blocks progressively and group by message_id.

For messages that come back without a `blocks` field (e.g. before T6 wires
parse_with_fallback into the agent), the worker coerces the free-text
`content` into a single TextBlock — defensive coercion, not a compat shim.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.application.handlers.thread_turn_handler import ThreadStreamDelta
from src.application.results import PreparedThreadTurn, ThreadTurnRequest
from src.runtime.chat_turns import ChatTurnRunManager, run_chat_turn
from src.runtime.stream_bridge import END_SENTINEL, MemoryStreamBridge


@dataclass
class _StreamRunWithBlocks:
    blocks: list[dict[str, Any]]
    content: str = ""

    async def _iterate(self):
        if False:
            yield ThreadStreamDelta(kind="content", text="")

    def __aiter__(self):
        return self._iterate()

    async def wait_completed(self):
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.blocks:
            msg["blocks"] = self.blocks
        return SimpleNamespace(assistant_message=msg)

    async def aclose(self):
        return None


class _Handler:
    def __init__(self, stream_run) -> None:
        self._stream_run = stream_run
        self.interruptions: list[bool] = []

    async def prepare_turn(self, request: ThreadTurnRequest, *, actor_id: str):
        thread = SimpleNamespace(id="thread-1", workspace_id="ws-1", skill=None)
        return PreparedThreadTurn(request=request, thread=thread)

    def stream_turn(self, prepared: PreparedThreadTurn, *, actor_id: str):
        return self._stream_run

    async def handle_run_interruption(self, prepared, *, rollback):
        self.interruptions.append(rollback)


def _request() -> ThreadTurnRequest:
    return ThreadTurnRequest(message="hi", workspace_id="ws-1", thread_id="thread-1")


async def _collect(bridge: MemoryStreamBridge, run_id: str) -> list[tuple[str, Any]]:
    """Returns (event_name, data) tuples from the stream."""
    events: list[tuple[str, Any]] = []
    async for item in bridge.subscribe(run_id):
        if item is END_SENTINEL:
            break
        events.append((item.event, item.data))
    return events


@pytest.mark.asyncio
async def test_emits_one_block_event_per_block_with_shared_message_id():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")

    blocks = [
        {"kind": "text", "content": "好"},
        {"kind": "status_line", "label": "phase 1 done", "run_id": "r1", "tone": "info"},
    ]
    handler = _Handler(_StreamRunWithBlocks(blocks=blocks))

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()):
        await run_chat_turn(
            bridge, manager, record,
            handler=handler,  # type: ignore[arg-type]
            request=_request(),
            actor_id="user-1",
        )

    events = await _collect(bridge, record.run_id)
    block_events = [(name, payload) for name, payload in events if name == "block"]

    assert len(block_events) == 2
    msg_ids = {p["message_id"] for _, p in block_events}
    assert len(msg_ids) == 1, f"expected single message_id, got {msg_ids}"
    assert block_events[0][1]["block"] == blocks[0]
    assert block_events[1][1]["block"] == blocks[1]


@pytest.mark.asyncio
async def test_no_legacy_assistant_message_event_emitted():
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")
    handler = _Handler(_StreamRunWithBlocks(blocks=[{"kind": "text", "content": "hi"}]))

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()):
        await run_chat_turn(
            bridge, manager, record,
            handler=handler,  # type: ignore[arg-type]
            request=_request(),
            actor_id="user-1",
        )

    events = await _collect(bridge, record.run_id)
    assert not any(name == "assistant_message" for name, _ in events)


@pytest.mark.asyncio
async def test_missing_blocks_coerces_content_to_text_block():
    """Defensive: legacy free-text replies get wrapped as a single TextBlock."""
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")
    handler = _Handler(_StreamRunWithBlocks(blocks=[], content="hello"))

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()):
        await run_chat_turn(
            bridge, manager, record,
            handler=handler,  # type: ignore[arg-type]
            request=_request(),
            actor_id="user-1",
        )

    events = await _collect(bridge, record.run_id)
    block_events = [(name, payload) for name, payload in events if name == "block"]
    assert len(block_events) == 1
    assert block_events[0][1]["block"] == {"kind": "text", "content": "hello"}


@pytest.mark.asyncio
async def test_empty_blocks_and_empty_content_emits_no_blocks():
    """Edge case: nothing to emit. No spurious empty TextBlock."""
    manager = ChatTurnRunManager()
    bridge = MemoryStreamBridge()
    record = await manager.create_or_reject("thread-1")
    handler = _Handler(_StreamRunWithBlocks(blocks=[], content=""))

    with patch("src.runtime.chat_turns.worker.set_thread_status", new=AsyncMock()):
        await run_chat_turn(
            bridge, manager, record,
            handler=handler,  # type: ignore[arg-type]
            request=_request(),
            actor_id="user-1",
        )

    events = await _collect(bridge, record.run_id)
    block_events = [(name, payload) for name, payload in events if name == "block"]
    assert len(block_events) == 0

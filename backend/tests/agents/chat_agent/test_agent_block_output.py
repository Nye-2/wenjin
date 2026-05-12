"""Tests for AgentBlock structured-output wiring in _MiddlewareWrappedAgent.

Spec: Plan 1 Task 6 — parse_with_fallback feeds response_blocks which
the worker streams as per-block SSE events.
"""
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.chat_agent.agent import (
    _concat_text_blocks,
    _MiddlewareWrappedAgent,
)
from src.agents.chat_agent.blocks import AgentMessage, StatusLineBlock, TextBlock
from src.agents.chat_agent.prompts.jargon import assert_no_jargon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_message(content: str) -> Any:
    """Return a minimal LangChain-like message object."""
    return SimpleNamespace(content=content)


def _make_agent(*, scripted_agent_msg: AgentMessage, base_model: Any = None) -> _MiddlewareWrappedAgent:
    """Build a _MiddlewareWrappedAgent whose inner agent returns a fixed state.

    The inner agent returns a ThreadState dict with a single message whose
    content will be passed through parse_with_fallback (monkeypatched in each
    test to return scripted_agent_msg).
    """
    inner_agent = MagicMock()
    inner_agent.ainvoke = AsyncMock(
        return_value={
            "messages": [_make_fake_message("这是一个测试回复。")],
            "response_blocks": [],
        }
    )

    if base_model is None:
        base_model = MagicMock()

    wrapped = _MiddlewareWrappedAgent(
        inner_agent,
        middlewares=[],  # no middlewares keeps _apply_after_model reachable
        default_config={"configurable": {"thread_id": "test-thread-1", "model_name": "gpt-4o-mini"}},
        base_model=base_model,
    )
    return wrapped


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lead_agent_reply_carries_blocks(monkeypatch):
    """Agent reply.blocks contains the AgentBlock dump for downstream SSE."""
    expected_msg = AgentMessage(
        blocks=[
            StatusLineBlock(label="正在处理", run_id="test-thread-1"),
            TextBlock(content="这是回复正文。"),
        ]
    )

    monkeypatch.setattr(
        "src.agents.chat_agent.structured_output.parse_with_fallback",
        AsyncMock(return_value=expected_msg),
    )

    agent = _make_agent(scripted_agent_msg=expected_msg)
    result = await agent.ainvoke(
        {"messages": [_make_fake_message("你好")]},
        config={"configurable": {"thread_id": "test-thread-1", "model_name": "gpt-4o-mini"}},
    )

    assert isinstance(result, dict), "ainvoke should return a dict (ThreadState)"
    blocks = result.get("response_blocks") or []
    assert len(blocks) == 2, f"Expected 2 blocks, got {len(blocks)}: {blocks}"
    assert blocks[0]["kind"] == "status_line"
    assert blocks[1]["kind"] == "text"
    assert blocks[1]["content"] == "这是回复正文。"


@pytest.mark.asyncio
async def test_lead_agent_reply_content_concatenates_text_blocks(monkeypatch):
    """reply.content is joined text from all TextBlocks in the AgentMessage."""
    msg = AgentMessage(
        blocks=[
            TextBlock(content="第一段。"),
            StatusLineBlock(label="状态", run_id="r1"),
            TextBlock(content="第二段。"),
        ]
    )

    monkeypatch.setattr(
        "src.agents.chat_agent.structured_output.parse_with_fallback",
        AsyncMock(return_value=msg),
    )

    agent = _make_agent(scripted_agent_msg=msg)
    result = await agent.ainvoke(
        {"messages": [_make_fake_message("测试")]},
        config={"configurable": {"thread_id": "t2", "model_name": "gpt-4o-mini"}},
    )

    blocks = result.get("response_blocks") or []
    # The text blocks are present in the response_blocks
    text_blocks_in_result = [b for b in blocks if b.get("kind") == "text"]
    assert len(text_blocks_in_result) == 2

    # _concat_text_blocks joins only TextBlock.content values
    joined = _concat_text_blocks(msg)
    assert joined == "第一段。\n\n第二段。"


@pytest.mark.asyncio
async def test_lead_agent_reply_no_jargon_in_output(monkeypatch):
    """assert_no_jargon passes on the structured reply (no internal tokens leak)."""
    msg = AgentMessage(
        blocks=[
            TextBlock(content="你的研究方向很有潜力，建议从三个角度展开。"),
            TextBlock(content="需要进一步收集文献以支持论点。"),
        ]
    )

    monkeypatch.setattr(
        "src.agents.chat_agent.structured_output.parse_with_fallback",
        AsyncMock(return_value=msg),
    )

    agent = _make_agent(scripted_agent_msg=msg)
    await agent.ainvoke(
        {"messages": [_make_fake_message("帮我分析")]},
        config={"configurable": {"thread_id": "t3", "model_name": "gpt-4o-mini"}},
    )

    # assert_no_jargon should not raise for clean output
    assert_no_jargon(msg)


@pytest.mark.asyncio
async def test_lead_agent_skips_structured_output_when_no_base_model():
    """If _base_model is None, response_blocks stays empty (graceful degradation)."""
    inner_agent = MagicMock()
    inner_agent.ainvoke = AsyncMock(
        return_value={
            "messages": [_make_fake_message("plain text reply")],
            "response_blocks": [],
        }
    )

    wrapped = _MiddlewareWrappedAgent(
        inner_agent,
        middlewares=[],
        default_config={"configurable": {"thread_id": "t4", "model_name": "gpt-4o-mini"}},
        base_model=None,  # no model — structured output disabled
    )

    result = await wrapped.ainvoke(
        {"messages": [_make_fake_message("hello")]},
        config={"configurable": {"thread_id": "t4", "model_name": "gpt-4o-mini"}},
    )

    blocks = result.get("response_blocks") or []
    assert blocks == [], f"Expected empty blocks, got {blocks}"


@pytest.mark.asyncio
async def test_lead_agent_preserves_existing_response_blocks(monkeypatch):
    """If response_blocks are already set (e.g. by middleware), parse_with_fallback is skipped."""
    prebuilt_block = {"kind": "text", "content": "from middleware"}

    inner_agent = MagicMock()
    inner_agent.ainvoke = AsyncMock(
        return_value={
            "messages": [_make_fake_message("agent reply")],
            "response_blocks": [prebuilt_block],
        }
    )

    fake_parse = AsyncMock(
        return_value=AgentMessage(blocks=[TextBlock(content="should not appear")])
    )
    monkeypatch.setattr("src.agents.chat_agent.structured_output.parse_with_fallback", fake_parse)

    base_model = MagicMock()
    wrapped = _MiddlewareWrappedAgent(
        inner_agent,
        middlewares=[],
        default_config={"configurable": {"thread_id": "t5", "model_name": "gpt-4o-mini"}},
        base_model=base_model,
    )

    result = await wrapped.ainvoke(
        {"messages": [_make_fake_message("hi")]},
        config={"configurable": {"thread_id": "t5", "model_name": "gpt-4o-mini"}},
    )

    # parse_with_fallback must NOT have been called
    fake_parse.assert_not_called()

    blocks = result.get("response_blocks") or []
    assert len(blocks) == 1
    assert blocks[0]["content"] == "from middleware"

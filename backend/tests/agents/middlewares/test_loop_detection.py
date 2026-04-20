"""Tests for LoopDetectionMiddleware."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.middlewares.loop_detection import LoopDetectionMiddleware


def _state_with_tool_call(*, file_path: str = "a.txt") -> dict:
    return {
        "messages": [
            HumanMessage(content="请读取文件"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "read_file",
                        "args": {"file_path": file_path},
                    }
                ],
            ),
        ]
    }


@pytest.mark.asyncio
async def test_loop_detection_warns_on_repetition():
    middleware = LoopDetectionMiddleware(
        warn_threshold=2,
        hard_limit=5,
        tool_freq_warn=100,
        tool_freq_hard_limit=200,
    )
    config = {"configurable": {"thread_id": "thread-1"}}

    first = await middleware.after_model(_state_with_tool_call(), config)
    assert first == {}

    second = await middleware.after_model(_state_with_tool_call(), config)
    assert second
    updated_last = second["messages"][-1]
    assert isinstance(updated_last, AIMessage)
    assert "[LOOP DETECTED]" in str(updated_last.content)
    assert len(updated_last.tool_calls or []) == 1


@pytest.mark.asyncio
async def test_loop_detection_hard_stops_repetition():
    middleware = LoopDetectionMiddleware(
        warn_threshold=2,
        hard_limit=3,
        tool_freq_warn=100,
        tool_freq_hard_limit=200,
    )
    config = {"configurable": {"thread_id": "thread-hard-stop"}}

    await middleware.after_model(_state_with_tool_call(), config)
    await middleware.after_model(_state_with_tool_call(), config)
    third = await middleware.after_model(_state_with_tool_call(), config)

    assert third
    updated_last = third["messages"][-1]
    assert isinstance(updated_last, AIMessage)
    assert "[FORCED STOP]" in str(updated_last.content)
    assert updated_last.tool_calls == []


@pytest.mark.asyncio
async def test_loop_detection_tool_frequency_hard_stops_varying_args():
    middleware = LoopDetectionMiddleware(
        warn_threshold=100,
        hard_limit=200,
        tool_freq_warn=2,
        tool_freq_hard_limit=3,
    )
    config = {"configurable": {"thread_id": "thread-freq"}}

    await middleware.after_model(_state_with_tool_call(file_path="a.txt"), config)
    await middleware.after_model(_state_with_tool_call(file_path="b.txt"), config)
    third = await middleware.after_model(_state_with_tool_call(file_path="c.txt"), config)

    assert third
    updated_last = third["messages"][-1]
    assert isinstance(updated_last, AIMessage)
    assert "[FORCED STOP]" in str(updated_last.content)
    assert updated_last.tool_calls == []

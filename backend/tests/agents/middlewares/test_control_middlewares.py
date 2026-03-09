"""Tests for control middlewares (SubagentLimit, Clarification)."""

import pytest
from langchain_core.messages import AIMessage

from src.agents.middlewares.subagent_limit import SubagentLimitMiddleware
from src.agents.middlewares.clarification import ClarificationMiddleware


class TestSubagentLimitMiddleware:
    @pytest.mark.asyncio
    async def test_truncates_excess_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=2)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "task", "args": {"prompt": "task1", "subagent_type": "scout", "description": "t1"}},
            {"id": "c2", "name": "task", "args": {"prompt": "task2", "subagent_type": "writer", "description": "t2"}},
            {"id": "c3", "name": "task", "args": {"prompt": "task3", "subagent_type": "analyst", "description": "t3"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert result is not None
        updated_msg = result["messages"][-1]
        task_calls = [tc for tc in updated_msg.tool_calls if tc["name"] == "task"]
        assert len(task_calls) <= 2

    @pytest.mark.asyncio
    async def test_no_truncation_under_limit(self):
        mw = SubagentLimitMiddleware(max_concurrent=3)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "task", "args": {"prompt": "task1", "subagent_type": "scout", "description": "t1"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert result == {}  # No truncation needed

    @pytest.mark.asyncio
    async def test_preserves_non_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=1)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c0", "name": "bash", "args": {"command": "ls"}},
            {"id": "c1", "name": "task", "args": {"prompt": "t1", "subagent_type": "scout", "description": "d1"}},
            {"id": "c2", "name": "task", "args": {"prompt": "t2", "subagent_type": "writer", "description": "d2"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert result is not None
        updated = result["messages"][-1]
        non_task = [tc for tc in updated.tool_calls if tc["name"] != "task"]
        assert len(non_task) == 1  # bash preserved


class TestClarificationMiddleware:
    @pytest.mark.asyncio
    async def test_intercepts_clarification_call(self):
        mw = ClarificationMiddleware()
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "ask_clarification", "args": {"question": "What API version?"}},
        ])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        # Should signal interruption
        assert result is not None

    @pytest.mark.asyncio
    async def test_noop_without_clarification(self):
        mw = ClarificationMiddleware()
        ai_msg = AIMessage(content="Here's the result", tool_calls=[])
        state = {"messages": [ai_msg]}
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert result == {}

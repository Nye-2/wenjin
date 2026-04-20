"""Tests for _MiddlewareWrappedAgent LLM retry/fallback behaviour."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from src.agents.lead_agent.agent import _MiddlewareWrappedAgent
from src.agents.middlewares.llm_error_handling import LLMErrorHandlingMiddleware


class _TransientError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class _FlakyAgent:
    def __init__(self, fail_times: int):
        self._fail_times = fail_times
        self._calls = 0

    async def ainvoke(self, state, config=None, **kwargs):
        self._calls += 1
        if self._calls <= self._fail_times:
            raise _TransientError("temporary overload", 503)
        return {"messages": [AIMessage(content="ok")]}

    def invoke(self, state, config=None, **kwargs):
        self._calls += 1
        if self._calls <= self._fail_times:
            raise _TransientError("temporary overload", 503)
        return {"messages": [AIMessage(content="ok")]}


@pytest.mark.asyncio
async def test_wrapper_retries_transient_llm_errors_then_succeeds():
    middleware = LLMErrorHandlingMiddleware(
        retry_max_attempts=3,
        retry_base_delay_ms=1,
        retry_cap_delay_ms=1,
    )
    wrapped = _MiddlewareWrappedAgent(
        _FlakyAgent(fail_times=2),
        middlewares=[middleware],
        default_config={"configurable": {"model_name": "gpt-4o"}},
    )

    result = await wrapped.ainvoke(
        {"messages": []},
        config={"configurable": {"thread_id": "thread-1"}},
    )

    assert isinstance(result, dict)
    assert "messages" in result
    assert str(result["messages"][-1].content) == "ok"


@pytest.mark.asyncio
async def test_wrapper_degrades_to_ai_message_for_non_retriable_provider_error():
    class _QuotaAgent:
        async def ainvoke(self, state, config=None, **kwargs):
            raise Exception("insufficient_quota")

        def invoke(self, state, config=None, **kwargs):
            raise Exception("insufficient_quota")

    middleware = LLMErrorHandlingMiddleware(
        retry_max_attempts=1,
        retry_base_delay_ms=1,
        retry_cap_delay_ms=1,
    )
    wrapped = _MiddlewareWrappedAgent(
        _QuotaAgent(),
        middlewares=[middleware],
        default_config={"configurable": {"model_name": "gpt-4o"}},
    )

    result = await wrapped.ainvoke(
        {"messages": []},
        config={"configurable": {"thread_id": "thread-2"}},
    )

    assert isinstance(result, dict)
    assert "messages" in result
    assert "额度" in str(result["messages"][-1].content)

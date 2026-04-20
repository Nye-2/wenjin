"""Tests for LLMErrorHandlingMiddleware."""

from __future__ import annotations

import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.middlewares.llm_error_handling import LLMErrorHandlingMiddleware


class _TransientError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.asyncio
async def test_before_model_skips_when_circuit_is_open():
    middleware = LLMErrorHandlingMiddleware()
    middleware._circuit_state = "open"
    middleware._circuit_open_until = time.time() + 60

    state = {"messages": [HumanMessage(content="hello")]}
    updates = await middleware.before_model(state, {"configurable": {}})

    assert updates is not None
    assert updates.get("_skip_model_call") is True
    assert isinstance(updates["messages"][-1], AIMessage)
    assert "熔断" in str(updates["messages"][-1].content)


@pytest.mark.asyncio
async def test_on_model_error_generates_quota_fallback_message():
    middleware = LLMErrorHandlingMiddleware()
    state = {"messages": [HumanMessage(content="hello")]}

    updates = await middleware.on_model_error(
        state=state,
        config={"configurable": {}},
        error=Exception("insufficient_quota"),
    )

    assert updates is not None
    assert isinstance(updates["messages"][-1], AIMessage)
    assert "额度" in str(updates["messages"][-1].content)


def test_classify_error_marks_transient_status_codes():
    middleware = LLMErrorHandlingMiddleware()
    retriable, reason = middleware.classify_error(_TransientError("temporary failure", 503))

    assert retriable is True
    assert reason == "transient"


def test_record_failure_trips_circuit_breaker():
    middleware = LLMErrorHandlingMiddleware(
        circuit_failure_threshold=2,
        circuit_recovery_timeout_sec=120,
    )

    middleware.record_failure()
    assert middleware._circuit_state == "closed"

    middleware.record_failure()
    assert middleware._circuit_state == "open"
    assert middleware._circuit_open_until > time.time()

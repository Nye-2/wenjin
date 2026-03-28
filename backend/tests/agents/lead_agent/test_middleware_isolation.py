"""Tests for middleware error isolation."""

import pytest
from src.agents.middlewares.base import Middleware


class _CrashingMiddleware(Middleware):
    """Middleware that always raises."""
    async def before_model(self, state, config):
        raise RuntimeError("middleware boom")

    async def after_model(self, state, config):
        raise RuntimeError("middleware boom after")

    async def before_tool(self, state, config, tool_name, tool_args):
        raise RuntimeError("before_tool boom")

    async def after_tool(self, state, config, tool_name, tool_result):
        raise RuntimeError("after_tool boom")


class _PassthroughMiddleware(Middleware):
    """Middleware that records it was called."""
    def __init__(self):
        self.before_model_called = False
        self.after_model_called = False

    async def before_model(self, state, config):
        self.before_model_called = True
        return {}

    async def after_model(self, state, config):
        self.after_model_called = True
        return {}


class TestMiddlewareErrorIsolation:
    @pytest.mark.asyncio
    async def test_crashing_before_model_does_not_block_chain(self):
        from src.agents.lead_agent.agent import middleware_before_model

        passthrough = _PassthroughMiddleware()
        middlewares = [_CrashingMiddleware(), passthrough]
        state = {"messages": []}
        config = {"configurable": {}}

        result = await middleware_before_model(state, config, middlewares)

        assert passthrough.before_model_called is True
        assert result is not None

    @pytest.mark.asyncio
    async def test_crashing_after_model_does_not_block_chain(self):
        from src.agents.lead_agent.agent import middleware_after_model

        passthrough = _PassthroughMiddleware()
        middlewares = [_CrashingMiddleware(), passthrough]
        state = {"messages": []}
        config = {"configurable": {}}

        result = await middleware_after_model(state, config, middlewares)

        assert passthrough.after_model_called is True
        assert result is not None

    @pytest.mark.asyncio
    async def test_all_middlewares_crash_returns_original_state(self):
        from src.agents.lead_agent.agent import middleware_before_model

        state = {"messages": ["hello"]}
        config = {"configurable": {}}

        result = await middleware_before_model(state, config, [_CrashingMiddleware()])

        assert result == state

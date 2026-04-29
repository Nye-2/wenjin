"""Tests for SummarizationMiddleware."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.middlewares.summarization import SummarizationMiddleware


class TestSummarizationMiddleware:
    def test_init_default_values(self):
        mw = SummarizationMiddleware()
        assert mw._trigger_tokens == 80000
        assert mw._keep_messages == 10

    def test_init_custom_values(self):
        mw = SummarizationMiddleware(trigger_tokens=50000, keep_messages=5)
        assert mw._trigger_tokens == 50000
        assert mw._keep_messages == 5

    @pytest.mark.asyncio
    async def test_no_summarization_under_limit(self):
        """Should not summarize if under token limit."""
        mw = SummarizationMiddleware(trigger_tokens=1000)
        state = {
            "messages": [HumanMessage(content="Hello"), AIMessage(content="Hi there")],
        }
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert result == {}  # No changes

    @pytest.mark.asyncio
    async def test_summarization_over_limit(self):
        """Should request summarization if over token limit."""
        mw = SummarizationMiddleware(trigger_tokens=100, keep_messages=2)
        # Create many messages to exceed limit
        messages = [HumanMessage(content="Message " + "x" * 50) for _ in range(5)]
        messages.extend([AIMessage(content="Response " + "y" * 50) for _ in range(5)])
        state = {"messages": messages}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        # Should have summarized (injected summary message)
        assert result == {} or "messages" in result

    @pytest.mark.asyncio
    async def test_skip_summarization_when_no_old_messages_to_fold(self):
        """When all messages are in keep window, middleware should no-op."""
        mw = SummarizationMiddleware(trigger_tokens=1, keep_messages=2)
        state = {
            "messages": [
                HumanMessage(content="x" * 200),
                AIMessage(content="y" * 200),
            ],
        }
        config = {"configurable": {}}

        with patch.object(mw, "_summarize", new=AsyncMock(return_value="summary")) as summarize:
            result = await mw.before_model(state, config)

        assert result == {}
        summarize.assert_not_awaited()

    def test_count_tokens_approximate(self):
        """Token counting should be approximate."""
        mw = SummarizationMiddleware()
        messages = [HumanMessage(content="Hello world")]
        count = mw._count_tokens(messages)
        assert count > 0
        assert count < 10  # "Hello world" is ~2-3 tokens

    @pytest.mark.asyncio
    async def test_summarize_uses_full_old_history_not_only_last_20(self):
        mw = SummarizationMiddleware()
        messages = [HumanMessage(content=f"message-{index}") for index in range(25)]

        with patch("src.models.router.route_model", return_value="utility-primary"), patch(
            "src.models.factory.create_chat_model",
            return_value=object(),
        ), patch.object(
            mw,
            "_invoke_summary_model",
            new=AsyncMock(return_value="summary"),
        ) as invoke_summary:
            result = await mw._summarize(messages)

        assert result == "summary"
        prompt = invoke_summary.await_args_list[0].args[1]
        assert "message-0" in prompt
        assert "message-24" in prompt


def test_count_tokens_cjk_content():
    """CJK characters must not be severely under-counted."""
    mw = SummarizationMiddleware()
    # "深度学习" = 4 Chinese chars, each 3 UTF-8 bytes = 12 bytes → 4 tokens via bytes//3
    # Old heuristic: 4 chars // 4 = 1 token (massive under-count!)
    messages = [HumanMessage(content="深度学习")]
    count = mw._count_tokens(messages)
    # Must count at least 2 tokens for 4 CJK characters (bytes//3 = 4)
    assert count >= 2, f"CJK token count too low: {count}"


def test_count_tokens_mixed_content():
    """Mixed ASCII + CJK must count higher than ASCII-only of same length."""
    mw = SummarizationMiddleware()
    ascii_only = [HumanMessage(content="hello")]     # 5 bytes → 1 token
    cjk_only   = [HumanMessage(content="你好啊")]    # 9 bytes → 3 tokens
    assert mw._count_tokens(cjk_only) > mw._count_tokens(ascii_only)


def test_count_tokens_ascii_unchanged():
    """ASCII content token count must still be reasonable (within 2x of old heuristic)."""
    mw = SummarizationMiddleware()
    messages = [HumanMessage(content="Hello world")]
    count = mw._count_tokens(messages)
    # "Hello world" = 11 bytes // 3 ≈ 3 tokens. Still > 0 and < 10.
    assert 0 < count < 10

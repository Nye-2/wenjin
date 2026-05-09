"""Tests for CompactMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agents.chat_agent.middlewares.compact import CompactMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_large_messages(n: int, chars_each: int = 4000) -> list:
    """Create n HumanMessage objects each with ~chars_each chars of content."""
    return [HumanMessage(content="x" * chars_each) for _ in range(n)]


def _make_compact_runner(
    summary: str = "Previous conversation summary.",
    facts: list | None = None,
    decisions: list | None = None,
) -> AsyncMock:
    return AsyncMock(
        return_value={
            "summary": summary,
            "facts": facts or [],
            "decisions": decisions or [],
        }
    )


def _make_middleware(
    *,
    threshold: float = 0.5,
    keep_last: int = 3,
    model_context_limit: int = 1000,
    memory_service: Any = None,
    decisions_service: Any = None,
    compact_runner: Any = None,
) -> CompactMiddleware:
    return CompactMiddleware(
        threshold=threshold,
        keep_last=keep_last,
        model_context_limit=model_context_limit,
        memory_service=memory_service or AsyncMock(),
        decisions_service=decisions_service or AsyncMock(),
        compact_runner=compact_runner or _make_compact_runner(),
    )


from typing import Any

CONFIG = {
    "configurable": {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
    }
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNoCompactUnderThreshold:
    @pytest.mark.asyncio
    async def test_small_messages_state_unchanged(self):
        """When messages are small, state is returned unmodified."""
        middleware = _make_middleware(threshold=0.8, model_context_limit=200_000)
        msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
        state = {"messages": msgs}

        result = await middleware.before_model(state, CONFIG)

        assert result is state  # same object — unchanged
        assert result["messages"] == msgs

    @pytest.mark.asyncio
    async def test_empty_messages_state_unchanged(self):
        middleware = _make_middleware(threshold=0.8, model_context_limit=200_000)
        state = {"messages": []}
        result = await middleware.before_model(state, CONFIG)
        assert result["messages"] == []

    @pytest.mark.asyncio
    async def test_compact_runner_not_called_under_threshold(self):
        runner = _make_compact_runner()
        middleware = _make_middleware(
            threshold=0.8, model_context_limit=200_000, compact_runner=runner
        )
        state = {"messages": [HumanMessage(content="short")]}
        await middleware.before_model(state, CONFIG)
        runner.assert_not_awaited()


class TestCompactTriggersAboveThreshold:
    @pytest.mark.asyncio
    async def test_large_messages_triggers_compaction(self):
        """Above threshold: state.messages is replaced with summary + last_n."""
        # 10 messages * 4000 chars / 4 = 10_000 tokens
        # model_context_limit=10_000, threshold=0.8 → needs 8_000+ tokens → triggers
        runner = _make_compact_runner(summary="All the old stuff summarised.")
        middleware = _make_middleware(
            threshold=0.8,
            keep_last=3,
            model_context_limit=10_000,
            compact_runner=runner,
        )
        msgs = _make_large_messages(10, chars_each=4000)
        state = {"messages": msgs}

        result = await middleware.before_model(state, CONFIG)

        # Runner was called
        runner.assert_awaited_once()
        # Result messages = 1 SystemMessage + last 3
        assert len(result["messages"]) == 4
        assert isinstance(result["messages"][0], SystemMessage)
        assert result["messages"][0].content == "All the old stuff summarised."
        # Last 3 messages preserved
        assert result["messages"][1:] == msgs[-3:]

    @pytest.mark.asyncio
    async def test_only_old_turns_sent_to_runner(self):
        """compact_runner receives messages EXCEPT the last keep_last."""
        captured = []

        async def capturing_runner(old_turns, workspace_type):
            captured.extend(old_turns)
            return {"summary": "x", "facts": [], "decisions": []}

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            compact_runner=capturing_runner,
        )
        # 4 messages each with 200 chars → 800 chars / 4 = 200 tokens
        # 200 / 100 = 2.0 ≥ 0.5 → triggers
        msgs = [HumanMessage(content="a" * 200) for _ in range(4)]
        await middleware.before_model({"messages": msgs}, CONFIG)

        # Should have received first 2 (len - keep_last = 4 - 2 = 2)
        assert len(captured) == 2
        assert captured == msgs[:2]


class TestCompactWritesFactsToMemory:
    @pytest.mark.asyncio
    async def test_facts_written_to_memory(self):
        """Extracted facts are persisted to memory_service.add_facts."""
        memory = MagicMock()
        memory.add_facts = AsyncMock(return_value=[])

        facts = [
            {"category": "preference", "content": "APA style", "confidence": 1.0}
        ]
        runner = _make_compact_runner(facts=facts)

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            memory_service=memory,
            compact_runner=runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        await middleware.before_model({"messages": msgs}, CONFIG)

        memory.add_facts.assert_awaited_once()
        # Check workspace_id is passed
        call_args = memory.add_facts.call_args
        assert call_args[0][0] == "ws-1"
        # Check one FactCreate was created
        fact_list = call_args[0][1]
        assert len(fact_list) == 1
        assert fact_list[0].content == "APA style"

    @pytest.mark.asyncio
    async def test_no_facts_skips_memory_write(self):
        """When facts list is empty, memory_service.add_facts is not called."""
        memory = MagicMock()
        memory.add_facts = AsyncMock()

        runner = _make_compact_runner(facts=[])
        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            memory_service=memory,
            compact_runner=runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        await middleware.before_model({"messages": msgs}, CONFIG)

        memory.add_facts.assert_not_awaited()


class TestCompactWritesDecisions:
    @pytest.mark.asyncio
    async def test_decisions_written(self):
        """Extracted decisions are persisted via decisions_service.set."""
        decisions_svc = MagicMock()
        decisions_svc.set = AsyncMock(return_value=MagicMock(id="d-1"))

        decisions = [
            {"key": "citation_style", "value": "APA", "confidence": 0.9},
            {"key": "language", "value": "en"},
        ]
        runner = _make_compact_runner(decisions=decisions)

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            decisions_service=decisions_svc,
            compact_runner=runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        await middleware.before_model({"messages": msgs}, CONFIG)

        assert decisions_svc.set.await_count == 2
        # Check first call args
        first_call = decisions_svc.set.call_args_list[0]
        assert first_call[0][0] == "ws-1"
        assert first_call[1]["key"] == "citation_style"
        assert first_call[1]["value"] == "APA"
        assert first_call[1]["confidence"] == 0.9
        assert first_call[1]["extracted_by"] == "compact_agent"

    @pytest.mark.asyncio
    async def test_decision_default_confidence(self):
        """Decisions without confidence default to 1.0."""
        decisions_svc = MagicMock()
        decisions_svc.set = AsyncMock(return_value=MagicMock(id="d-1"))

        decisions = [{"key": "lang", "value": "zh"}]  # no confidence
        runner = _make_compact_runner(decisions=decisions)

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            decisions_service=decisions_svc,
            compact_runner=runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        await middleware.before_model({"messages": msgs}, CONFIG)

        call_kwargs = decisions_svc.set.call_args[1]
        assert call_kwargs["confidence"] == 1.0


class TestCompactSwallowsRunnerFailure:
    @pytest.mark.asyncio
    async def test_runner_exception_returns_original_state(self):
        """If compact_runner raises, state is returned unchanged."""
        async def failing_runner(turns, ws_type):
            raise RuntimeError("LLM unavailable")

        memory = MagicMock()
        memory.add_facts = AsyncMock()

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            memory_service=memory,
            compact_runner=failing_runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        state = {"messages": msgs}
        result = await middleware.before_model(state, CONFIG)

        # State unchanged
        assert result is state
        # Memory was not written
        memory.add_facts.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_runner_failure_logged(self, caplog):
        """Runner failure produces a log message."""
        import logging

        async def failing_runner(turns, ws_type):
            raise RuntimeError("boom")

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            compact_runner=failing_runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        with caplog.at_level(logging.ERROR):
            await middleware.before_model({"messages": msgs}, CONFIG)

        assert any("compact_runner" in r.message for r in caplog.records)


class TestCompactSwallowsMemoryWriteFailure:
    @pytest.mark.asyncio
    async def test_memory_failure_does_not_prevent_state_update(self):
        """Even if memory.add_facts raises, compaction still updates state."""
        memory = MagicMock()
        memory.add_facts = AsyncMock(side_effect=Exception("DB error"))

        facts = [{"category": "pref", "content": "X", "confidence": 1.0}]
        runner = _make_compact_runner(summary="Summary text", facts=facts)

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            memory_service=memory,
            compact_runner=runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        result = await middleware.before_model({"messages": msgs}, CONFIG)

        # State IS updated despite memory failure
        assert isinstance(result["messages"][0], SystemMessage)
        assert result["messages"][0].content == "Summary text"

    @pytest.mark.asyncio
    async def test_decisions_failure_does_not_prevent_state_update(self):
        """Even if decisions_service.set raises, compaction still updates state."""
        decisions_svc = MagicMock()
        decisions_svc.set = AsyncMock(side_effect=Exception("DB error"))

        decisions = [{"key": "k", "value": "v"}]
        runner = _make_compact_runner(summary="Summary", decisions=decisions)

        middleware = _make_middleware(
            threshold=0.5,
            keep_last=2,
            model_context_limit=100,
            decisions_service=decisions_svc,
            compact_runner=runner,
        )

        msgs = _make_large_messages(5, chars_each=200)
        result = await middleware.before_model({"messages": msgs}, CONFIG)

        # State IS updated
        assert isinstance(result["messages"][0], SystemMessage)
        assert result["messages"][0].content == "Summary"

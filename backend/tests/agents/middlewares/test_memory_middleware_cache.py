"""MemoryMiddleware: TTL cache for build_memory_context."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.middlewares.memory import MemoryMiddleware


@pytest.mark.asyncio
async def test_memory_context_is_cached_on_second_call():
    """Second call with same user/workspace must not hit build_memory_context."""
    mw = MemoryMiddleware(enabled=True, inject_enabled=True, cache_ttl=60)

    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {"user_id": "user-1", "workspace_id": "ws-1"}}

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        new_callable=AsyncMock,
        return_value="User prefers concise answers.",
    ) as mock_build:
        result1 = await mw.before_model(state, config)
        result2 = await mw.before_model(state, config)

    assert mock_build.call_count == 1, "build_memory_context should only be called once"
    assert result1 == result2
    assert result1.get("memory_context") == "User prefers concise answers."


@pytest.mark.asyncio
async def test_cache_expires_after_ttl():
    """Cache entry must expire after TTL and trigger a fresh DB call."""
    mw = MemoryMiddleware(enabled=True, inject_enabled=True, cache_ttl=0.05)  # 50ms TTL

    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {"user_id": "user-1", "workspace_id": "ws-1"}}

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        new_callable=AsyncMock,
        return_value="ctx",
    ) as mock_build:
        await mw.before_model(state, config)
        await asyncio.sleep(0.1)  # Wait for TTL to expire
        await mw.before_model(state, config)

    assert mock_build.call_count == 2, "Expired cache must trigger a new DB call"


@pytest.mark.asyncio
async def test_cache_invalidated_after_capture():
    """after_model must invalidate the cache so next before_model fetches fresh context."""
    from langchain_core.messages import AIMessage, HumanMessage

    mw = MemoryMiddleware(enabled=True, inject_enabled=True, capture_enabled=True, cache_ttl=300)

    state_before = {"messages": [], "workspace_id": "ws-1"}
    state_after = {
        "messages": [
            HumanMessage(content="I prefer bullet points."),
            AIMessage(content="Noted, I will use bullet points."),
        ],
        "workspace_id": "ws-1",
    }
    config = {"configurable": {"user_id": "user-1", "workspace_id": "ws-1", "thread_id": "t-1"}}

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        new_callable=AsyncMock,
        return_value="ctx",
    ) as mock_build, patch(
        "src.agents.middlewares.memory.enqueue_memory_capture",
    ):
        await mw.before_model(state_before, config)  # populates cache
        await mw.after_model(state_after, config)    # should invalidate
        await mw.before_model(state_before, config)  # should re-fetch

    assert mock_build.call_count == 2, "Cache must be invalidated after capture"


@pytest.mark.asyncio
async def test_different_users_have_separate_cache_entries():
    """Cache must be scoped per (user_id, workspace_id)."""
    mw = MemoryMiddleware(enabled=True, inject_enabled=True, cache_ttl=300)

    state = {"messages": [], "workspace_id": "ws-1"}
    config_a = {"configurable": {"user_id": "user-A", "workspace_id": "ws-1"}}
    config_b = {"configurable": {"user_id": "user-B", "workspace_id": "ws-1"}}

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        new_callable=AsyncMock,
        side_effect=["ctx-A", "ctx-B"],
    ) as mock_build:
        result_a = await mw.before_model(state, config_a)
        result_b = await mw.before_model(state, config_b)

    assert mock_build.call_count == 2
    assert result_a.get("memory_context") == "ctx-A"
    assert result_b.get("memory_context") == "ctx-B"


@pytest.mark.asyncio
async def test_cache_evicts_oldest_entry_at_capacity():
    """When cache reaches max_cache_size, the oldest entry is evicted (LRU)."""
    mw = MemoryMiddleware(enabled=True, inject_enabled=True, cache_ttl=300, max_cache_size=2)

    state = {"messages": [], "workspace_id": "ws-1"}
    config_a = {"configurable": {"user_id": "user-A", "workspace_id": "ws-1"}}
    config_b = {"configurable": {"user_id": "user-B", "workspace_id": "ws-1"}}
    config_c = {"configurable": {"user_id": "user-C", "workspace_id": "ws-1"}}

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        new_callable=AsyncMock,
        side_effect=["ctx-A", "ctx-B", "ctx-C"],
    ):
        await mw.before_model(state, config_a)  # inserts user-A (size=1)
        await mw.before_model(state, config_b)  # inserts user-B (size=2, at capacity)
        await mw.before_model(state, config_c)  # evicts LRU (user-A), inserts user-C

    assert "user-A:ws-1" not in mw._memory_cache, "Oldest entry must be evicted"
    assert "user-B:ws-1" in mw._memory_cache
    assert "user-C:ws-1" in mw._memory_cache
    assert len(mw._memory_cache) == 2


def test_invalid_max_cache_size_raises():
    """Constructing MemoryMiddleware with max_cache_size < 1 must raise ValueError."""
    with pytest.raises(ValueError, match="max_cache_size must be >= 1"):
        MemoryMiddleware(max_cache_size=0)


@pytest.mark.asyncio
async def test_lru_promotion_saves_recently_hit_entry():
    """A cache hit promotes an entry to MRU; on eviction the true LRU is removed."""
    mw = MemoryMiddleware(enabled=True, inject_enabled=True, cache_ttl=300, max_cache_size=2)

    state = {"messages": [], "workspace_id": "ws-1"}
    config_a = {"configurable": {"user_id": "user-A", "workspace_id": "ws-1"}}
    config_b = {"configurable": {"user_id": "user-B", "workspace_id": "ws-1"}}
    config_c = {"configurable": {"user_id": "user-C", "workspace_id": "ws-1"}}

    with patch(
        "src.agents.middlewares.memory.build_memory_context",
        new_callable=AsyncMock,
        side_effect=["ctx-A", "ctx-B", "ctx-C"],
    ):
        await mw.before_model(state, config_a)   # insert user-A (size=1)
        await mw.before_model(state, config_b)   # insert user-B (size=2, full)
        # Hit user-A — promotes it to MRU; user-B is now the LRU
        await mw.before_model(state, config_a)   # cache hit, no new build_memory_context call
        # Insert user-C — should evict user-B (the LRU), not user-A
        await mw.before_model(state, config_c)   # insert user-C, evicts user-B

    assert "user-B:ws-1" not in mw._memory_cache, "LRU entry (user-B) must be evicted"
    assert "user-A:ws-1" in mw._memory_cache, "Promoted entry (user-A) must be retained"
    assert "user-C:ws-1" in mw._memory_cache
    assert len(mw._memory_cache) == 2


def test_cache_set_with_eviction_logs(caplog):
    """Evicting a cache entry should emit a debug log."""
    import logging
    import time

    middleware = MemoryMiddleware(queue=None, enabled=True, max_cache_size=1)
    # Pre-populate cache
    middleware._memory_cache["old-key"] = ("old-context", time.monotonic())

    with caplog.at_level(logging.DEBUG, logger="src.agents.middlewares.memory"):
        middleware._cache_set("new-key", "new-context")

    assert any("evict" in r.message.lower() for r in caplog.records)
    assert "old-key" not in middleware._memory_cache
    assert "new-key" in middleware._memory_cache


@pytest.mark.asyncio
async def test_after_model_requires_thread_id_when_capture_enabled():
    """Memory capture must not silently collapse into a shared default thread."""
    from langchain_core.messages import AIMessage, HumanMessage

    middleware = MemoryMiddleware(enabled=True, inject_enabled=False, capture_enabled=True)
    state = {
        "messages": [
            HumanMessage(content="Remember that I prefer concise answers."),
            AIMessage(content="Understood."),
        ],
        "workspace_id": "ws-1",
    }

    with patch("src.agents.middlewares.memory.enqueue_memory_capture") as enqueue_mock:
        with pytest.raises(RuntimeError, match="MemoryMiddleware requires config.configurable.thread_id"):
            await middleware.after_model(
                state,
                {"configurable": {"user_id": "user-1", "workspace_id": "ws-1"}},
            )

    enqueue_mock.assert_not_called()

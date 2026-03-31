# Agent Harness & Memory System Optimizations

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix six performance, correctness, and resilience issues found in the lead agent harness and memory system.

**Architecture:** Six independent tasks in priority order. Tasks 1-2 hit the hot path (every chat request). Tasks 3-4 are correctness/safety fixes. Tasks 5-6 are resilience guards. Each task is self-contained — no task depends on another completing first.

**Tech Stack:** Python 3.12, asyncio, LangGraph, threading, collections.OrderedDict.

---

## Baseline check (run before starting)

```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/ tests/subagents/ -q --tb=no --continue-on-collection-errors 2>&1 | tail -5
```

Note the pass/fail count. Pre-existing failures are expected (circular import in test_feature_bridge.py).

---

## Task 1 — MemoryMiddleware: per-user TTL cache for `build_memory_context`

**Context:** `src/agents/middlewares/memory.py:110` calls `build_memory_context()` (a DB query) on **every single chat message** in `before_model`. This adds 100–500 ms of latency per request. The memory context for a given user/workspace changes infrequently (only when `after_model` extracts new knowledge), so a short TTL cache eliminates most of this overhead.

**Files:**
- Modify: `backend/src/agents/middlewares/memory.py`
- Test: `backend/tests/agents/middlewares/test_memory_middleware_cache.py` (create new)

---

### Step 1: Write the failing test

Create `backend/tests/agents/middlewares/test_memory_middleware_cache.py`:

```python
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
```

Run to verify FAIL:
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_memory_middleware_cache.py -v 2>&1 | tail -15
```
Expected: FAILED — `TypeError: MemoryMiddleware.__init__() got an unexpected keyword argument 'cache_ttl'`

---

### Step 2: Implement the cache

In `backend/src/agents/middlewares/memory.py`, make these changes:

**a) Add `time` import** at the top of the file (after existing imports):
```python
import time
```

**b) Add `cache_ttl` parameter** to `__init__`:
```python
def __init__(
    self,
    queue: MemoryQueue | None = None,
    enabled: bool = True,
    min_messages: int = 2,
    inject_enabled: bool = True,
    capture_enabled: bool = True,
    cache_ttl: float = 300.0,   # <-- add this
):
    ...
    self._cache_ttl = cache_ttl
    self._memory_cache: dict[str, tuple[str, float]] = {}  # key → (context, cached_at)
```

**c) Add `_cache_key` helper method**:
```python
def _cache_key(self, user_id: str, workspace_id: str | None) -> str:
    return f"{user_id}:{workspace_id or ''}"
```

**d) Replace the `build_memory_context` call** in `before_model` with a cache-aware version.

Find this block (around line 110):
```python
memory_context = await build_memory_context(
    str(user_id),
    str(workspace_id) if workspace_id else None,
    current_context=conversation_context or None,
)
if not memory_context:
    return {}
return {"memory_context": memory_context}
```

Replace with:
```python
cache_key = self._cache_key(str(user_id), str(workspace_id) if workspace_id else None)
cached_context, cached_at = self._memory_cache.get(cache_key, ("", 0.0))
if cached_context and time.monotonic() - cached_at < self._cache_ttl:
    return {"memory_context": cached_context}

memory_context = await build_memory_context(
    str(user_id),
    str(workspace_id) if workspace_id else None,
    current_context=conversation_context or None,
)
if not memory_context:
    return {}
self._memory_cache[cache_key] = (memory_context, time.monotonic())
return {"memory_context": memory_context}
```

**e) Invalidate cache in `after_model`** right after the `enqueue_memory_capture` call:
```python
# Invalidate cache so the next request fetches fresh context
cache_key = self._cache_key(str(user_id) if user_id else "", str(workspace_id) if workspace_id else None)
self._memory_cache.pop(cache_key, None)
```

---

### Step 3: Run the tests
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_memory_middleware_cache.py tests/agents/middleware/test_memory.py -v 2>&1 | tail -20
```
Expected: all PASSED.

### Step 4: Commit
```bash
cd /home/cjz/wenjin/backend && git add src/agents/middlewares/memory.py tests/agents/middlewares/test_memory_middleware_cache.py && git commit -m "perf(memory): add per-user TTL cache to MemoryMiddleware.before_model"
```

---

## Task 2 — DynamicToolNode: tool refresh TTL + change detection

**Context:** `src/agents/lead_agent/dynamic_tools.py:67-78` — `_refresh_tools()` is called on **every tool invocation** (`_func` and `_afunc` both call it). It re-imports and rebuilds the entire tool registry every time. This is expensive because `get_available_tools()` loads modules. The tool set almost never changes mid-session (only on MCP reconnect). A 60-second TTL with tool-name change detection eliminates redundant rebuilds.

**Files:**
- Modify: `backend/src/agents/lead_agent/dynamic_tools.py`
- Test: `backend/tests/agents/lead_agent/test_dynamic_tools.py` (extend existing)

---

### Step 1: Write the failing test

Read `backend/tests/agents/lead_agent/test_dynamic_tools.py` first to understand existing tests, then **append** to it:

```python
def test_tool_refresh_skips_rebuild_within_ttl():
    """_refresh_tools should not rebuild if called again within TTL and tools unchanged."""
    call_count = 0

    def counting_loader():
        nonlocal call_count
        call_count += 1
        return [echo_tool]

    node = DynamicToolNode(counting_loader, refresh_interval=60.0)
    node._refresh_tools()   # first call: load
    node._refresh_tools()   # second call: should skip (within TTL, names unchanged)

    assert call_count == 1, "Loader must only be called once within TTL when tools unchanged"


def test_tool_refresh_reloads_after_ttl(monkeypatch):
    """_refresh_tools must reload after TTL expires."""
    import time

    call_count = 0

    def counting_loader():
        nonlocal call_count
        call_count += 1
        return [echo_tool]

    node = DynamicToolNode(counting_loader, refresh_interval=0.05)  # 50ms TTL
    node._refresh_tools()

    # Advance time past TTL
    monkeypatch.setattr(time, "monotonic", lambda: node._last_refresh + 1.0)
    node._refresh_tools()

    assert call_count == 2, "Loader must be called again after TTL expires"


def test_tool_refresh_forced_when_tools_change():
    """_refresh_tools must rebuild immediately when the tool set changes."""
    tools_v1 = [echo_tool]

    @tool
    async def extra_tool(x: int) -> int:
        """Return x."""
        return x

    tools_v2 = [echo_tool, extra_tool]
    iteration = [0]

    def versioned_loader():
        return tools_v1 if iteration[0] == 0 else tools_v2

    node = DynamicToolNode(versioned_loader, refresh_interval=60.0)
    node._refresh_tools()  # loads v1, stores names

    iteration[0] = 1
    # Force TTL bypass: mark last refresh as stale
    node._last_refresh = 0.0
    node._refresh_tools()  # detects new tool, rebuilds

    assert "extra_tool" in node.tools_by_name
```

Run to verify FAIL:
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/lead_agent/test_dynamic_tools.py::test_tool_refresh_skips_rebuild_within_ttl -v 2>&1 | tail -10
```
Expected: FAILED — `TypeError: DynamicToolNode.__init__() got an unexpected keyword argument 'refresh_interval'`

---

### Step 2: Implement TTL + change detection

In `backend/src/agents/lead_agent/dynamic_tools.py`, make these changes:

**a) Add `time` import** at the top (after existing imports):
```python
import time
```

**b) Add `refresh_interval` parameter** to `__init__`:
```python
def __init__(
    self,
    tool_loader: ToolLoader,
    *,
    name: str = "tools",
    middlewares: Sequence[Middleware] | None = None,
    tags: list[str] | None = None,
    handle_tool_errors: bool | str | Callable[..., str] | tuple[type[Exception], ...] = True,
    messages_key: str = "messages",
    refresh_interval: float = 60.0,   # <-- add this
) -> None:
    self._tool_loader = tool_loader
    self._refresh_lock = threading.RLock()
    self._middlewares = list(middlewares or [])
    self._refresh_interval = refresh_interval
    self._last_refresh: float = 0.0
    self._last_tool_names: frozenset[str] = frozenset()
    super().__init__(
        list(tool_loader()),
        ...
    )
```

**c) Replace `_refresh_tools`** with a TTL-aware + change-detection version:

```python
def _refresh_tools(self) -> None:
    with self._refresh_lock:
        now = time.monotonic()
        if now - self._last_refresh < self._refresh_interval:
            return  # Within TTL: skip full reload
        tools = list(self._tool_loader())
        new_names = frozenset(tool.name for tool in tools)
        if new_names == self._last_tool_names and self._last_refresh > 0:
            self._last_refresh = now  # Reset TTL without rebuilding
            return
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.tool_to_state_args = {
            tool.name: _get_state_args(tool)
            for tool in tools
        }
        self.tool_to_store_arg = {
            tool.name: _get_store_arg(tool)
            for tool in tools
        }
        self._last_tool_names = new_names
        self._last_refresh = now
```

**d) Add `invalidate_tool_cache` method** (for MCP reconnects):
```python
def invalidate_tool_cache(self) -> None:
    """Force a full tool reload on the next invocation (e.g. after MCP reconnect)."""
    with self._refresh_lock:
        self._last_refresh = 0.0
```

---

### Step 3: Run the tests
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/lead_agent/test_dynamic_tools.py -v 2>&1 | tail -20
```
Expected: all PASSED.

### Step 4: Commit
```bash
cd /home/cjz/wenjin/backend && git add src/agents/lead_agent/dynamic_tools.py tests/agents/lead_agent/test_dynamic_tools.py && git commit -m "perf(tools): add TTL + change detection to DynamicToolNode._refresh_tools"
```

---

## Task 3 — SummarizationMiddleware: UTF-8 bytes heuristic for CJK-aware token counting

**Context:** `src/agents/middlewares/summarization.py:71-80` uses `chars // 4` to estimate token count. This under-counts CJK (Chinese, Japanese, Korean) content — each Chinese character is typically 1–2 tokens in Claude but only 1 char. The UTF-8 byte count is a better proxy: ASCII chars = 1 byte ≈ 0.25 tokens, CJK chars = 3 bytes ≈ 1 token. Using `bytes // 3` gives a more accurate estimate across languages without adding dependencies.

**Files:**
- Modify: `backend/src/agents/middlewares/summarization.py`
- Test: `backend/tests/agents/middlewares/test_summarization.py` (extend existing)

---

### Step 1: Write the failing test

Read `backend/tests/agents/middlewares/test_summarization.py` first, then **append**:

```python
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
```

Run to verify the CJK test FAILS:
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_summarization.py::test_count_tokens_cjk_content -v 2>&1 | tail -10
```
Expected: FAILED — assertion `count >= 2` fails (old code returns 1 for "深度学习")

---

### Step 2: Replace the token counter

In `backend/src/agents/middlewares/summarization.py`, replace the `_count_tokens` method body:

Old:
```python
def _count_tokens(self, messages: list) -> int:
    total_chars = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total_chars += len(content)
    return total_chars // 4
```

New:
```python
def _count_tokens(self, messages: list) -> int:
    """Estimate token count using UTF-8 byte length.

    Heuristic: 3 bytes ≈ 1 token. This handles CJK content significantly
    better than the naive chars//4 approach (a single Chinese character is
    3 UTF-8 bytes and roughly 1 token, whereas chars//4 would give 0.25).
    """
    total_bytes = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total_bytes += len(content.encode("utf-8"))
    return total_bytes // 3
```

---

### Step 3: Run all summarization tests
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_summarization.py -v 2>&1 | tail -15
```
Expected: all PASSED.

### Step 4: Commit
```bash
cd /home/cjz/wenjin/backend && git add src/agents/middlewares/summarization.py tests/agents/middlewares/test_summarization.py && git commit -m "fix(summarization): use UTF-8 byte heuristic for CJK-aware token counting"
```

---

## Task 4 — GraphTemplateRegistry: LRU eviction to prevent unbounded growth

**Context:** `src/subagents/graph.py:55-80` — `GraphTemplateRegistry` has no size limit. Each unique subagent config creates a cached graph (compiled LangGraph object), and this cache grows forever. In long-running deployments with varied subagent configs, this will exhaust memory.

**Files:**
- Modify: `backend/src/subagents/graph.py`
- Test: `backend/tests/subagents/test_graph.py` (extend existing)

---

### Step 1: Write the failing test

Read `backend/tests/subagents/test_graph.py` first, then **append**:

```python
def test_registry_evicts_oldest_entry_at_max_size():
    """Registry must evict the LRU (oldest) entry when max_size is reached."""
    from src.subagents.graph import GraphTemplateRegistry

    registry = GraphTemplateRegistry(max_size=3)
    g1, g2, g3, g4 = MagicMock(), MagicMock(), MagicMock(), MagicMock()

    registry.register("a", g1)
    registry.register("b", g2)
    registry.register("c", g3)
    assert registry.count == 3

    # Adding a 4th entry must evict the oldest ("a")
    registry.register("d", g4)
    assert registry.count == 3
    assert registry.get("a") is None, "Oldest entry 'a' must have been evicted"
    assert registry.get("d") is g4


def test_registry_get_moves_entry_to_most_recent():
    """Accessing an entry must make it the most recently used (not evicted next)."""
    from src.subagents.graph import GraphTemplateRegistry

    registry = GraphTemplateRegistry(max_size=2)
    g1, g2, g3 = MagicMock(), MagicMock(), MagicMock()

    registry.register("a", g1)
    registry.register("b", g2)

    # Access "a" to mark it as recently used
    assert registry.get("a") is g1

    # Adding "c" must evict "b" (LRU), not "a"
    registry.register("c", g3)
    assert registry.get("b") is None, "'b' should have been evicted as LRU"
    assert registry.get("a") is g1, "'a' should survive (was recently accessed)"
    assert registry.get("c") is g3


def test_registry_default_max_size_is_50():
    """Default max_size must be 50."""
    from src.subagents.graph import GraphTemplateRegistry

    registry = GraphTemplateRegistry()
    assert registry.max_size == 50
```

Run to verify FAIL:
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/subagents/test_graph.py::test_registry_evicts_oldest_entry_at_max_size -v 2>&1 | tail -10
```
Expected: FAILED — `TypeError: GraphTemplateRegistry.__init__() got an unexpected keyword argument 'max_size'`

---

### Step 2: Implement LRU eviction

In `backend/src/subagents/graph.py`, change `GraphTemplateRegistry`:

**a) Add import** at the top of the file:
```python
from collections import OrderedDict
```

**b) Replace the class body**:

```python
class GraphTemplateRegistry:
    """LRU-evicting registry for compiled subagent graph templates.

    Prevents unbounded memory growth by evicting the least-recently-used
    entry when the registry reaches max_size.
    """

    def __init__(self, max_size: int = 50) -> None:
        """Initialize with a size cap.

        Args:
            max_size: Maximum number of graphs to keep. The LRU entry is
                      evicted when this limit is reached. Default: 50.
        """
        self._templates: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    @property
    def max_size(self) -> int:
        """Return the configured maximum registry size."""
        return self._max_size

    @property
    def count(self) -> int:
        """Return the number of registered templates."""
        with self._lock:
            return len(self._templates)

    def register(self, name: str, graph: Any) -> None:
        """Register a graph template, evicting the LRU entry if at capacity.

        Args:
            name: Cache key (typically a hash of the task config).
            graph: Compiled LangGraph object.
        """
        with self._lock:
            if name in self._templates:
                # Move to end (most recently used)
                self._templates.move_to_end(name)
            else:
                if len(self._templates) >= self._max_size:
                    # Evict least-recently-used (first item)
                    self._templates.popitem(last=False)
                self._templates[name] = graph

    def get(self, name: str) -> Any | None:
        """Get a registered template and mark it as recently used.

        Args:
            name: Template cache key.

        Returns:
            The graph object, or None if not found.
        """
        with self._lock:
            if name not in self._templates:
                return None
            self._templates.move_to_end(name)
            return self._templates[name]

    def clear(self) -> None:
        """Remove all registered templates."""
        with self._lock:
            self._templates.clear()
```

---

### Step 3: Run graph registry tests
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/subagents/test_graph.py -v 2>&1 | tail -20
```
Expected: all PASSED.

### Step 4: Commit
```bash
cd /home/cjz/wenjin/backend && git add src/subagents/graph.py tests/subagents/test_graph.py && git commit -m "fix(subagents): add LRU eviction to GraphTemplateRegistry (max_size=50)"
```

---

## Task 5 — Timeout guards on context-loading middlewares

**Context:** Four middlewares call external services in `before_model` with no timeout:
- `workspace_context.py:38` — DB query via `workspace_service.get()`
- `literature_context.py:59` — `index_service.get_workspace_toc_summary()`
- `knowledge_context.py:78` — `artifact_service.list_by_workspace()`
- `memory.py:110` — `build_memory_context()` (already has cache from Task 1, but can still timeout on cold miss)

A slow or unresponsive service hangs the entire agent request. Wrapping each call with `asyncio.wait_for(..., timeout=5.0)` and falling back to `{}` keeps the agent working even when backing services are degraded.

**Files:**
- Modify: `backend/src/agents/middlewares/workspace_context.py`
- Modify: `backend/src/agents/middlewares/literature_context.py`
- Modify: `backend/src/agents/middlewares/knowledge_context.py`
- Modify: `backend/src/agents/middlewares/memory.py`
- Test: `backend/tests/agents/middlewares/test_context_timeouts.py` (create new)

---

### Step 1: Write the failing tests

Create `backend/tests/agents/middlewares/test_context_timeouts.py`:

```python
"""Context-loading middlewares must degrade gracefully on timeout."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.middlewares.knowledge_context import KnowledgeContextMiddleware
from src.agents.middlewares.literature_context import LiteratureContextMiddleware
from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware


async def _slow_coro(*args, **kwargs):
    """Simulates a service call that never finishes."""
    await asyncio.sleep(60)
    return "should not reach here"


@pytest.mark.asyncio
async def test_workspace_context_timeout_returns_empty():
    """WorkspaceContextMiddleware must return {} on service timeout."""
    slow_service = AsyncMock()
    slow_service.get.side_effect = _slow_coro

    mw = WorkspaceContextMiddleware(slow_service, timeout=0.05)
    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {}}

    result = await mw.before_model(state, config)
    assert result == {} or result.get("workspace_type") is None


@pytest.mark.asyncio
async def test_literature_context_timeout_returns_empty():
    """LiteratureContextMiddleware must return {} on service timeout."""
    slow_service = AsyncMock()
    slow_service.get_workspace_toc_summary.side_effect = _slow_coro

    mw = LiteratureContextMiddleware(slow_service, timeout=0.05)
    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {}}

    result = await mw.before_model(state, config)
    assert "literature_context" not in result or result["literature_context"] == ""


@pytest.mark.asyncio
async def test_knowledge_context_timeout_returns_empty():
    """KnowledgeContextMiddleware must return {} on service timeout."""
    slow_service = AsyncMock()
    slow_service.list_by_workspace.side_effect = _slow_coro

    mw = KnowledgeContextMiddleware(slow_service, timeout=0.05)
    state = {"messages": [], "workspace_id": "ws-1"}
    config = {"configurable": {}}

    result = await mw.before_model(state, config)
    assert result == {} or result.get("knowledge_context") == ""
```

Run to verify FAIL:
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_context_timeouts.py -v 2>&1 | tail -15
```
Expected: FAILED — `TypeError: WorkspaceContextMiddleware.__init__() got an unexpected keyword argument 'timeout'`

---

### Step 2: Add timeout to WorkspaceContextMiddleware

In `backend/src/agents/middlewares/workspace_context.py`, add `asyncio` import and `timeout` parameter:

```python
import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class WorkspaceContextMiddleware(Middleware):
    def __init__(self, workspace_service, timeout: float = 5.0):
        self.workspace_service = workspace_service
        self._timeout = timeout

    async def before_model(self, state: ThreadState, config: RunnableConfig) -> dict[str, Any]:
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        try:
            workspace = await asyncio.wait_for(
                self.workspace_service.get(workspace_id),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "WorkspaceContextMiddleware: timed out loading workspace %s (%.1fs); "
                "proceeding without workspace context",
                workspace_id,
                self._timeout,
            )
            return {}
        if not workspace:
            return dict(state)

        return {
            **state,
            "workspace_type": workspace.type,
            "discipline": workspace.discipline,
            "workspace_config": workspace.config,
        }
```

---

### Step 3: Add timeout to LiteratureContextMiddleware

In `backend/src/agents/middlewares/literature_context.py`:

```python
import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class LiteratureContextMiddleware(Middleware):
    def __init__(self, index_service, timeout: float = 5.0):
        self.index_service = index_service
        self._timeout = timeout

    async def before_model(self, state: ThreadState, config: RunnableConfig) -> dict[str, Any]:
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        try:
            toc_summary = await asyncio.wait_for(
                self.index_service.get_workspace_toc_summary(workspace_id),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "LiteratureContextMiddleware: timed out loading TOC for workspace %s (%.1fs); "
                "proceeding without literature context",
                workspace_id,
                self._timeout,
            )
            return {}

        if not toc_summary:
            return dict(state)

        return {
            **state,
            "literature_context": toc_summary,
        }
```

---

### Step 4: Add timeout to KnowledgeContextMiddleware

In `backend/src/agents/middlewares/knowledge_context.py`, add `asyncio`, `logging` imports, `timeout` parameter, and wrap `list_by_workspace`:

```python
import asyncio
import logging
# (keep existing imports)

logger = logging.getLogger(__name__)

class KnowledgeContextMiddleware(Middleware):
    def __init__(self, artifact_service, timeout: float = 5.0):
        self.artifact_service = artifact_service
        self._timeout = timeout

    async def before_model(self, state: ThreadState, config: RunnableConfig) -> dict[str, Any]:
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        try:
            artifacts = await asyncio.wait_for(
                self.artifact_service.list_by_workspace(workspace_id),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "KnowledgeContextMiddleware: timed out loading artifacts for workspace %s (%.1fs)",
                workspace_id,
                self._timeout,
            )
            return {}

        knowledge_context = self._build_knowledge_graph(artifacts)
        return {
            **state,
            "knowledge_context": knowledge_context,
        }
```

---

### Step 5: Add timeout to MemoryMiddleware.before_model

In `backend/src/agents/middlewares/memory.py`, wrap the `build_memory_context` call (which may happen on cache miss):

Find the call to `build_memory_context` (after the cache check added in Task 1):
```python
memory_context = await build_memory_context(
    str(user_id),
    str(workspace_id) if workspace_id else None,
    current_context=conversation_context or None,
)
```

Replace with:
```python
try:
    memory_context = await asyncio.wait_for(
        build_memory_context(
            str(user_id),
            str(workspace_id) if workspace_id else None,
            current_context=conversation_context or None,
        ),
        timeout=5.0,
    )
except asyncio.TimeoutError:
    logger.warning(
        "MemoryMiddleware: timed out loading memory context for user %s (5.0s); "
        "proceeding without memory context",
        user_id,
    )
    return {}
```

Also add `import asyncio` at the top of `memory.py` if not already present.

---

### Step 6: Run the timeout tests
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/middlewares/test_context_timeouts.py tests/agents/middlewares/test_academic_middlewares.py tests/agents/middlewares/test_workspace_context.py -v 2>&1 | tail -20
```
Expected: all PASSED.

### Step 7: Commit
```bash
cd /home/cjz/wenjin/backend && git add \
  src/agents/middlewares/workspace_context.py \
  src/agents/middlewares/literature_context.py \
  src/agents/middlewares/knowledge_context.py \
  src/agents/middlewares/memory.py \
  tests/agents/middlewares/test_context_timeouts.py && \
  git commit -m "feat(middlewares): add asyncio timeout guards to all context-loading middlewares"
```

---

## Task 6 — DynamicToolNode: log warning on sync/async bridge thread spawn

**Context:** `src/agents/lead_agent/dynamic_tools.py:81-103` — `_run_coroutine_sync` spawns a `threading.Thread` when called from within a running event loop (i.e., from `_func`). This is a known-problematic pattern: thread-local DB sessions don't transfer across threads, and spawning threads from async contexts is expensive. In production, LangGraph uses `ainvoke`, so `_func` is rarely called. Adding a warning log makes this visible when it unexpectedly occurs.

**Files:**
- Modify: `backend/src/agents/lead_agent/dynamic_tools.py`
- Test: `backend/tests/agents/lead_agent/test_dynamic_tools.py` (extend existing)

---

### Step 1: Write the failing test

Append to `backend/tests/agents/lead_agent/test_dynamic_tools.py`:

```python
def test_run_coroutine_sync_warns_when_loop_is_running(caplog):
    """_run_coroutine_sync must emit a WARNING when called inside a running event loop."""
    import logging
    import asyncio

    async def _check_warning():
        async def noop():
            return 42

        with caplog.at_level(logging.WARNING, logger="src.agents.lead_agent.dynamic_tools"):
            # We're inside an event loop here; this should trigger the warning
            result = DynamicToolNode._run_coroutine_sync(noop())
        return result

    result = asyncio.run(_check_warning())
    assert result == 42
    assert any("sync" in record.message.lower() or "thread" in record.message.lower()
               for record in caplog.records), (
        "Expected a WARNING log when _run_coroutine_sync spawns a thread inside a running loop"
    )
```

Run to verify FAIL:
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/lead_agent/test_dynamic_tools.py::test_run_coroutine_sync_warns_when_loop_is_running -v 2>&1 | tail -10
```
Expected: FAILED (no warning log emitted currently)

---

### Step 2: Add the warning log

In `backend/src/agents/lead_agent/dynamic_tools.py`, add `logger` and update `_run_coroutine_sync`:

Ensure at the module level (after existing imports):
```python
logger = logging.getLogger(__name__)
```

Replace the thread-spawn branch of `_run_coroutine_sync`:
```python
@staticmethod
def _run_coroutine_sync(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run an async middleware hook from a synchronous tool path.

    NOTE: When called inside a running event loop (LangGraph sync path), this
    spawns a daemon thread with its own event loop. This is a known limitation:
    thread-local database sessions do not transfer across threads. Prefer the
    async path (_afunc / ainvoke) wherever possible.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    logger.warning(
        "DynamicToolNode._run_coroutine_sync: called inside a running event loop. "
        "Spawning a daemon thread to avoid nested-loop deadlock. "
        "This is safe for stateless middleware but may fail if the coroutine "
        "uses thread-local DB sessions. Prefer ainvoke() over invoke()."
    )

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # noqa: BLE001
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return cast(T, result.get("value"))
```

---

### Step 3: Run the test
```bash
cd /home/cjz/wenjin/backend && python -m pytest tests/agents/lead_agent/test_dynamic_tools.py -v 2>&1 | tail -15
```
Expected: all PASSED.

### Step 4: Commit
```bash
cd /home/cjz/wenjin/backend && git add src/agents/lead_agent/dynamic_tools.py tests/agents/lead_agent/test_dynamic_tools.py && git commit -m "fix(tools): log warning when _run_coroutine_sync spawns thread inside event loop"
```

---

## Acceptance criteria

```bash
cd /home/cjz/wenjin/backend

# Task 1: memory cache
python -m pytest tests/agents/middlewares/test_memory_middleware_cache.py -v

# Task 2: tool refresh TTL
python -m pytest tests/agents/lead_agent/test_dynamic_tools.py -v

# Task 3: token counter
python -m pytest tests/agents/middlewares/test_summarization.py -v

# Task 4: graph LRU
python -m pytest tests/subagents/test_graph.py -v

# Task 5: context timeouts
python -m pytest tests/agents/middlewares/test_context_timeouts.py tests/agents/middlewares/test_academic_middlewares.py -v

# Task 6: sync/async warning
python -m pytest tests/agents/lead_agent/test_dynamic_tools.py -v

# Full suite
python -m pytest tests/ -q --tb=short --continue-on-collection-errors 2>&1 | tail -5
```

Manual checks:
- [ ] `grep -c "self._memory_cache" src/agents/middlewares/memory.py` → 3 (init, get, invalidate)
- [ ] `grep "time.monotonic" src/agents/lead_agent/dynamic_tools.py` → present
- [ ] `grep "encode.*utf-8" src/agents/middlewares/summarization.py` → present
- [ ] `grep "OrderedDict" src/subagents/graph.py` → present
- [ ] `grep "wait_for" src/agents/middlewares/workspace_context.py src/agents/middlewares/literature_context.py src/agents/middlewares/knowledge_context.py` → each has it
- [ ] `grep "WARNING" src/agents/lead_agent/dynamic_tools.py` → present

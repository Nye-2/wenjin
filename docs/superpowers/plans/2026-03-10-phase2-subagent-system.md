# Phase 2: Subagent System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete subagent system with dual-layer concurrency control, SSE event streaming, and LangGraph integration.

**Architecture:** Hybrid layered architecture with GlobalSubagentManager as singleton coordinator, DualLayerLimiter for global + per-thread concurrency, SubagentEventStream for SSE, SubagentExecutor for task execution with LangGraph.

**Tech Stack:** Python 3.12+, asyncio, LangGraph, FastAPI SSE, Pydantic v2

**Spec Document:** `docs/superpowers/specs/2026-03-10-phase2-subagent-system-design.md`

---

## File Structure

```
backend/src/subagents/
├── __init__.py              # Public exports
├── models.py                # SubagentStatus, SubagentTask, SubagentEvent, SubagentResult
├── config.py                # SubagentConfig
├── limiter.py               # ConcurrencyLimiter, DualLayerLimiter
├── events.py                # SubagentEventStream
├── graph.py                 # GraphTemplateRegistry, create_default_subagent_graph
├── executor.py              # SubagentExecutor
└── manager.py               # ThreadContext, GlobalSubagentManager

backend/src/api/
└── subagents.py             # FastAPI routes

backend/tests/subagents/
├── __init__.py
├── conftest.py              # Fixtures
├── test_models.py
├── test_limiter.py
├── test_events.py
├── test_graph.py
├── test_executor.py
├── test_manager.py
└── test_api.py
```

---

## Chunk 1: Data Models and Configuration

### Task 1.1: SubagentStatus Enum and SubagentTask

**Files:**
- Create: `backend/src/subagents/__init__.py`
- Create: `backend/src/subagents/models.py`
- Create: `backend/tests/subagents/__init__.py`
- Create: `backend/tests/subagents/test_models.py`

- [ ] **Step 1: Write the failing test for SubagentStatus**

```python
# tests/subagents/test_models.py
"""Tests for subagent data models."""

import pytest
from datetime import datetime
from src.subagents.models import (
    SubagentStatus,
    SubagentTask,
    SubagentEvent,
    SubagentResult,
)


class TestSubagentStatus:
    """Tests for SubagentStatus enum."""

    def test_status_values(self):
        """Should have all required status values."""
        assert SubagentStatus.PENDING == "pending"
        assert SubagentStatus.RUNNING == "running"
        assert SubagentStatus.COMPLETED == "completed"
        assert SubagentStatus.FAILED == "failed"
        assert SubagentStatus.CANCELLED == "cancelled"
        assert SubagentStatus.TIMEOUT == "timeout"

    def test_status_is_string_enum(self):
        """Should be a string enum."""
        assert isinstance(SubagentStatus.PENDING, str)
        assert SubagentStatus.PENDING.value == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_models.py::TestSubagentStatus -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Create package init file**

```python
# src/subagents/__init__.py
"""Subagent system for parallel AI task execution."""

from .models import (
    SubagentStatus,
    SubagentTask,
    SubagentEvent,
    SubagentResult,
)
from .config import SubagentConfig
from .limiter import ConcurrencyLimiter, DualLayerLimiter
from .events import SubagentEventStream
from .graph import GraphTemplateRegistry, create_default_subagent_graph
from .executor import SubagentExecutor
from .manager import ThreadContext, GlobalSubagentManager

__all__ = [
    # Models
    "SubagentStatus",
    "SubagentTask",
    "SubagentEvent",
    "SubagentResult",
    # Config
    "SubagentConfig",
    # Limiter
    "ConcurrencyLimiter",
    "DualLayerLimiter",
    # Events
    "SubagentEventStream",
    # Graph
    "GraphTemplateRegistry",
    "create_default_subagent_graph",
    # Executor
    "SubagentExecutor",
    # Manager
    "ThreadContext",
    "GlobalSubagentManager",
]
```

- [ ] **Step 4: Write SubagentStatus and SubagentTask models**

```python
# src/subagents/models.py
"""Data models for subagent system."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SubagentStatus(str, Enum):
    """Status of a subagent task."""

    PENDING = "pending"       # Waiting for execution slot
    RUNNING = "running"       # Currently executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Execution failed
    CANCELLED = "cancelled"   # Cancelled by user
    TIMEOUT = "timeout"       # Exceeded time limit


@dataclass
class SubagentTask:
    """Definition of a subagent task."""

    task_id: str
    thread_id: str
    prompt: str
    graph_template: str = "default"
    max_turns: int = 10
    timeout: int = 900  # 15 minutes
    created_at: datetime = field(default_factory=datetime.now)
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "prompt": self.prompt,
            "graph_template": self.graph_template,
            "max_turns": self.max_turns,
            "timeout": self.timeout,
            "created_at": self.created_at.isoformat(),
            "tools": self.tools,
            "metadata": self.metadata,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_models.py::TestSubagentStatus -v`
Expected: PASS

---

### Task 1.2: SubagentEvent and SubagentResult

**Files:**
- Modify: `backend/src/subagents/models.py`
- Modify: `backend/tests/subagents/test_models.py`

- [ ] **Step 1: Write the failing tests for SubagentEvent**

```python
# Add to tests/subagents/test_models.py

class TestSubagentEvent:
    """Tests for SubagentEvent model."""

    def test_create_event(self):
        """Should create event with required fields."""
        event = SubagentEvent(
            event_type="task_started",
            task_id="task-123",
            thread_id="thread-456",
            data={"prompt": "test"},
        )
        assert event.event_type == "task_started"
        assert event.task_id == "task-123"
        assert event.thread_id == "thread-456"
        assert event.data == {"prompt": "test"}
        assert isinstance(event.timestamp, datetime)

    def test_event_to_sse(self):
        """Should convert to SSE format string."""
        event = SubagentEvent(
            event_type="task_completed",
            task_id="task-123",
            thread_id="thread-456",
            data={"output": "done"},
        )
        sse_str = event.to_sse()
        assert "event: task_completed" in sse_str
        assert "data:" in sse_str
        assert "task-123" in sse_str

    def test_event_to_dict(self):
        """Should serialize to dictionary."""
        event = SubagentEvent(
            event_type="task_failed",
            task_id="task-123",
            thread_id="thread-456",
            data={"error": "oops"},
        )
        d = event.to_dict()
        assert d["event_type"] == "task_failed"
        assert d["task_id"] == "task-123"
        assert isinstance(d["timestamp"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_models.py::TestSubagentEvent -v`
Expected: FAIL

- [ ] **Step 3: Write SubagentEvent model**

```python
# Add to src/subagents/models.py

@dataclass
class SubagentEvent:
    """Event emitted during subagent execution."""

    event_type: str  # task_started, turn_complete, task_completed, task_failed, task_cancelled
    task_id: str
    thread_id: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_sse(self) -> str:
        """Convert to SSE format string."""
        return f"event: {self.event_type}\ndata: {json.dumps(self.to_dict())}\n\n"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_models.py::TestSubagentEvent -v`
Expected: PASS

- [ ] **Step 5: Write the failing tests for SubagentResult**

```python
# Add to tests/subagents/test_models.py

class TestSubagentResult:
    """Tests for SubagentResult model."""

    def test_create_success_result(self):
        """Should create successful result."""
        result = SubagentResult(
            task_id="task-123",
            status=SubagentStatus.COMPLETED,
            output="Task done",
            turns_used=5,
            duration_seconds=10.5,
        )
        assert result.task_id == "task-123"
        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "Task done"
        assert result.turns_used == 5
        assert result.duration_seconds == 10.5
        assert result.error is None

    def test_create_failed_result(self):
        """Should create failed result."""
        result = SubagentResult(
            task_id="task-456",
            status=SubagentStatus.FAILED,
            error="Something went wrong",
            duration_seconds=2.0,
        )
        assert result.status == SubagentStatus.FAILED
        assert result.error == "Something went wrong"
        assert result.output is None

    def test_result_to_dict(self):
        """Should serialize to dictionary."""
        result = SubagentResult(
            task_id="task-789",
            status=SubagentStatus.TIMEOUT,
            error="Timed out",
            duration_seconds=900.0,
        )
        d = result.to_dict()
        assert d["task_id"] == "task-789"
        assert d["status"] == "timeout"
        assert d["error"] == "Timed out"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_models.py::TestSubagentResult -v`
Expected: FAIL

- [ ] **Step 7: Write SubagentResult model**

```python
# Add to src/subagents/models.py

@dataclass
class SubagentResult:
    """Result of a subagent task execution."""

    task_id: str
    status: SubagentStatus
    output: Optional[str] = None
    error: Optional[str] = None
    turns_used: int = 0
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "turns_used": self.turns_used,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/subagents/__init__.py src/subagents/models.py tests/subagents/__init__.py tests/subagents/test_models.py
git commit -m "feat(subagents): add data models (SubagentStatus, SubagentTask, SubagentEvent, SubagentResult)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 1.3: SubagentConfig

**Files:**
- Create: `backend/src/subagents/config.py`
- Create: `backend/tests/subagents/test_config.py`

- [ ] **Step 1: Write the failing tests for SubagentConfig**

```python
# tests/subagents/test_config.py
"""Tests for subagent configuration."""

import pytest
from src.subagents.config import SubagentConfig


class TestSubagentConfig:
    """Tests for SubagentConfig."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = SubagentConfig()
        assert config.global_max_concurrent == 10
        assert config.per_thread_max_concurrent == 3
        assert config.default_timeout == 900
        assert config.max_timeout == 3600
        assert config.sse_heartbeat_interval == 30
        assert config.event_queue_size == 100
        assert config.default_max_turns == 10
        assert config.max_turns_limit == 50

    def test_custom_values(self):
        """Should accept custom values."""
        config = SubagentConfig(
            global_max_concurrent=20,
            per_thread_max_concurrent=5,
            default_timeout=600,
        )
        assert config.global_max_concurrent == 20
        assert config.per_thread_max_concurrent == 5
        assert config.default_timeout == 600

    def test_llm_and_tools_optional(self):
        """LLM and tools should be optional."""
        config = SubagentConfig()
        assert config.llm is None
        assert config.default_tools == []

    def test_env_prefix(self):
        """Should support environment variables with SUBAGENT_ prefix."""
        import os
        os.environ["SUBAGENT_GLOBAL_MAX_CONCURRENT"] = "15"
        config = SubagentConfig()
        assert config.global_max_concurrent == 15
        del os.environ["SUBAGENT_GLOBAL_MAX_CONCURRENT"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Write SubagentConfig**

```python
# src/subagents/config.py
"""Configuration for subagent system."""

from typing import Any

from pydantic import BaseModel, Field


class SubagentConfig(BaseModel):
    """Configuration for the subagent system."""

    # Concurrency limits
    global_max_concurrent: int = Field(
        default=10,
        description="Maximum concurrent subagents globally",
    )
    per_thread_max_concurrent: int = Field(
        default=3,
        description="Maximum concurrent subagents per thread",
    )

    # Timeout settings
    default_timeout: int = Field(
        default=900,
        description="Default task timeout in seconds (15 min)",
    )
    max_timeout: int = Field(
        default=3600,
        description="Maximum allowed timeout in seconds (1 hour)",
    )

    # SSE settings
    sse_heartbeat_interval: int = Field(
        default=30,
        description="SSE heartbeat interval in seconds",
    )
    event_queue_size: int = Field(
        default=100,
        description="Maximum events queued per subscriber",
    )

    # LangGraph settings
    default_max_turns: int = Field(
        default=10,
        description="Default maximum turns per task",
    )
    max_turns_limit: int = Field(
        default=50,
        description="Maximum allowed turns per task",
    )

    # LLM and tools (set at runtime)
    llm: Any = None
    default_tools: list = Field(default_factory=list)

    class Config:
        env_prefix = "SUBAGENT_"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/subagents/config.py tests/subagents/test_config.py
git commit -m "feat(subagents): add SubagentConfig with Pydantic settings

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Concurrency Limiter

### Task 2.1: ConcurrencyLimiter

**Files:**
- Create: `backend/src/subagents/limiter.py`
- Create: `backend/tests/subagents/test_limiter.py`

- [ ] **Step 1: Write the failing tests for ConcurrencyLimiter**

```python
# tests/subagents/test_limiter.py
"""Tests for concurrency limiters."""

import asyncio
import pytest
from src.subagents.limiter import ConcurrencyLimiter, DualLayerLimiter


class TestConcurrencyLimiter:
    """Tests for ConcurrencyLimiter."""

    def test_create_limiter(self):
        """Should create limiter with max concurrent."""
        limiter = ConcurrencyLimiter(max_concurrent=3)
        assert limiter.max_concurrent == 3
        assert limiter.active_count == 0
        assert limiter.available_slots == 3

    @pytest.mark.asyncio
    async def test_acquire_slot(self):
        """Should acquire and release slots."""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        async with limiter.acquire():
            assert limiter.active_count == 1
            assert limiter.available_slots == 1

        assert limiter.active_count == 0
        assert limiter.available_slots == 2

    @pytest.mark.asyncio
    async def test_concurrent_acquisition(self):
        """Should limit concurrent acquisitions."""
        limiter = ConcurrencyLimiter(max_concurrent=2)
        acquired_count = 0
        max_concurrent = 0

        async def track_concurrency():
            nonlocal acquired_count, max_concurrent
            async with limiter.acquire():
                acquired_count += 1
                max_concurrent = max(max_concurrent, limiter.active_count)
                await asyncio.sleep(0.1)

        # Spawn 5 tasks but only 2 should run concurrently
        await asyncio.gather(*[track_concurrency() for _ in range(5)])

        assert acquired_count == 5
        assert max_concurrent == 2
        assert limiter.active_count == 0

    @pytest.mark.asyncio
    async def test_blocking_when_full(self):
        """Should block when all slots are taken."""
        limiter = ConcurrencyLimiter(max_concurrent=1)
        order = []

        async def task1():
            async with limiter.acquire():
                order.append("task1_start")
                await asyncio.sleep(0.2)
                order.append("task1_end")

        async def task2():
            await asyncio.sleep(0.05)  # Let task1 start first
            order.append("task2_waiting")
            async with limiter.acquire():
                order.append("task2_start")

        await asyncio.gather(task1(), task2())

        # task2 should block until task1 finishes
        assert order.index("task2_waiting") < order.index("task1_end")
        assert order.index("task2_start") > order.index("task1_end")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_limiter.py::TestConcurrencyLimiter -v`
Expected: FAIL

- [ ] **Step 3: Write ConcurrencyLimiter**

```python
# src/subagents/limiter.py
"""Concurrency control for subagent execution."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional


class ConcurrencyLimiter:
    """Limits concurrent operations using a semaphore."""

    def __init__(self, max_concurrent: int):
        """Initialize the limiter.

        Args:
            max_concurrent: Maximum number of concurrent operations.
        """
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        """Get maximum concurrent operations."""
        return self._max_concurrent

    @property
    def active_count(self) -> int:
        """Get current number of active operations."""
        return self._active_count

    @property
    def available_slots(self) -> int:
        """Get number of available slots."""
        return self._semaphore._value

    @asynccontextmanager
    async def acquire(self):
        """Acquire a slot. Blocks if all slots are taken."""
        await self._semaphore.acquire()
        async with self._lock:
            self._active_count += 1
        try:
            yield
        finally:
            async with self._lock:
                self._active_count -= 1
            self._semaphore.release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_limiter.py::TestConcurrencyLimiter -v`
Expected: PASS

---

### Task 2.2: DualLayerLimiter

**Files:**
- Modify: `backend/src/subagents/limiter.py`
- Modify: `backend/tests/subagents/test_limiter.py`

- [ ] **Step 1: Write the failing tests for DualLayerLimiter**

```python
# Add to tests/subagents/test_limiter.py

class TestDualLayerLimiter:
    """Tests for DualLayerLimiter."""

    def test_create_dual_limiter(self):
        """Should create with global and per-thread limits."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)
        assert limiter.global_max == 10
        assert limiter.per_thread_max == 3

    @pytest.mark.asyncio
    async def test_per_thread_limit(self):
        """Should limit concurrent operations per thread."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=2)
        thread_concurrent = {"thread-1": 0, "thread-1_max": 0}

        async def task(thread_id: str):
            async with limiter.acquire(thread_id):
                thread_concurrent[thread_id] += 1
                thread_concurrent[f"{thread_id}_max"] = max(
                    thread_concurrent[f"{thread_id}_max"],
                    thread_concurrent[thread_id]
                )
                await asyncio.sleep(0.1)
                thread_concurrent[thread_id] -= 1

        # Spawn 5 tasks for same thread, max 2 should run
        await asyncio.gather(*[task("thread-1") for _ in range(5)])

        assert thread_concurrent["thread-1_max"] == 2

    @pytest.mark.asyncio
    async def test_global_limit(self):
        """Should limit total concurrent operations globally."""
        limiter = DualLayerLimiter(global_max=3, per_thread_max=10)
        global_concurrent = 0
        global_max = 0
        lock = asyncio.Lock()

        async def task(thread_id: str):
            nonlocal global_concurrent, global_max
            async with limiter.acquire(thread_id):
                async with lock:
                    global_concurrent += 1
                    global_max = max(global_max, global_concurrent)
                await asyncio.sleep(0.1)
                async with lock:
                    global_concurrent -= 1

        # Spawn tasks across different threads
        await asyncio.gather(*[
            task(f"thread-{i % 5}") for i in range(10)
        ])

        assert global_max == 3

    @pytest.mark.asyncio
    async def test_cleanup_thread(self):
        """Should clean up thread limiter."""
        limiter = DualLayerLimiter(global_max=10, per_thread_max=3)

        # Create a thread limiter
        async with limiter.acquire("thread-1"):
            pass

        assert "thread-1" in limiter._thread_limiters

        # Clean up
        limiter.cleanup_thread("thread-1")
        assert "thread-1" not in limiter._thread_limiters

    @pytest.mark.asyncio
    async def test_both_limits_applied(self):
        """Should apply both global and per-thread limits."""
        limiter = DualLayerLimiter(global_max=4, per_thread_max=2)
        results = {"max_global": 0, "max_thread_1": 0, "max_thread_2": 0}
        global_count = 0
        thread_counts = {"thread-1": 0, "thread-2": 0}
        lock = asyncio.Lock()

        async def task(thread_id: str):
            nonlocal global_count
            async with limiter.acquire(thread_id):
                async with lock:
                    global_count += 1
                    thread_counts[thread_id] += 1
                    results["max_global"] = max(results["max_global"], global_count)
                    results[f"max_{thread_id.replace('-', '_')}"] = max(
                        results[f"max_{thread_id.replace('-', '_')}"],
                        thread_counts[thread_id]
                    )
                await asyncio.sleep(0.1)
                async with lock:
                    global_count -= 1
                    thread_counts[thread_id] -= 1

        # Spawn 4 tasks for thread-1, 4 for thread-2
        tasks = [task("thread-1") for _ in range(4)] + [task("thread-2") for _ in range(4)]
        await asyncio.gather(*tasks)

        # Global limit should be hit (4)
        assert results["max_global"] == 4
        # Per-thread limits should be hit (2 each)
        assert results["max_thread_1"] == 2
        assert results["max_thread_2"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_limiter.py::TestDualLayerLimiter -v`
Expected: FAIL

- [ ] **Step 3: Write DualLayerLimiter**

```python
# Add to src/subagents/limiter.py

class DualLayerLimiter:
    """Two-layer concurrency limiter: global + per-thread."""

    def __init__(self, global_max: int, per_thread_max: int):
        """Initialize dual-layer limiter.

        Args:
            global_max: Maximum concurrent operations globally.
            per_thread_max: Maximum concurrent operations per thread.
        """
        self._global = ConcurrencyLimiter(global_max)
        self._per_thread_max = per_thread_max
        self._thread_limiters: dict[str, ConcurrencyLimiter] = {}
        self._lock = asyncio.Lock()

    @property
    def global_max(self) -> int:
        """Get global maximum."""
        return self._global.max_concurrent

    @property
    def per_thread_max(self) -> int:
        """Get per-thread maximum."""
        return self._per_thread_max

    @asynccontextmanager
    async def acquire(self, thread_id: str):
        """Acquire both global and thread-specific slots.

        Args:
            thread_id: Thread identifier for per-thread limiting.

        Yields when both slots are acquired.
        """
        # Acquire global slot first
        async with self._global.acquire():
            # Then acquire thread-specific slot
            limiter = await self._get_or_create_thread_limiter(thread_id)
            async with limiter.acquire():
                yield

    async def _get_or_create_thread_limiter(self, thread_id: str) -> ConcurrencyLimiter:
        """Get existing or create new thread limiter."""
        async with self._lock:
            if thread_id not in self._thread_limiters:
                self._thread_limiters[thread_id] = ConcurrencyLimiter(
                    self._per_thread_max
                )
            return self._thread_limiters[thread_id]

    def cleanup_thread(self, thread_id: str) -> None:
        """Remove thread limiter when thread is cleaned up.

        Args:
            thread_id: Thread identifier to clean up.
        """
        if thread_id in self._thread_limiters:
            del self._thread_limiters[thread_id]

    @property
    def active_global_count(self) -> int:
        """Get current global active count."""
        return self._global.active_count

    def get_thread_active_count(self, thread_id: str) -> int:
        """Get active count for a specific thread."""
        if thread_id in self._thread_limiters:
            return self._thread_limiters[thread_id].active_count
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_limiter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/subagents/limiter.py tests/subagents/test_limiter.py
git commit -m "feat(subagents): add ConcurrencyLimiter and DualLayerLimiter

- ConcurrencyLimiter: single semaphore-based limiter
- DualLayerLimiter: global + per-thread concurrency control

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: SSE Event Stream

### Task 3.1: SubagentEventStream

**Files:**
- Create: `backend/src/subagents/events.py`
- Create: `backend/tests/subagents/test_events.py`

- [ ] **Step 1: Write the failing tests for SubagentEventStream**

```python
# tests/subagents/test_events.py
"""Tests for SSE event stream."""

import asyncio
import pytest
from src.subagents.events import SubagentEventStream
from src.subagents.models import SubagentEvent


class TestSubagentEventStream:
    """Tests for SubagentEventStream."""

    def test_create_stream(self):
        """Should create stream with default settings."""
        stream = SubagentEventStream()
        assert stream.max_queue_size == 100

    def test_create_stream_custom_queue_size(self):
        """Should accept custom queue size."""
        stream = SubagentEventStream(max_queue_size=50)
        assert stream.max_queue_size == 50

    @pytest.mark.asyncio
    async def test_publish_to_subscriber(self):
        """Should publish events to subscribers."""
        stream = SubagentEventStream()
        event = SubagentEvent(
            event_type="test",
            task_id="task-1",
            thread_id="thread-1",
            data={"key": "value"},
        )
        received = []

        async def subscriber():
            async for sse_str in stream.subscribe(thread_id="thread-1"):
                received.append(sse_str)
                break  # Exit after first event

        async def publisher():
            await asyncio.sleep(0.01)  # Let subscriber start
            await stream.publish(event)
            await asyncio.sleep(0.01)  # Let subscriber receive

        await asyncio.gather(subscriber(), publisher())

        assert len(received) == 1
        assert "event: test" in received[0]

    @pytest.mark.asyncio
    async def test_thread_filtering(self):
        """Should filter events by thread_id."""
        stream = SubagentEventStream()
        event1 = SubagentEvent(
            event_type="test",
            task_id="task-1",
            thread_id="thread-1",
            data={},
        )
        event2 = SubagentEvent(
            event_type="test",
            task_id="task-2",
            thread_id="thread-2",
            data={},
        )
        received = []

        async def subscriber():
            async for sse_str in stream.subscribe(thread_id="thread-1"):
                received.append(sse_str)
                if len(received) >= 1:
                    break

        async def publisher():
            await asyncio.sleep(0.01)
            await stream.publish(event2)  # Different thread
            await stream.publish(event1)  # Matching thread
            await asyncio.sleep(0.01)

        await asyncio.gather(subscriber(), publisher())

        # Should only receive event1 (thread-1)
        assert len(received) == 1
        assert "task-1" in received[0]

    @pytest.mark.asyncio
    async def test_global_subscriber(self):
        """Global subscriber should receive all events."""
        stream = SubagentEventStream()
        events = [
            SubagentEvent(event_type="test", task_id=f"task-{i}", thread_id=f"thread-{i}", data={})
            for i in range(3)
        ]
        received = []

        async def subscriber():
            count = 0
            async for sse_str in stream.subscribe(thread_id=None):  # Global
                received.append(sse_str)
                count += 1
                if count >= 3:
                    break

        async def publisher():
            await asyncio.sleep(0.01)
            for event in events:
                await stream.publish(event)
            await asyncio.sleep(0.01)

        await asyncio.gather(subscriber(), publisher())

        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_close_stream(self):
        """Should close all subscriptions."""
        stream = SubagentEventStream()
        closed = []

        async def subscriber():
            async for _ in stream.subscribe():
                pass
            closed.append(True)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)
        await stream.close()
        await task

        assert len(closed) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_events.py -v`
Expected: FAIL

- [ ] **Step 3: Write SubagentEventStream**

```python
# src/subagents/events.py
"""SSE event stream for subagent status updates."""

import asyncio
from typing import AsyncIterator, Optional

from .models import SubagentEvent


class SubagentEventStream:
    """Manages SSE subscriptions with thread filtering."""

    def __init__(self, max_queue_size: int = 100):
        """Initialize the event stream.

        Args:
            max_queue_size: Maximum events to queue per subscriber.
        """
        self._max_queue_size = max_queue_size
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    @property
    def max_queue_size(self) -> int:
        """Get maximum queue size."""
        return self._max_queue_size

    async def subscribe(
        self, thread_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Subscribe to event stream.

        Args:
            thread_id: If specified, only receive events for this thread.
                       None means receive all events (global subscriber).

        Yields:
            SSE-formatted event strings.
        """
        queue: asyncio.Queue[Optional[SubagentEvent]] = asyncio.Queue(
            maxsize=self._max_queue_size
        )
        key = f"thread:{thread_id}" if thread_id else "global"

        async with self._lock:
            self._subscribers[key] = queue

        try:
            while True:
                event = await queue.get()
                if event is None:  # Shutdown signal
                    break
                yield event.to_sse()
        finally:
            async with self._lock:
                if key in self._subscribers:
                    del self._subscribers[key]

    async def publish(self, event: SubagentEvent) -> None:
        """Publish event to relevant subscribers.

        Events are sent to:
        - Thread-specific subscriber (if exists)
        - Global subscriber (if exists)

        Args:
            event: Event to publish.
        """
        thread_key = f"thread:{event.thread_id}"
        global_key = "global"

        async with self._lock:
            for key in [thread_key, global_key]:
                if key in self._subscribers:
                    try:
                        self._subscribers[key].put_nowait(event)
                    except asyncio.QueueFull:
                        # Drop event if queue is full (backpressure handling)
                        pass

    async def close(self) -> None:
        """Close all subscriptions."""
        async with self._lock:
            for queue in self._subscribers.values():
                await queue.put(None)
            self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        """Get current number of subscribers."""
        return len(self._subscribers)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_events.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/subagents/events.py tests/subagents/test_events.py
git commit -m "feat(subagents): add SubagentEventStream for SSE

- Thread-based event filtering
- Global subscriber support
- Backpressure handling with queue limits

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: LangGraph Integration

### Task 4.1: GraphTemplateRegistry

**Files:**
- Create: `backend/src/subagents/graph.py`
- Create: `backend/tests/subagents/test_graph.py`

- [ ] **Step 1: Write the failing tests for GraphTemplateRegistry**

```python
# tests/subagents/test_graph.py
"""Tests for LangGraph integration."""

import pytest
from unittest.mock import MagicMock
from src.subagents.graph import GraphTemplateRegistry


class TestGraphTemplateRegistry:
    """Tests for GraphTemplateRegistry."""

    def test_create_registry(self):
        """Should create empty registry."""
        registry = GraphTemplateRegistry()
        assert registry.count == 0

    def test_register_graph(self):
        """Should register a graph template."""
        registry = GraphTemplateRegistry()
        mock_graph = MagicMock()
        registry.register("default", mock_graph)
        assert registry.count == 1
        assert registry.has("default")

    def test_get_graph(self):
        """Should retrieve registered graph."""
        registry = GraphTemplateRegistry()
        mock_graph = MagicMock()
        registry.register("custom", mock_graph)
        retrieved = registry.get("custom")
        assert retrieved is mock_graph

    def test_get_nonexistent_graph(self):
        """Should return None for unregistered template."""
        registry = GraphTemplateRegistry()
        assert registry.get("nonexistent") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/subagents/test_graph.py::TestGraphTemplateRegistry -v`
Expected: FAIL

- [ ] **Step 3: Write GraphTemplateRegistry**

```python
# src/subagents/graph.py
"""LangGraph integration for subagent execution."""

from typing import Any, Optional


class GraphTemplateRegistry:
    """Registry for compiled LangGraph templates."""

    def __init__(self):
        self._templates: dict[str, Any] = {}

    @property
    def count(self) -> int:
        return len(self._templates)

    def register(self, name: str, graph: Any) -> None:
        self._templates[name] = graph

    def get(self, name: str) -> Optional[Any]:
        return self._templates.get(name)

    def has(self, name: str) -> bool:
        return name in self._templates


def create_default_subagent_graph(llm: Any, tools: list, max_turns: int = 10) -> Any:
    """Create a default ReAct-style subagent graph."""
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        raise ImportError("langgraph is required. Install with: pip install langgraph")

    return create_react_agent(llm, tools=tools)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/subagents/graph.py tests/subagents/test_graph.py
git commit -m "feat(subagents): add GraphTemplateRegistry and create_default_subagent_graph

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 5: SubagentExecutor

### Task 5.1: SubagentExecutor

**Files:**
- Create: `backend/src/subagents/executor.py`
- Create: `backend/tests/subagents/test_executor.py`
- Create: `backend/tests/subagents/conftest.py`

- [ ] **Step 1: Create test fixtures in conftest.py**

```python
# tests/subagents/conftest.py
"""Test fixtures for subagent tests."""

import pytest
from unittest.mock import MagicMock

from src.subagents.config import SubagentConfig
from src.subagents.events import SubagentEventStream
from src.subagents.graph import GraphTemplateRegistry


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_tools():
    return [MagicMock(), MagicMock()]


@pytest.fixture
def event_stream():
    return SubagentEventStream()


@pytest.fixture
def graph_registry():
    return GraphTemplateRegistry()


@pytest.fixture
def subagent_config(mock_llm, mock_tools):
    return SubagentConfig(llm=mock_llm, default_tools=mock_tools)
```

- [ ] **Step 2: Write the failing tests for SubagentExecutor**

```python
# tests/subagents/test_executor.py
"""Tests for SubagentExecutor."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.subagents.executor import SubagentExecutor
from src.subagents.models import SubagentTask, SubagentStatus


class TestSubagentExecutor:
    @pytest.fixture
    def executor(self, mock_llm, mock_tools, event_stream, graph_registry):
        return SubagentExecutor(
            llm=mock_llm,
            tools=mock_tools,
            event_stream=event_stream,
            graph_registry=graph_registry,
        )

    @pytest.fixture
    def sample_task(self):
        return SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test prompt",
            timeout=60,
        )

    @pytest.mark.asyncio
    async def test_execute_success(self, executor, sample_task):
        """Should execute task and return success result."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done")]
        })
        executor._graph_registry.register("default", mock_graph)

        result = await executor.execute(sample_task)

        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "Done"

    @pytest.mark.asyncio
    async def test_execute_timeout(self, executor):
        """Should handle timeout correctly."""
        task = SubagentTask(
            task_id="timeout-task",
            thread_id="thread-789",
            prompt="Will timeout",
            timeout=1,
        )

        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)
            return {"messages": []}

        mock_graph = AsyncMock()
        mock_graph.ainvoke = slow_invoke
        executor._graph_registry.register("default", mock_graph)

        result = await executor.execute(task)

        assert result.status == SubagentStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_execute_failure(self, executor):
        """Should handle execution failure."""
        task = SubagentTask(
            task_id="fail-task",
            thread_id="thread-fail",
            prompt="Will fail",
            timeout=60,
        )

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=ValueError("Error"))
        executor._graph_registry.register("default", mock_graph)

        result = await executor.execute(task)

        assert result.status == SubagentStatus.FAILED
        assert "Error" in result.error
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_executor.py -v`
Expected: FAIL

- [ ] **Step 4: Write SubagentExecutor**

```python
# src/subagents/executor.py
"""Subagent task executor."""

import asyncio
from datetime import datetime
from typing import Any

from .events import SubagentEventStream
from .graph import GraphTemplateRegistry, create_default_subagent_graph
from .models import SubagentEvent, SubagentResult, SubagentStatus, SubagentTask


class SubagentExecutor:
    """Executes individual subagent tasks."""

    def __init__(
        self,
        llm: Any,
        tools: list,
        event_stream: SubagentEventStream,
        graph_registry: GraphTemplateRegistry,
    ):
        self._llm = llm
        self._tools = tools
        self._event_stream = event_stream
        self._graph_registry = graph_registry

    async def execute(self, task: SubagentTask) -> SubagentResult:
        start_time = datetime.now()

        try:
            await self._publish_event(task, "task_started", {"prompt": task.prompt})

            graph = self._get_graph(task.graph_template)

            from langchain_core.messages import HumanMessage
            result = await asyncio.wait_for(
                graph.ainvoke({"messages": [HumanMessage(content=task.prompt)]}),
                timeout=task.timeout,
            )

            messages = result.get("messages", [])
            output = messages[-1].content if messages else ""

            await self._publish_event(task, "task_completed", {"output": output})

            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.COMPLETED,
                output=output,
                turns_used=len(messages) // 2,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except asyncio.TimeoutError:
            await self._publish_event(task, "task_failed", {"error": "Timeout"})
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.TIMEOUT,
                error=f"Timed out after {task.timeout}s",
                duration_seconds=task.timeout,
            )

        except asyncio.CancelledError:
            await self._publish_event(task, "task_cancelled", {})
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.CANCELLED,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            await self._publish_event(task, "task_failed", {"error": str(e)})
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.FAILED,
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _get_graph(self, template_name: str) -> Any:
        graph = self._graph_registry.get(template_name)
        if graph is None:
            graph = create_default_subagent_graph(self._llm, self._tools)
            self._graph_registry.register(template_name, graph)
        return graph

    async def _publish_event(self, task: SubagentTask, event_type: str, data: dict):
        await self._event_stream.publish(SubagentEvent(
            event_type=event_type,
            task_id=task.task_id,
            thread_id=task.thread_id,
            data=data,
        ))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_executor.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/subagents/executor.py tests/subagents/test_executor.py tests/subagents/conftest.py
git commit -m "feat(subagents): add SubagentExecutor with timeout and cancellation support

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 6: GlobalSubagentManager

### Task 6.1: ThreadContext and GlobalSubagentManager

**Files:**
- Create: `backend/src/subagents/manager.py`
- Create: `backend/tests/subagents/test_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/subagents/test_manager.py
"""Tests for GlobalSubagentManager and ThreadContext."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.subagents.manager import ThreadContext, GlobalSubagentManager
from src.subagents.models import SubagentTask, SubagentResult, SubagentStatus


class TestThreadContext:
    def test_create_context(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        assert ctx.thread_id == "thread-1"
        assert ctx.total_tasks == 0

    def test_store_and_get_result(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        result = SubagentResult(task_id="task-1", status=SubagentStatus.COMPLETED)
        ctx.store_result("task-1", result)
        assert ctx.get_result("task-1") is result


class TestGlobalSubagentManager:
    @pytest.fixture
    def manager(self, subagent_config):
        GlobalSubagentManager.reset()
        manager = GlobalSubagentManager(subagent_config)
        GlobalSubagentManager._instance = manager
        yield manager
        GlobalSubagentManager.reset()

    def test_singleton(self, subagent_config):
        GlobalSubagentManager.reset()
        m1 = GlobalSubagentManager.initialize(subagent_config)
        m2 = GlobalSubagentManager.get_instance()
        assert m1 is m2
        GlobalSubagentManager.reset()

    @pytest.mark.asyncio
    async def test_spawn_task(self, manager):
        task = SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test",
            timeout=60,
        )
        manager._executor.execute = AsyncMock(return_value=SubagentResult(
            task_id="task-123", status=SubagentStatus.COMPLETED, output="Done"
        ))

        task_id = await manager.spawn(task)
        assert task_id == "task-123"

        await asyncio.sleep(0.1)
        status = await manager.get_status("thread-456", "task-123")
        assert status == SubagentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel_task(self, manager):
        task = SubagentTask(
            task_id="cancel-test",
            thread_id="thread-cancel",
            prompt="Test",
            timeout=60,
        )

        async def slow_execute(t):
            await asyncio.sleep(10)
            return SubagentResult(task_id=t.task_id, status=SubagentStatus.COMPLETED)

        manager._executor.execute = slow_execute
        await manager.spawn(task)
        await asyncio.sleep(0.05)

        success = await manager.cancel("thread-cancel", "cancel-test")
        assert success is True

    @pytest.mark.asyncio
    async def test_cleanup_thread(self, manager):
        task = SubagentTask(
            task_id="cleanup-test",
            thread_id="thread-cleanup",
            prompt="Test",
            timeout=60,
        )
        manager._executor.execute = AsyncMock(return_value=SubagentResult(
            task_id="cleanup-test", status=SubagentStatus.COMPLETED
        ))

        await manager.spawn(task)
        await asyncio.sleep(0.1)

        assert "thread-cleanup" in manager._threads
        await manager.cleanup_thread("thread-cleanup")
        assert "thread-cleanup" not in manager._threads
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Write ThreadContext and GlobalSubagentManager**

```python
# src/subagents/manager.py
"""Global subagent manager and thread context."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .config import SubagentConfig
from .events import SubagentEventStream
from .executor import SubagentExecutor
from .graph import GraphTemplateRegistry
from .limiter import ConcurrencyLimiter, DualLayerLimiter
from .models import SubagentResult, SubagentStatus, SubagentTask


@dataclass
class ThreadContext:
    """Context for a single conversation thread."""
    thread_id: str
    max_concurrent: int
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _results: dict[str, SubagentResult] = field(default_factory=dict)

    @property
    def total_tasks(self) -> int:
        return len(self._tasks)

    def store_result(self, task_id: str, result: SubagentResult) -> None:
        self._results[task_id] = result

    def get_result(self, task_id: str) -> Optional[SubagentResult]:
        return self._results.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[SubagentStatus]:
        if task_id in self._results:
            return self._results[task_id].status
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if task.done():
                if task.cancelled():
                    return SubagentStatus.CANCELLED
                if task.exception():
                    return SubagentStatus.FAILED
                return SubagentStatus.COMPLETED
            return SubagentStatus.RUNNING
        return None


class GlobalSubagentManager:
    """Singleton manager for all subagent operations."""
    _instance: Optional["GlobalSubagentManager"] = None

    def __init__(self, config: SubagentConfig):
        self._config = config
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._event_stream = SubagentEventStream(max_queue_size=config.event_queue_size)
        self._graph_registry = GraphTemplateRegistry()
        self._threads: dict[str, ThreadContext] = {}
        self._executor = SubagentExecutor(
            llm=config.llm,
            tools=config.default_tools,
            event_stream=self._event_stream,
            graph_registry=self._graph_registry,
        )
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "GlobalSubagentManager":
        if cls._instance is None:
            raise RuntimeError("GlobalSubagentManager not initialized")
        return cls._instance

    @classmethod
    def initialize(cls, config: SubagentConfig) -> "GlobalSubagentManager":
        if cls._instance is not None:
            raise RuntimeError("GlobalSubagentManager already initialized")
        cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    async def spawn(self, task: SubagentTask) -> str:
        async with self._lock:
            ctx = self._get_or_create_context(task.thread_id)

        async def run_with_limiter():
            async with self._limiter.acquire(task.thread_id):
                result = await self._executor.execute(task)
                ctx.store_result(task.task_id, result)
                return result

        async_task = asyncio.create_task(run_with_limiter())
        ctx._tasks[task.task_id] = async_task
        return task.task_id

    async def cancel(self, thread_id: str, task_id: str) -> bool:
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx or task_id not in ctx._tasks:
                return False
            async_task = ctx._tasks[task_id]
            if not async_task.done():
                async_task.cancel()
                return True
            return False

    async def get_status(self, thread_id: str, task_id: str) -> Optional[SubagentStatus]:
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return None
            return ctx.get_task_status(task_id)

    async def get_result(self, thread_id: str, task_id: str) -> Optional[SubagentResult]:
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return None
            return ctx.get_result(task_id)

    async def subscribe_events(self, thread_id: Optional[str] = None):
        async for event_str in self._event_stream.subscribe(thread_id):
            yield event_str

    async def cleanup_thread(self, thread_id: str) -> None:
        async with self._lock:
            if thread_id not in self._threads:
                return
            ctx = self._threads[thread_id]
            for task in ctx._tasks.values():
                if not task.done():
                    task.cancel()
            del self._threads[thread_id]
            self._limiter.cleanup_thread(thread_id)

    def _get_or_create_context(self, thread_id: str) -> ThreadContext:
        if thread_id not in self._threads:
            self._threads[thread_id] = ThreadContext(
                thread_id=thread_id,
                max_concurrent=self._config.per_thread_max_concurrent,
            )
        return self._threads[thread_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/subagents/manager.py tests/subagents/test_manager.py
git commit -m "feat(subagents): add ThreadContext and GlobalSubagentManager

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 7: API Routes

### Task 7.1: FastAPI Routes

**Files:**
- Create: `backend/src/api/subagents.py`
- Create: `backend/tests/subagents/test_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/subagents/test_api.py
"""Tests for subagent API routes."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.subagents import router, get_manager
from src.subagents.models import SubagentStatus, SubagentResult


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager._config = MagicMock()
    manager._config.max_turns_limit = 50
    manager._config.max_timeout = 3600
    manager.spawn = AsyncMock(return_value="task-123")
    manager.get_status = AsyncMock(return_value=SubagentStatus.COMPLETED)
    manager.get_result = AsyncMock(return_value=SubagentResult(
        task_id="task-123", status=SubagentStatus.COMPLETED, output="Done"
    ))
    manager.cancel = AsyncMock(return_value=True)
    return manager


class TestSpawnEndpoint:
    def test_spawn_success(self, client, mock_manager):
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-123"
        app.dependency_overrides = {}


class TestStatusEndpoint:
    def test_get_status_success(self, client, mock_manager):
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/threads/thread-123/tasks/task-123/status")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        app.dependency_overrides = {}

    def test_get_status_not_found(self, client, mock_manager):
        mock_manager.get_status = AsyncMock(return_value=None)
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/threads/thread-123/tasks/unknown/status")
        assert response.status_code == 404
        app.dependency_overrides = {}


class TestCancelEndpoint:
    def test_cancel_success(self, client, mock_manager):
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.post("/subagents/threads/thread-123/tasks/task-123/cancel")
        assert response.status_code == 200
        assert response.json()["success"] is True
        app.dependency_overrides = {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: Write API routes**

```python
# src/api/subagents.py
"""FastAPI routes for subagent operations."""

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.subagents import (
    GlobalSubagentManager,
    SubagentTask,
    SubagentStatus,
    SubagentResult,
)


router = APIRouter(prefix="/subagents", tags=["subagents"])


class SpawnRequest(BaseModel):
    prompt: str
    max_turns: int = 10
    timeout: int = 900
    graph_template: str = "default"


class SpawnResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    thread_id: str
    status: SubagentStatus
    result: Optional[SubagentResult] = None


class CancelResponse(BaseModel):
    success: bool


def get_manager() -> GlobalSubagentManager:
    return GlobalSubagentManager.get_instance()


@router.post("/threads/{thread_id}/spawn", response_model=SpawnResponse)
async def spawn_subagent(
    thread_id: str,
    request: SpawnRequest,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> SpawnResponse:
    task = SubagentTask(
        task_id=str(uuid4()),
        thread_id=thread_id,
        prompt=request.prompt,
        max_turns=min(request.max_turns, manager._config.max_turns_limit),
        timeout=min(request.timeout, manager._config.max_timeout),
        graph_template=request.graph_template,
    )
    await manager.spawn(task)
    return SpawnResponse(task_id=task.task_id, status="pending")


@router.get(
    "/threads/{thread_id}/tasks/{task_id}/status",
    response_model=TaskStatusResponse,
)
async def get_task_status(
    thread_id: str,
    task_id: str,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> TaskStatusResponse:
    status = await manager.get_status(thread_id, task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await manager.get_result(thread_id, task_id)
    return TaskStatusResponse(
        task_id=task_id,
        thread_id=thread_id,
        status=status,
        result=result,
    )


@router.post(
    "/threads/{thread_id}/tasks/{task_id}/cancel",
    response_model=CancelResponse,
)
async def cancel_task(
    thread_id: str,
    task_id: str,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> CancelResponse:
    success = await manager.cancel(thread_id, task_id)
    return CancelResponse(success=success)


@router.get("/events")
async def subscribe_events(
    thread_id: Optional[str] = None,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> StreamingResponse:
    return StreamingResponse(
        manager.subscribe_events(thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/subagents.py tests/subagents/test_api.py
git commit -m "feat(subagents): add FastAPI routes for spawn/status/cancel/events

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 8: Final Verification

### Task 8.1: Run All Tests

- [ ] **Step 1: Run all subagent tests**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/subagents/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run full test suite**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && python -m pytest tests/ -v`
Expected: All tests PASS (including sandbox)

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(subagents): complete Phase 2 subagent system

Core framework includes:
- Dual-layer concurrency control (global + per-thread)
- SSE event streaming
- LangGraph integration
- FastAPI routes (spawn/status/cancel/events)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary

**Files Created:**
- `src/subagents/__init__.py`
- `src/subagents/models.py`
- `src/subagents/config.py`
- `src/subagents/limiter.py`
- `src/subagents/events.py`
- `src/subagents/graph.py`
- `src/subagents/executor.py`
- `src/subagents/manager.py`
- `src/api/subagents.py`
- `tests/subagents/__init__.py`
- `tests/subagents/conftest.py`
- `tests/subagents/test_models.py`
- `tests/subagents/test_config.py`
- `tests/subagents/test_limiter.py`
- `tests/subagents/test_events.py`
- `tests/subagents/test_graph.py`
- `tests/subagents/test_executor.py`
- `tests/subagents/test_manager.py`
- `tests/subagents/test_api.py`

**Total Tasks: 8**
**Estimated Test Count: ~50**

**Dependencies to add:**
```
langgraph>=0.2.0
langchain-core>=0.3.0
```

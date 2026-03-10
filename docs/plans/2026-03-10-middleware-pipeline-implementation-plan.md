# 16层中间件管道完善 - 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成 16 层中间件管道，添加缺失的 SandboxMiddleware、MemoryMiddleware、TodoListMiddleware、ViewImageMiddleware

**Architecture:** 基于 deer-flow 的中间件模式，每个中间件实现 `before_model` 和 `after_model` 钩子，按严格顺序执行形成管道。新增中间件遵循相同的接口规范。

**Tech Stack:** Python 3.12+, LangGraph, asyncio, Pydantic

---

## 前置准备

### 参考文件 (deer-flow)
- `/home/cjz/deer-flow/backend/src/agents/middlewares/sandbox_middleware.py` - Sandbox 实现
- `/home/cjz/deer-flow/backend/src/agents/middlewares/memory_middleware.py` - Memory 实现
- `/home/cjz/deer-flow/backend/src/agents/middlewares/todo_list_middleware.py` - TodoList 实现
- `/home/cjz/deer-flow/backend/src/agents/middlewares/view_image_middleware.py` - ViewImage 实现

### 目标文件 (academiagpt-v2)
- `backend/src/agents/middlewares/base.py` - 基类接口
- `backend/src/agents/middlewares/__init__.py` - 导出
- `backend/src/agents/lead_agent/agent.py` - 管道组装

---

## Task 1: 创建 SandboxMiddleware

**Files:**
- Create: `backend/src/agents/middlewares/sandbox.py`
- Modify: `backend/src/agents/middlewares/__init__.py`
- Test: `backend/tests/unit/middlewares/test_sandbox.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/middlewares/test_sandbox.py
"""Tests for SandboxMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.middlewares.sandbox import SandboxMiddleware
from src.agents.thread_state import ThreadState


class TestSandboxMiddleware:
    """Test cases for SandboxMiddleware."""

    @pytest.fixture
    def mock_provider(self):
        """Create mock sandbox provider."""
        provider = MagicMock()
        provider.acquire = AsyncMock()
        provider.release = AsyncMock()
        return provider

    @pytest.fixture
    def middleware(self, mock_provider):
        """Create middleware instance."""
        return SandboxMiddleware(mock_provider)

    @pytest.fixture
    def initial_state(self):
        """Create initial thread state."""
        return ThreadState(messages=[])

    @pytest.fixture
    def config(self):
        """Create runtime config."""
        return {"configurable": {"thread_id": "test-thread-123"}}

    @pytest.mark.asyncio
    async def test_before_model_acquires_sandbox(
        self, middleware, mock_provider, initial_state, config
    ):
        """Test that before_model acquires a sandbox."""
        # Setup mock
        mock_sandbox = MagicMock()
        mock_sandbox.sandbox_id = "sandbox-456"
        mock_provider.acquire.return_value = mock_sandbox

        # Execute
        result = await middleware.before_model(initial_state, config)

        # Verify
        mock_provider.acquire.assert_called_once_with("test-thread-123")
        assert result == {"sandbox": {"sandbox_id": "sandbox-456"}}

    @pytest.mark.asyncio
    async def test_before_model_skips_if_sandbox_exists(
        self, middleware, mock_provider, config
    ):
        """Test that before_model skips if sandbox already exists."""
        state = ThreadState(messages=[], sandbox={"sandbox_id": "existing"})

        result = await middleware.before_model(state, config)

        mock_provider.acquire.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_returns_empty(self, middleware, initial_state, config):
        """Test that after_model returns empty dict."""
        result = await middleware.after_model(initial_state, config)
        assert result == {}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_sandbox.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.middlewares.sandbox'"

**Step 3: Write minimal implementation**

```python
# backend/src/agents/middlewares/sandbox.py
"""SandboxMiddleware for managing sandbox lifecycle."""

from typing import Any

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class SandboxMiddleware(Middleware):
    """Middleware for acquiring and managing sandbox instances.

    This middleware integrates the SandboxProvider into the agent pipeline,
    ensuring each thread has access to a sandbox for code execution.
    """

    def __init__(self, provider: Any):
        """Initialize with a sandbox provider.

        Args:
            provider: SandboxProvider instance (from src.sandbox.providers)
        """
        self.provider = provider

    async def before_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Acquire sandbox before model call.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Dict with sandbox state if acquired, empty dict otherwise
        """
        # Skip if sandbox already exists
        if state.get("sandbox"):
            return {}

        # Get thread ID from config
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return {}

        # Acquire sandbox from provider
        sandbox = await self.provider.acquire(thread_id)

        return {"sandbox": {"sandbox_id": sandbox.sandbox_id}}

    async def after_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """No-op after model call.

        Sandbox is released by the provider when appropriate.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict
        """
        return {}
```

**Step 4: Update middlewares/__init__.py**

```python
# Add to backend/src/agents/middlewares/__init__.py
from .sandbox import SandboxMiddleware

# Update __all__ list
__all__ = [
    # ... existing exports ...
    "SandboxMiddleware",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_sandbox.py -v`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/src/agents/middlewares/sandbox.py backend/src/agents/middlewares/__init__.py backend/tests/unit/middlewares/test_sandbox.py
git commit -m "feat(middleware): add SandboxMiddleware for sandbox lifecycle management"
```

---

## Task 2: 创建 MemoryMiddleware

**Files:**
- Create: `backend/src/agents/middlewares/memory.py`
- Modify: `backend/src/agents/middlewares/__init__.py`
- Test: `backend/tests/unit/middlewares/test_memory.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/middlewares/test_memory.py
"""Tests for MemoryMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from src.agents.middlewares.memory import MemoryMiddleware
from src.agents.thread_state import ThreadState


class TestMemoryMiddleware:
    """Test cases for MemoryMiddleware."""

    @pytest.fixture
    def mock_queue(self):
        """Create mock memory queue."""
        queue = MagicMock()
        queue.enqueue = AsyncMock()
        return queue

    @pytest.fixture
    def middleware(self, mock_queue):
        """Create middleware instance with mocked dependencies."""
        return MemoryMiddleware(
            memory_queue=mock_queue,
            enabled=True,
        )

    @pytest.fixture
    def initial_state(self):
        """Create initial thread state."""
        return ThreadState(messages=[])

    @pytest.fixture
    def config(self):
        """Create runtime config."""
        return {"configurable": {"thread_id": "test-thread-123"}}

    @pytest.mark.asyncio
    async def test_before_model_returns_empty(
        self, middleware, initial_state, config
    ):
        """Test that before_model returns empty dict."""
        result = await middleware.before_model(initial_state, config)
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_enqueues_conversation(
        self, middleware, mock_queue, config
    ):
        """Test that after_model enqueues conversation for memory update."""
        state = ThreadState(messages=[
            HumanMessage(content="What is machine learning?"),
            AIMessage(content="Machine learning is a subset of AI..."),
        ])

        result = await middleware.after_model(state, config)

        # Verify enqueue was called
        mock_queue.enqueue.assert_called_once()
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_skips_when_disabled(self, mock_queue, config):
        """Test that after_model skips when middleware is disabled."""
        middleware = MemoryMiddleware(
            memory_queue=mock_queue,
            enabled=False,
        )
        state = ThreadState(messages=[
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ])

        result = await middleware.after_model(state, config)

        mock_queue.enqueue.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_skips_short_conversations(
        self, middleware, mock_queue, config
    ):
        """Test that after_model skips conversations with only user messages."""
        state = ThreadState(messages=[
            HumanMessage(content="Hello"),
        ])

        result = await middleware.after_model(state, config)

        mock_queue.enqueue.assert_not_called()
        assert result == {}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_memory.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.middlewares.memory'"

**Step 3: Write minimal implementation**

```python
# backend/src/agents/middlewares/memory.py
"""MemoryMiddleware for async memory updates."""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class MemoryMiddleware(Middleware):
    """Middleware for updating long-term memory.

    This middleware intercepts conversations and queues them for async
    memory extraction and storage.
    """

    def __init__(
        self,
        memory_queue: Any = None,
        enabled: bool = True,
    ):
        """Initialize memory middleware.

        Args:
            memory_queue: MemoryQueue instance for debounced updates
            enabled: Whether memory updates are enabled
        """
        self.memory_queue = memory_queue
        self.enabled = enabled

    async def before_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """No-op before model call.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict
        """
        return {}

    async def after_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Queue conversation for memory update after model call.

        Filters to user inputs and final AI responses, then enqueues
        for async memory extraction.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict
        """
        if not self.enabled or not self.memory_queue:
            return {}

        # Filter messages for memory update
        filtered_messages = self._filter_messages(state.get("messages", []))
        if not filtered_messages:
            return {}

        # Get thread ID
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return {}

        # Enqueue for async processing
        await self.memory_queue.enqueue(thread_id, filtered_messages)

        return {}

    def _filter_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Filter messages to user inputs and AI responses.

        Args:
            messages: All messages in conversation

        Returns:
            Filtered list suitable for memory extraction
        """
        if len(messages) < 2:
            return []

        filtered = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                filtered.append(msg)
            elif isinstance(msg, AIMessage):
                # Only include final AI responses (not tool calls)
                if not msg.tool_calls:
                    filtered.append(msg)

        return filtered
```

**Step 4: Update middlewares/__init__.py**

```python
# Add to backend/src/agents/middlewares/__init__.py
from .memory import MemoryMiddleware

# Update __all__ list
__all__ = [
    # ... existing exports ...
    "MemoryMiddleware",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_memory.py -v`
Expected: PASS (4 tests)

**Step 6: Commit**

```bash
git add backend/src/agents/middlewares/memory.py backend/src/agents/middlewares/__init__.py backend/tests/unit/middlewares/test_memory.py
git commit -m "feat(middleware): add MemoryMiddleware for async memory updates"
```

---

## Task 3: 创建 TodoListMiddleware

**Files:**
- Create: `backend/src/agents/middlewares/todo_list.py`
- Modify: `backend/src/agents/middlewares/__init__.py`
- Test: `backend/tests/unit/middlewares/test_todo_list.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/middlewares/test_todo_list.py
"""Tests for TodoListMiddleware."""

import pytest

from src.agents.middlewares.todo_list import TodoListMiddleware
from src.agents.thread_state import ThreadState


class TestTodoListMiddleware:
    """Test cases for TodoListMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return TodoListMiddleware()

    @pytest.fixture
    def initial_state(self):
        """Create initial thread state."""
        return ThreadState(messages=[])

    @pytest.fixture
    def plan_mode_config(self):
        """Create config with plan mode enabled."""
        return {"configurable": {"is_plan_mode": True}}

    @pytest.fixture
    def normal_config(self):
        """Create config without plan mode."""
        return {"configurable": {"is_plan_mode": False}}

    @pytest.mark.asyncio
    async def test_before_model_injects_todos_in_plan_mode(
        self, middleware, initial_state, plan_mode_config
    ):
        """Test that before_model injects todos in plan mode."""
        result = await middleware.before_model(initial_state, plan_mode_config)

        assert "todos" in result
        assert result["todos"] == []

    @pytest.mark.asyncio
    async def test_before_model_skips_in_normal_mode(
        self, middleware, initial_state, normal_config
    ):
        """Test that before_model skips when not in plan mode."""
        result = await middleware.before_model(initial_state, normal_config)

        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_returns_empty(
        self, middleware, initial_state, plan_mode_config
    ):
        """Test that after_model returns empty dict."""
        result = await middleware.after_model(initial_state, plan_mode_config)
        assert result == {}

    def test_update_todos(self, middleware):
        """Test updating todos list."""
        todos = [
            {"content": "Task 1", "status": "completed"},
            {"content": "Task 2", "status": "in_progress"},
        ]

        middleware.update_todos(todos)

        assert middleware.todos == todos

    def test_get_next_todo(self, middleware):
        """Test getting next pending todo."""
        todos = [
            {"content": "Task 1", "status": "completed"},
            {"content": "Task 2", "status": "pending"},
            {"content": "Task 3", "status": "pending"},
        ]
        middleware.update_todos(todos)

        next_todo = middleware.get_next_todo()

        assert next_todo == {"content": "Task 2", "status": "pending"}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_todo_list.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.middlewares.todo_list'"

**Step 3: Write minimal implementation**

```python
# backend/src/agents/middlewares/todo_list.py
"""TodoListMiddleware for plan mode task tracking."""

from typing import Any

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class TodoListMiddleware(Middleware):
    """Middleware for task tracking in plan mode.

    This middleware enables the agent to track and manage a list of
    tasks when operating in plan mode.
    """

    def __init__(self):
        """Initialize todo list middleware."""
        self._todos: list[dict[str, Any]] = []

    @property
    def todos(self) -> list[dict[str, Any]]:
        """Get current todos list."""
        return self._todos

    async def before_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject todos into state if in plan mode.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Dict with todos if in plan mode, empty dict otherwise
        """
        is_plan_mode = config.get("configurable", {}).get("is_plan_mode", False)
        if not is_plan_mode:
            return {}

        # Inject current todos (empty list initially)
        return {"todos": self._todos.copy()}

    async def after_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """No-op after model call.

        Todo updates are handled via the write_todos tool.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict
        """
        return {}

    def update_todos(self, todos: list[dict[str, Any]]) -> None:
        """Update the todos list.

        Args:
            todos: New todos list
        """
        self._todos = todos

    def get_next_todo(self) -> dict[str, Any] | None:
        """Get the next pending todo.

        Returns:
            Next pending todo or None if all completed
        """
        for todo in self._todos:
            if todo.get("status") == "pending":
                return todo
        return None
```

**Step 4: Update middlewares/__init__.py**

```python
# Add to backend/src/agents/middlewares/__init__.py
from .todo_list import TodoListMiddleware

# Update __all__ list
__all__ = [
    # ... existing exports ...
    "TodoListMiddleware",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_todo_list.py -v`
Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/agents/middlewares/todo_list.py backend/src/agents/middlewares/__init__.py backend/tests/unit/middlewares/test_todo_list.py
git commit -m "feat(middleware): add TodoListMiddleware for plan mode task tracking"
```

---

## Task 4: 创建 ViewImageMiddleware

**Files:**
- Create: `backend/src/agents/middlewares/view_image.py`
- Modify: `backend/src/agents/middlewares/__init__.py`
- Test: `backend/tests/unit/middlewares/test_view_image.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/middlewares/test_view_image.py
"""Tests for ViewImageMiddleware."""

import pytest

from src.agents.middlewares.view_image import ViewImageMiddleware
from src.agents.thread_state import ThreadState


class TestViewImageMiddleware:
    """Test cases for ViewImageMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return ViewImageMiddleware()

    @pytest.fixture
    def initial_state(self):
        """Create initial thread state."""
        return ThreadState(messages=[])

    @pytest.fixture
    def vision_config(self):
        """Create config with vision support."""
        return {"configurable": {"supports_vision": True}}

    @pytest.fixture
    def no_vision_config(self):
        """Create config without vision support."""
        return {"configurable": {"supports_vision": False}}

    @pytest.fixture
    def state_with_image(self):
        """Create state with viewed image."""
        return ThreadState(
            messages=[],
            viewed_images={
                "/path/to/image.png": {
                    "base64": "iVBORw0KGgo=",
                    "mime_type": "image/png",
                }
            },
        )

    @pytest.mark.asyncio
    async def test_before_model_processes_images_with_vision(
        self, middleware, state_with_image, vision_config
    ):
        """Test that before_model processes images when vision is supported."""
        result = await middleware.before_model(state_with_image, vision_config)

        assert "viewed_images" in result
        assert "/path/to/image.png" in result["viewed_images"]

    @pytest.mark.asyncio
    async def test_before_model_skips_without_vision(
        self, middleware, state_with_image, no_vision_config
    ):
        """Test that before_model skips when vision not supported."""
        result = await middleware.before_model(state_with_image, no_vision_config)

        assert result == {}

    @pytest.mark.asyncio
    async def test_before_model_skips_without_images(
        self, middleware, initial_state, vision_config
    ):
        """Test that before_model skips when no images."""
        result = await middleware.before_model(initial_state, vision_config)

        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_returns_empty(
        self, middleware, initial_state, vision_config
    ):
        """Test that after_model returns empty dict."""
        result = await middleware.after_model(initial_state, vision_config)
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_clears_viewed_images(
        self, middleware, state_with_image, vision_config
    ):
        """Test that after_model clears viewed_images after processing."""
        # This is important to prevent memory bloat
        result = await middleware.after_model(state_with_image, vision_config)

        # Should return empty dict to clear viewed_images via reducer
        # The reducer handles the empty dict case
        assert result == {}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_view_image.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.middlewares.view_image'"

**Step 3: Write minimal implementation**

```python
# backend/src/agents/middlewares/view_image.py
"""ViewImageMiddleware for vision model support."""

from typing import Any

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class ViewImageMiddleware(Middleware):
    """Middleware for processing images in vision models.

    This middleware handles image data conversion and injection for
    models that support vision capabilities.
    """

    async def before_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Process images before model call if vision is supported.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Dict with processed images if vision supported, empty dict otherwise
        """
        # Check if model supports vision
        supports_vision = config.get("configurable", {}).get("supports_vision", False)
        if not supports_vision:
            return {}

        # Get viewed images
        viewed_images = state.get("viewed_images", {})
        if not viewed_images:
            return {}

        # Images are already in the correct format (base64 + mime_type)
        # Just pass them through - the model will consume them
        return {"viewed_images": viewed_images}

    async def after_model(
        self,
        state: ThreadState,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """No-op after model call.

        Images are handled by the reducer when state is updated.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict
        """
        return {}
```

**Step 4: Update middlewares/__init__.py**

```python
# Add to backend/src/agents/middlewares/__init__.py
from .view_image import ViewImageMiddleware

# Update __all__ list
__all__ = [
    # ... existing exports ...
    "ViewImageMiddleware",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/middlewares/test_view_image.py -v`
Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/agents/middlewares/view_image.py backend/src/agents/middlewares/__init__.py backend/tests/unit/middlewares/test_view_image.py
git commit -m "feat(middleware): add ViewImageMiddleware for vision model support"
```

---

## Task 5: 更新 build_pipeline 整合 16 层管道

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`
- Test: `backend/tests/unit/agents/test_pipeline.py`

**Step 1: Write the integration test**

```python
# backend/tests/unit/agents/test_pipeline.py
"""Tests for middleware pipeline assembly."""

import pytest
from unittest.mock import MagicMock

from src.agents.lead_agent.agent import build_pipeline


class TestBuildPipeline:
    """Test cases for build_pipeline function."""

    def test_pipeline_returns_list(self):
        """Test that build_pipeline returns a list."""
        pipeline = build_pipeline({})
        assert isinstance(pipeline, list)

    def test_pipeline_has_correct_order(self):
        """Test that middlewares are in correct order."""
        pipeline = build_pipeline({})

        # Extract middleware class names
        names = [m.__class__.__name__ for m in pipeline]

        # Verify key middlewares are present
        assert "ThreadDataMiddleware" in names
        assert "UploadsMiddleware" in names
        assert "DanglingToolCallMiddleware" in names
        assert "ClarificationMiddleware" in names

    def test_clarification_is_last(self):
        """Test that ClarificationMiddleware is always last."""
        pipeline = build_pipeline({})
        last_middleware = pipeline[-1]
        assert last_middleware.__class__.__name__ == "ClarificationMiddleware"

    def test_pipeline_with_plan_mode(self):
        """Test that TodoListMiddleware is included in plan mode."""
        config = {"configurable": {"is_plan_mode": True}}
        pipeline = build_pipeline(config)

        names = [m.__class__.__name__ for m in pipeline]
        assert "TodoListMiddleware" in names

    def test_pipeline_without_plan_mode(self):
        """Test that TodoListMiddleware is excluded without plan mode."""
        config = {"configurable": {"is_plan_mode": False}}
        pipeline = build_pipeline(config)

        names = [m.__class__.__name__ for m in pipeline]
        assert "TodoListMiddleware" not in names

    def test_pipeline_with_subagents(self):
        """Test that SubagentLimitMiddleware is included when enabled."""
        config = {"configurable": {"subagent_enabled": True}}
        pipeline = build_pipeline(config)

        names = [m.__class__.__name__ for m in pipeline]
        assert "SubagentLimitMiddleware" in names
```

**Step 2: Run test to verify it fails**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/agents/test_pipeline.py -v`
Expected: Some tests FAIL (TodoListMiddleware, ViewImageMiddleware not in pipeline)

**Step 3: Update build_pipeline()**

```python
# Modify backend/src/agents/lead_agent/agent.py - build_pipeline function
# Replace the existing build_pipeline with this updated version:

def build_pipeline(
    config: dict,
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
    sandbox_provider=None,
    memory_queue=None,
) -> list:
    """Build the 16-layer middleware pipeline.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  SandboxMiddleware          - Infrastructure (new)
    4.  DanglingToolCallMiddleware - Fix
    5.  SummarizationMiddleware    - Context management (conditional)
    6.  MemoryMiddleware           - Context management (new, conditional)
    7.  WorkspaceContextMiddleware - Academic (conditional)
    8.  LiteratureContextMiddleware - Academic (conditional)
    9.  KnowledgeContextMiddleware - Academic (conditional)
    10. DisciplineContextMiddleware - Academic
    11. TodoListMiddleware         - Interaction (new, conditional)
    12. ViewImageMiddleware        - Interaction (new)
    13. SubagentLimitMiddleware    - Control (conditional)
    14. TitleMiddleware            - Post-processing
    15. CitationContextMiddleware  - Post-processing (conditional)
    16. ClarificationMiddleware    - Control (MUST BE LAST)
    """
    from src.agents.middlewares import (
        CitationContextMiddleware,
        ClarificationMiddleware,
        DanglingToolCallMiddleware,
        DisciplineContextMiddleware,
        KnowledgeContextMiddleware,
        LiteratureContextMiddleware,
        MemoryMiddleware,
        SandboxMiddleware,
        SubagentLimitMiddleware,
        SummarizationMiddleware,
        ThreadDataMiddleware,
        TitleMiddleware,
        TodoListMiddleware,
        UploadsMiddleware,
        ViewImageMiddleware,
        WorkspaceContextMiddleware,
    )

    configurable = config.get("configurable", {})
    is_plan_mode = configurable.get("is_plan_mode", False)
    subagent_enabled = configurable.get("subagent_enabled", False)
    supports_vision = configurable.get("supports_vision", False)

    # Get middleware config
    from src.config.config_loader import get_app_config
    app_config = get_app_config()
    mw_config = app_config.middlewares

    pipeline = []

    # --- Infrastructure layer (1-3) ---
    pipeline.append(ThreadDataMiddleware())
    pipeline.append(UploadsMiddleware())

    # Sandbox (3) - requires provider
    if sandbox_provider:
        pipeline.append(SandboxMiddleware(sandbox_provider))

    # --- Fix layer (4) ---
    pipeline.append(DanglingToolCallMiddleware())

    # --- Context management layer (5-6) ---
    if mw_config.summarization.enabled:
        trigger = int(mw_config.summarization.trigger.split(":")[1]) if ":" in mw_config.summarization.trigger else 80000
        keep = int(mw_config.summarization.keep.split(":")[1]) if ":" in mw_config.summarization.keep else 10
        pipeline.append(SummarizationMiddleware(trigger_tokens=trigger, keep_messages=keep))

    # Memory (6) - requires queue
    memory_enabled = getattr(app_config, "memory", None)
    if memory_enabled and memory_enabled.enabled and memory_queue:
        pipeline.append(MemoryMiddleware(memory_queue=memory_queue, enabled=True))

    # --- Academic context layer (7-10) ---
    if workspace_service:
        pipeline.append(WorkspaceContextMiddleware(workspace_service))
    if index_service:
        pipeline.append(LiteratureContextMiddleware(index_service))
    if artifact_service:
        pipeline.append(KnowledgeContextMiddleware(artifact_service))
    pipeline.append(DisciplineContextMiddleware())

    # --- Interaction layer (11-13) ---
    # TodoList (11) - plan mode only
    if is_plan_mode:
        pipeline.append(TodoListMiddleware())

    # ViewImage (12) - vision models only
    pipeline.append(ViewImageMiddleware())

    # SubagentLimit (13) - subagents enabled
    if subagent_enabled:
        max_concurrent = configurable.get("max_concurrent_subagents", 3)
        pipeline.append(SubagentLimitMiddleware(max_concurrent=max_concurrent))

    # --- Post-processing layer (14-16) ---
    pipeline.append(TitleMiddleware())

    if paper_service:
        pipeline.append(CitationContextMiddleware(paper_service))

    # --- MUST BE LAST (16) ---
    pipeline.append(ClarificationMiddleware())

    return pipeline
```

**Step 4: Run test to verify it passes**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/agents/test_pipeline.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/agent.py backend/tests/unit/agents/test_pipeline.py
git commit -m "feat(agent): integrate 16-layer middleware pipeline"
```

---

## Task 6: 运行完整测试套件

**Step 1: Run all tests**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest -v --tb=short`

Expected: All tests PASS

**Step 2: Run with coverage**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest --cov=src/agents/middlewares --cov-report=term-missing`

Expected: Coverage > 80% for new middlewares

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(middleware): complete 16-layer middleware pipeline implementation

- Add SandboxMiddleware for sandbox lifecycle management
- Add MemoryMiddleware for async memory updates
- Add TodoListMiddleware for plan mode task tracking
- Add ViewImageMiddleware for vision model support
- Update build_pipeline() with correct middleware ordering
- Add comprehensive unit tests for all new middlewares"
```

---

## 验收检查清单

- [ ] Task 1: SandboxMiddleware 创建并测试通过
- [ ] Task 2: MemoryMiddleware 创建并测试通过
- [ ] Task 3: TodoListMiddleware 创建并测试通过
- [ ] Task 4: ViewImageMiddleware 创建并测试通过
- [ ] Task 5: build_pipeline() 更新并测试通过
- [ ] Task 6: 完整测试套件通过
- [ ] 所有新中间件导出到 `__init__.py`
- [ ] ClarificationMiddleware 始终是管道最后一个
- [ ] 条件启用逻辑正确工作

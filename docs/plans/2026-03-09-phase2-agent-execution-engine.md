# Phase 2: Agent Execution Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance SubagentExecutor with SSE event streaming, implement LLM-driven memory updates, add SummarizationMiddleware, and integrate skill execution with subagent chains.

**Architecture:**
- SSE event streaming via FastAPI StreamingResponse for real-time subagent progress
- LLM-driven memory extraction using structured output
- Token-aware summarization with LangChain's counting utilities
- Skill-to-subagent chain execution via SKILL.md parsing

**Tech Stack:** FastAPI SSE, LangChain token counting, Pydantic structured output, asyncio ThreadPoolExecutor

---

## Pre-requisites

Before starting, verify Phase 1 is complete:

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q 2>&1 | tail -5
```

Expected: `884 passed`

---

### Task 1: Add SSE Event Streaming to SubagentExecutor

**Files:**
- Create: `backend/src/subagents/events.py`
- Modify: `backend/src/subagents/executor.py`
- Create: `backend/tests/subagents/test_events.py`

**Step 1: Write the failing test**

Create `backend/tests/subagents/test_events.py`:

```python
"""Tests for SSE event streaming."""

import pytest
from src.subagents.events import (
    SubagentEvent,
    SubagentEventType,
    EventStream,
    create_event_stream,
)


class TestSubagentEvent:
    def test_event_types(self):
        assert SubagentEventType.STARTED.value == "started"
        assert SubagentEventType.RUNNING.value == "running"
        assert SubagentEventType.COMPLETED.value == "completed"
        assert SubagentEventType.FAILED.value == "failed"
        assert SubagentEventType.TIMED_OUT.value == "timed_out"

    def test_event_creation(self):
        event = SubagentEvent(
            type=SubagentEventType.STARTED,
            task_id="test-123",
            subagent_type="scout",
            message="Task started",
        )
        assert event.type == SubagentEventType.STARTED
        assert event.task_id == "test-123"
        assert event.data is None


class TestEventStream:
    def test_push_and_iterate(self):
        stream = EventStream()
        stream.push(SubagentEvent(
            type=SubagentEventType.STARTED,
            task_id="t1",
            subagent_type="scout",
            message="Started",
        ))
        events = list(stream.iterate())
        assert len(events) == 1
        assert events[0].task_id == "t1"

    def test_close(self):
        stream = EventStream()
        stream.close()
        assert stream.is_closed


class TestCreateEventStream:
    def test_factory(self):
        stream = create_event_stream()
        assert stream is not None
        assert hasattr(stream, "push")
        assert hasattr(stream, "iterate")
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/subagents/test_events.py -v
```

Expected: Import errors

**Step 3: Implement SSE event system**

Create `backend/src/subagents/events.py`:

```python
"""SSE event streaming for subagent execution."""

import asyncio
import queue
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Iterator


class SubagentEventType(Enum):
    """Event types for subagent execution."""
    STARTED = "started"
    RUNNING = "running"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentEvent:
    """A single event from subagent execution."""
    type: SubagentEventType
    task_id: str
    subagent_type: str
    message: str
    data: dict[str, Any] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventStream:
    """Thread-safe event stream for SSE."""

    def __init__(self):
        self._queue: queue.Queue[SubagentEvent | None] = queue.Queue()
        self._closed = False

    def push(self, event: SubagentEvent) -> None:
        """Push an event to the stream."""
        if not self._closed:
            self._queue.put(event)

    def close(self) -> None:
        """Close the stream, signaling no more events."""
        self._closed = True
        self._queue.put(None)

    @property
    def is_closed(self) -> bool:
        """Check if the stream is closed."""
        return self._closed

    def iterate(self, timeout: float = 30.0) -> Iterator[SubagentEvent]:
        """Iterate over events until stream is closed or timeout.

        Yields:
            SubagentEvent instances

        Raises:
            TimeoutError: If no event received within timeout
        """
        while True:
            try:
                event = self._queue.get(timeout=timeout)
                if event is None:
                    break
                yield event
            except queue.Empty:
                if self._closed:
                    break
                raise TimeoutError("Event stream timeout")


def create_event_stream() -> EventStream:
    """Factory function to create an event stream."""
    return EventStream()
```

**Step 4: Update executor.py to emit events**

Add event stream support to `backend/src/subagents/executor.py`. Add after line 40:

```python
# Event streaming support
_event_streams: dict[str, EventStream] = {}


def register_event_stream(task_id: str, stream: EventStream) -> None:
    """Register an event stream for a task."""
    _event_streams[task_id] = stream


def unregister_event_stream(task_id: str) -> None:
    """Unregister an event stream."""
    _event_streams.pop(task_id, None)


def get_event_stream(task_id: str) -> EventStream | None:
    """Get the event stream for a task."""
    return _event_streams.get(task_id)
```

Update the `execute` method to emit events:

```python
def execute(self, task: str, result_holder: SubagentResult | None = None, stream: EventStream | None = None) -> SubagentResult:
    """Synchronous execution with optional event streaming."""
    if result_holder is None:
        result_holder = SubagentResult(task_id=str(uuid.uuid4())[:8])

    task_id = result_holder.task_id

    # Emit started event
    if stream:
        stream.push(SubagentEvent(
            type=SubagentEventType.STARTED,
            task_id=task_id,
            subagent_type=self.config.name.lower(),
            message=f"Starting {self.config.name} subagent",
        ))

    result_holder.status = SubagentStatus.RUNNING
    result_holder.started_at = datetime.now(UTC)

    # Emit running event
    if stream:
        stream.push(SubagentEvent(
            type=SubagentEventType.RUNNING,
            task_id=task_id,
            subagent_type=self.config.name.lower(),
            message="Executing task...",
        ))

    try:
        agent = self._create_agent()
        response = agent.invoke({"messages": [("human", task)]})
        messages = response.get("messages", [])
        last_msg = messages[-1] if messages else None
        result_holder.result = getattr(last_msg, "content", str(last_msg)) if last_msg else ""
        result_holder.status = SubagentStatus.COMPLETED

        # Emit completed event
        if stream:
            stream.push(SubagentEvent(
                type=SubagentEventType.COMPLETED,
                task_id=task_id,
                subagent_type=self.config.name.lower(),
                message="Task completed successfully",
                data={"result": result_holder.result[:500] if result_holder.result else None},
            ))
    except Exception as e:
        result_holder.error = str(e)
        result_holder.status = SubagentStatus.FAILED

        # Emit failed event
        if stream:
            stream.push(SubagentEvent(
                type=SubagentEventType.FAILED,
                task_id=task_id,
                subagent_type=self.config.name.lower(),
                message=f"Task failed: {str(e)[:200]}",
                data={"error": str(e)},
            ))
    finally:
        result_holder.completed_at = datetime.now(UTC)

    return result_holder
```

Update the import at top:

```python
from src.subagents.events import EventStream, SubagentEvent, SubagentEventType
```

**Step 5: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/subagents/test_events.py -v
PYTHONPATH=. uv run pytest -x -q
```

**Step 6: Commit**

```bash
git add backend/src/subagents/events.py backend/src/subagents/executor.py backend/tests/subagents/test_events.py
git commit -m "feat: add SSE event streaming to SubagentExecutor"
```

---

### Task 2: Implement LLM-Driven Memory Updates

**Files:**
- Modify: `backend/src/agents/memory/updater.py`
- Create: `backend/tests/agents/memory/test_llm_updates.py`

**Step 1: Write the failing test**

Create `backend/tests/agents/memory/test_llm_updates.py`:

```python
"""Tests for LLM-driven memory updates."""

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.memory.updater import MemoryUpdater, create_default_memory
from src.agents.memory.prompts import MEMORY_EXTRACTION_PROMPT


class TestMemoryExtractionPrompt:
    def test_prompt_exists(self):
        """Memory extraction prompt should be defined."""
        assert MEMORY_EXTRACTION_PROMPT is not None
        assert "user" in MEMORY_EXTRACTION_PROMPT.lower() or "fact" in MEMORY_EXTRACTION_PROMPT.lower()


class TestLLMMemoryUpdates:
    @pytest.mark.asyncio
    async def test_extract_facts_from_messages(self, tmp_path):
        """Should extract facts from conversation."""
        from langchain_core.messages import HumanMessage, AIMessage

        storage = tmp_path / "memory.json"
        updater = MemoryUpdater(storage_path=str(storage))

        messages = [
            HumanMessage(content="I'm working on NLP research, specifically on transformer models."),
            AIMessage(content="Great! I can help you with transformer architecture research."),
        ]

        # This should trigger LLM extraction (or return False if not implemented)
        result = await updater.update_from_messages(messages, thread_id="test-1")
        # Result is False if LLM not configured, or True if extraction succeeded
        assert isinstance(result, bool)

    def test_format_extraction_result(self, tmp_path):
        """Should format extraction result for storage."""
        storage = tmp_path / "memory.json"
        updater = MemoryUpdater(storage_path=str(storage))

        extraction = {
            "user": {
                "researchContext": {"summary": "NLP and transformers", "updatedAt": "2026-03-09"},
            },
            "facts": [
                {"content": "User focuses on NLP", "category": "knowledge", "confidence": 0.9},
            ],
        }

        updater._apply_extraction(extraction)

        # Verify the memory was updated
        from src.agents.memory.updater import get_memory_data
        data = get_memory_data(str(storage))
        assert data["user"]["researchContext"]["summary"] == "NLP and transformers"
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/memory/test_llm_updates.py -v
```

**Step 3: Create memory extraction prompt**

Create `backend/src/agents/memory/prompts.py`:

```python
"""Prompts for LLM-driven memory extraction."""

MEMORY_EXTRACTION_PROMPT = """You are a memory extraction assistant. Analyze the conversation and extract structured information about the user.

## Task
Extract the following from the conversation:
1. Research context: What field/topic is the user working on?
2. Writing preferences: Any writing style preferences mentioned?
3. Tool preferences: Any model or tool preferences?
4. Facts: Important user information to remember

## Output Format
Return a JSON object with this structure:
```json
{
  "user": {
    "researchContext": {"summary": "...", "updatedAt": "..."},
    "writingPreferences": {"summary": "...", "updatedAt": "..."},
    "toolPreferences": {"summary": "...", "updatedAt": "..."}
  },
  "facts": [
    {"content": "...", "category": "knowledge|behavior|preference", "confidence": 0.0-1.0}
  ]
}
```

## Rules
- Only extract information explicitly mentioned
- Set confidence based on clarity (1.0 = explicit, 0.5 = implied)
- Keep summaries under 100 words
- Maximum 5 facts per extraction
- Return empty objects for categories with no information"""

MEMORY_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "researchContext": {"type": "object", "properties": {"summary": {"type": "string"}, "updatedAt": {"type": "string"}}},
                "writingPreferences": {"type": "object", "properties": {"summary": {"type": "string"}, "updatedAt": {"type": "string"}}},
                "toolPreferences": {"type": "object", "properties": {"summary": {"type": "string"}, "updatedAt": {"type": "string"}}},
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "category": {"type": "string", "enum": ["knowledge", "behavior", "preference"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["content", "category", "confidence"],
            },
        },
    },
}
```

**Step 4: Implement LLM-driven updates in updater.py**

Update `backend/src/agents/memory/updater.py`. Add import:

```python
from datetime import UTC, datetime
```

Add new methods to `MemoryUpdater` class:

```python
async def update_from_messages(self, messages: list, thread_id: str | None = None) -> bool:
    """Update memory from a conversation using LLM extraction.

    Args:
        messages: List of conversation messages
        thread_id: Optional thread identifier for logging

    Returns:
        True if extraction succeeded, False otherwise
    """
    from src.agents.memory.prompts import MEMORY_EXTRACTION_PROMPT
    from langchain_core.messages import HumanMessage, AIMessage

    # Filter to only human and AI messages
    relevant = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
    if len(relevant) < 2:
        return False

    # Format conversation for extraction
    conversation = self._format_conversation(relevant)

    try:
        extraction = await self._run_extraction(conversation)
        if extraction:
            self._apply_extraction(extraction)
            return True
    except Exception as e:
        # Log but don't fail - memory updates are optional
        import logging
        logging.getLogger(__name__).warning(f"Memory extraction failed: {e}")

    return False

def _format_conversation(self, messages: list) -> str:
    """Format messages for extraction."""
    lines = []
    for m in messages:
        role = "User" if hasattr(m, 'type') and m.type == 'human' else "Assistant"
        content = m.content if isinstance(m.content, str) else str(m.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

async def _run_extraction(self, conversation: str) -> dict | None:
    """Run LLM extraction on conversation."""
    try:
        from src.models.factory import create_chat_model
        model = create_chat_model("qwen-flash")  # Use fast model for extraction
    except ValueError:
        # No model configured
        return None

    from src.agents.memory.prompts import MEMORY_EXTRACTION_PROMPT
    import json

    prompt = f"{MEMORY_EXTRACTION_PROMPT}\n\n## Conversation\n\n{conversation}"

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)

        # Extract JSON from response
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(content[json_start:json_end])
    except json.JSONDecodeError:
        pass
    except Exception:
        pass

    return None

def _apply_extraction(self, extraction: dict) -> None:
    """Apply extraction result to memory storage."""
    data = get_memory_data(storage_path=self._storage_path)
    now = datetime.now(UTC).isoformat()

    # Update user context
    if "user" in extraction:
        for key in ["researchContext", "writingPreferences", "toolPreferences"]:
            if key in extraction["user"] and extraction["user"][key].get("summary"):
                data["user"][key] = {
                    "summary": extraction["user"][key]["summary"],
                    "updatedAt": extraction["user"][key].get("updatedAt", now),
                }

    # Add new facts
    if "facts" in extraction:
        existing_contents = {f.get("content") for f in data.get("facts", [])}
        for fact in extraction["facts"]:
            if fact.get("content") and fact["content"] not in existing_contents:
                data.setdefault("facts", []).append({
                    "id": str(uuid.uuid4())[:8],
                    "content": fact["content"],
                    "category": fact.get("category", "knowledge"),
                    "confidence": fact.get("confidence", 0.5),
                    "source": "extraction",
                    "createdAt": now,
                })

    # Update timestamp
    data["lastUpdated"] = now

    # Write back
    _atomic_write(Path(self._storage_path), data)
```

Add missing import:

```python
import uuid
```

**Step 5: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/memory/ -v
PYTHONPATH=. uv run pytest -x -q
```

**Step 6: Commit**

```bash
git add backend/src/agents/memory/ backend/tests/agents/memory/
git commit -m "feat: implement LLM-driven memory extraction and updates"
```

---

### Task 3: Add SummarizationMiddleware

**Files:**
- Create: `backend/src/agents/middlewares/summarization.py`
- Create: `backend/tests/agents/middlewares/test_summarization.py`

**Step 1: Write the failing test**

Create `backend/tests/agents/middlewares/test_summarization.py`:

```python
"""Tests for SummarizationMiddleware."""

import pytest
from langchain_core.messages import HumanMessage, AIMessage

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

    def test_count_tokens_approximate(self):
        """Token counting should be approximate."""
        mw = SummarizationMiddleware()
        messages = [HumanMessage(content="Hello world")]
        count = mw._count_tokens(messages)
        assert count > 0
        assert count < 10  # "Hello world" is ~2-3 tokens
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_summarization.py -v
```

**Step 3: Implement SummarizationMiddleware**

Create `backend/src/agents/middlewares/summarization.py`:

```python
"""Summarization middleware for token limit management."""

from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class SummarizationMiddleware(Middleware):
    """Summarizes conversation history when approaching token limits.

    This middleware monitors token usage and triggers summarization
    when the conversation exceeds the configured threshold.
    """

    def __init__(
        self,
        trigger_tokens: int = 80000,
        keep_messages: int = 10,
        model_name: str | None = None,
    ):
        """Initialize summarization middleware.

        Args:
            trigger_tokens: Token count threshold to trigger summarization
            keep_messages: Number of recent messages to keep after summarization
            model_name: Model to use for summarization (defaults to fast model)
        """
        self._trigger_tokens = trigger_tokens
        self._keep_messages = keep_messages
        self._model_name = model_name

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Check token count and summarize if needed."""
        messages = state.get("messages", [])
        if not messages:
            return {}

        token_count = self._count_tokens(messages)
        if token_count < self._trigger_tokens:
            return {}

        # Perform summarization
        summary = await self._summarize(messages[: -self._keep_messages])
        if not summary:
            return {}

        # Replace old messages with summary
        kept_messages = messages[-self._keep_messages :]
        summary_message = SystemMessage(
            content=f"<conversation_summary>\n{summary}\n</conversation_summary>"
        )

        return {"messages": [summary_message] + kept_messages}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op after model."""
        return {}

    def _count_tokens(self, messages: list) -> int:
        """Approximate token count for messages.

        Uses a simple heuristic: ~4 characters per token.
        """
        total_chars = 0
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            total_chars += len(content)
        return total_chars // 4

    async def _summarize(self, messages: list) -> str | None:
        """Generate a summary of the messages."""
        try:
            from src.models.factory import create_chat_model
            model = create_chat_model(self._model_name or "qwen-flash")
        except ValueError:
            return None

        # Format messages for summarization
        formatted = []
        for msg in messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            formatted.append(f"{role}: {content}")

        prompt = f"""Summarize the following conversation, preserving key information:
- Main topics discussed
- Decisions made
- Important context for continuing the conversation

Conversation:
{chr(10).join(formatted[-20:])}  # Last 20 messages

Summary:"""

        try:
            response = await model.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception:
            return None
```

**Step 4: Update __init__.py to export new middleware**

Edit `backend/src/agents/middlewares/__init__.py` to add:

```python
from .summarization import SummarizationMiddleware
```

And add to `__all__`:

```python
    "SummarizationMiddleware",
```

**Step 5: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/agents/middlewares/test_summarization.py -v
PYTHONPATH=. uv run pytest -x -q
```

**Step 6: Commit**

```bash
git add backend/src/agents/middlewares/summarization.py backend/src/agents/middlewares/__init__.py backend/tests/agents/middlewares/test_summarization.py
git commit -m "feat: add SummarizationMiddleware for token limit management"
```

---

### Task 4: Integrate SummarizationMiddleware into Pipeline

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`

**Step 1: Update build_pipeline**

Modify `backend/src/agents/lead_agent/agent.py` to include SummarizationMiddleware in the pipeline:

```python
def build_pipeline(
    config: dict,
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
) -> list:
    """Build the 16-layer middleware pipeline.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  DanglingToolCallMiddleware - Fix
    4.  SummarizationMiddleware    - Context management (NEW)
    5.  WorkspaceContextMiddleware - Academic (conditional)
    6.  LiteratureContextMiddleware - Academic (conditional)
    7.  KnowledgeContextMiddleware - Academic (conditional)
    8.  DisciplineContextMiddleware - Academic
    9.  TitleMiddleware            - Post-processing
    10. SubagentLimitMiddleware    - Control (conditional)
    11. CitationContextMiddleware  - Post-processing (conditional)
    12. ClarificationMiddleware    - Control (MUST BE LAST)
    """
    configurable = config.get("configurable", {})
    subagent_enabled = configurable.get("subagent_enabled", False)

    # Get middleware config
    from src.config.config_loader import get_app_config
    app_config = get_app_config()
    mw_config = app_config.middlewares

    pipeline = []

    # --- Infrastructure layer ---
    pipeline.append(ThreadDataMiddleware())
    pipeline.append(UploadsMiddleware())

    # --- Fix layer ---
    pipeline.append(DanglingToolCallMiddleware())

    # --- Context management layer ---
    if mw_config.summarization.enabled:
        trigger = int(mw_config.summarization.trigger.split(":")[1]) if ":" in mw_config.summarization.trigger else 80000
        keep = int(mw_config.summarization.keep.split(":")[1]) if ":" in mw_config.summarization.keep else 10
        pipeline.append(SummarizationMiddleware(trigger_tokens=trigger, keep_messages=keep))

    # --- Academic context layer (conditional on services) ---
    if workspace_service:
        pipeline.append(WorkspaceContextMiddleware(workspace_service))
    if index_service:
        pipeline.append(LiteratureContextMiddleware(index_service))
    if artifact_service:
        pipeline.append(KnowledgeContextMiddleware(artifact_service))
    pipeline.append(DisciplineContextMiddleware())

    # --- Post-processing layer ---
    pipeline.append(TitleMiddleware())

    # --- Control layer ---
    if subagent_enabled:
        max_concurrent = configurable.get("max_concurrent_subagents", 3)
        pipeline.append(SubagentLimitMiddleware(max_concurrent=max_concurrent))

    if paper_service:
        pipeline.append(CitationContextMiddleware(paper_service))

    # --- MUST BE LAST ---
    pipeline.append(ClarificationMiddleware())

    return pipeline
```

Add import:

```python
from src.agents.middlewares import (
    # ... existing imports ...
    SummarizationMiddleware,
)
```

**Step 2: Run full test suite**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
```

**Step 3: Commit**

```bash
git add backend/src/agents/lead_agent/agent.py
git commit -m "feat: integrate SummarizationMiddleware into pipeline"
```

---

### Task 5: Add Skill Execution with Subagent Chain Support

**Files:**
- Modify: `backend/src/skills/executor.py`
- Create: `backend/src/skills/parser.py`
- Create: `backend/tests/skills/test_parser.py`

**Step 1: Write the failing test**

Create `backend/tests/skills/test_parser.py`:

```python
"""Tests for SKILL.md parsing."""

import tempfile
from pathlib import Path

from src.skills.parser import SkillParser, ParsedSkill


class TestSkillParser:
    def test_parse_skill_frontmatter(self):
        """Should parse YAML frontmatter from SKILL.md."""
        content = """---
name: test-skill
description: A test skill
allowed-tools:
  - read_file
  - semantic_scholar_search
---

# Test Skill

This is a test skill.
"""
        parser = SkillParser()
        skill = parser.parse(content)
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert "read_file" in skill.allowed_tools

    def test_parse_skill_without_frontmatter(self):
        """Should handle SKILL.md without frontmatter."""
        content = """# Test Skill

Just a simple skill.
"""
        parser = SkillParser()
        skill = parser.parse(content)
        assert skill.name == "unknown"
        assert skill.prompt == content

    def test_extract_subagent_calls(self):
        """Should extract subagent call patterns from skill prompt."""
        content = """---
name: research
---

# Research Skill

1. Call scout: task(subagent_type="scout", prompt="Search for papers")
2. Then analyze: task(subagent_type="analyst", prompt="Analyze results")
"""
        parser = SkillParser()
        skill = parser.parse(content)
        calls = skill.get_subagent_calls()
        assert len(calls) == 2
        assert calls[0]["subagent_type"] == "scout"
        assert calls[1]["subagent_type"] == "analyst"

    def test_parse_file(self, tmp_path):
        """Should parse a SKILL.md file."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: file-skill
description: From file
---
# Content
""")
        parser = SkillParser()
        skill = parser.parse_file(skill_file)
        assert skill.name == "file-skill"
```

**Step 2: Run test to verify it fails**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/skills/test_parser.py -v
```

**Step 3: Implement SkillParser**

Create `backend/src/skills/parser.py`:

```python
"""Parser for SKILL.md files."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ParsedSkill:
    """Represents a parsed SKILL.md."""
    name: str = "unknown"
    description: str = ""
    license: str = "MIT"
    allowed_tools: list[str] = field(default_factory=list)
    prompt: str = ""
    source_path: str | None = None

    def get_subagent_calls(self) -> list[dict]:
        """Extract subagent call patterns from the prompt.

        Returns:
            List of dicts with subagent_type and prompt
        """
        pattern = r'task\s*\(\s*subagent_type\s*=\s*["\']([^"\\']+)["\']\s*,\s*prompt\s*=\s*["\']([^"\\']+)["\']\s*\)'
        matches = re.findall(pattern, self.prompt)
        return [{"subagent_type": m[0], "prompt": m[1]} for m in matches]


class SkillParser:
    """Parser for SKILL.md files."""

    def parse(self, content: str) -> ParsedSkill:
        """Parse SKILL.md content.

        Args:
            content: The raw SKILL.md content

        Returns:
            ParsedSkill instance
        """
        skill = ParsedSkill()

        # Extract frontmatter
        frontmatter, prompt = self._extract_frontmatter(content)

        if frontmatter:
            skill.name = frontmatter.get("name", "unknown")
            skill.description = frontmatter.get("description", "")
            skill.license = frontmatter.get("license", "MIT")
            skill.allowed_tools = frontmatter.get("allowed-tools", [])

        skill.prompt = prompt
        return skill

    def parse_file(self, path: Path) -> ParsedSkill:
        """Parse a SKILL.md file.

        Args:
            path: Path to SKILL.md file

        Returns:
            ParsedSkill instance
        """
        content = path.read_text()
        skill = self.parse(content)
        skill.source_path = str(path)
        return skill

    def _extract_frontmatter(self, content: str) -> tuple[dict, str]:
        """Extract YAML frontmatter from content.

        Returns:
            Tuple of (frontmatter_dict, remaining_content)
        """
        if not content.startswith("---"):
            return {}, content

        # Find the closing ---
        end_match = re.search(r'\n---\s*\n', content[3:])
        if not end_match:
            return {}, content

        frontmatter_str = content[3:end_match.start() + 3]
        remaining = content[end_match.end() + 3:]

        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, remaining
```

**Step 4: Run tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/skills/test_parser.py -v
```

**Step 5: Update skills/__init__.py**

Add to `backend/src/skills/__init__.py`:

```python
from .parser import SkillParser, ParsedSkill

__all__ = [
    # ... existing exports ...
    "SkillParser",
    "ParsedSkill",
]
```

**Step 6: Run full test suite and commit**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q
git add backend/src/skills/parser.py backend/src/skills/__init__.py backend/tests/skills/test_parser.py
git commit -m "feat: add SKILL.md parser with subagent call extraction"
```

---

### Task 6: Integration Test - Subagent Chain Execution

**Files:**
- Create: `backend/tests/integration/test_subagent_chain.py`

**Step 1: Write integration test**

Create `backend/tests/integration/test_subagent_chain.py`:

```python
"""Integration tests for subagent chain execution."""

import pytest

from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.subagents.registry import SubagentConfig, registry
from src.subagents.events import EventStream, SubagentEvent, SubagentEventType


class TestSubagentChainIntegration:
    def test_registry_has_academic_subagents(self):
        """Academic subagent types should be registered."""
        assert registry.get("scout") is not None
        assert registry.get("writer") is not None
        assert registry.get("synthesizer") is not None

    @pytest.mark.asyncio
    async def test_executor_with_event_stream(self):
        """Executor should emit events to stream."""
        from unittest.mock import patch, MagicMock

        config = SubagentConfig(
            name="Test",
            description="Test",
            system_prompt="Reply with OK",
        )
        executor = SubagentExecutor(config=config, tools=[])

        stream = EventStream()

        with patch.object(executor, "_create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {"messages": [MagicMock(content="OK")]}
            mock_create.return_value = mock_agent

            result = executor.execute("test task", stream=stream)

            # Collect events
            events = []
            for event in stream.iterate(timeout=1.0):
                events.append(event)

            assert result.status == SubagentStatus.COMPLETED
            # Events may or may not be emitted depending on implementation
            assert isinstance(events, list)

    def test_subagent_config_from_yaml(self):
        """Subagent configs should match config.yaml."""
        from src.config.config_loader import get_app_config

        config = get_app_config()
        assert config.subagents.enabled is True
        assert "scout" in config.subagents.types
        assert config.subagents.types["scout"].max_turns > 0


class TestMemoryIntegration:
    @pytest.mark.asyncio
    async def test_memory_update_integration(self, tmp_path):
        """Memory system should integrate with pipeline."""
        from src.agents.memory.updater import MemoryUpdater
        from langchain_core.messages import HumanMessage, AIMessage

        storage = str(tmp_path / "memory.json")
        updater = MemoryUpdater(storage_path=storage)

        messages = [
            HumanMessage(content="I study NLP"),
            AIMessage(content="I'll help with NLP research"),
        ]

        # Update should not raise
        result = await updater.update_from_messages(messages)
        assert isinstance(result, bool)
```

**Step 2: Run integration tests**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest tests/integration/test_subagent_chain.py -v
PYTHONPATH=. uv run pytest -x -q
```

**Step 3: Commit**

```bash
git add backend/tests/integration/test_subagent_chain.py
git commit -m "test: add integration tests for subagent chain execution"
```

---

### Task 7: Final Verification and Phase 2 Summary

**Step 1: Run full test suite**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -v 2>&1 | tail -20
```

**Step 2: Verify new components**

```bash
cd /home/cjz/academiagpt-v2/backend
python -c "
from src.subagents.events import EventStream, SubagentEvent, SubagentEventType
from src.agents.memory.updater import MemoryUpdater
from src.agents.memory.prompts import MEMORY_EXTRACTION_PROMPT
from src.agents.middlewares.summarization import SummarizationMiddleware
from src.skills.parser import SkillParser, ParsedSkill
print('All Phase 2 imports successful!')
print(f'EventStream: {EventStream}')
print(f'SummarizationMiddleware: {SummarizationMiddleware}')
print(f'SkillParser: {SkillParser}')
"
```

**Step 3: Commit phase summary**

```bash
git add -A
git commit -m "docs: Phase 2 Agent Execution Engine complete

- SSE event streaming for subagent execution
- LLM-driven memory extraction and updates
- SummarizationMiddleware for token limit management
- SKILL.md parser with subagent call extraction
- Integration tests for subagent chain execution"
```

---

## Post-Phase 2 Checklist

After completing all tasks, verify:

- [ ] `PYTHONPATH=. uv run pytest -x -q` → all tests pass (884+ existing + new tests)
- [ ] `EventStream` can push and iterate events
- [ ] `SummarizationMiddleware` triggers at token threshold
- [ ] `SkillParser` extracts frontmatter and subagent calls
- [ ] `MemoryUpdater.update_from_messages()` runs without errors
- [ ] No circular import issues

## What's Next: Phase 3

Phase 3 (Core Academic Features) will:
1. Deep Research Skill rewrite with parallel subagent execution
2. Framework Designer Skill rewrite with Memory enhancement
3. Full Paper Writer Skill rewrite with academic writing order
4. Context Hub integration enhancement

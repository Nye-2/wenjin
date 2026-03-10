# Phase 2: Subagent System Design Document

> Created: 2026-03-10
> Status: Approved
> Author: Claude + User

## 1. Overview

### 1.1 Background

Phase 1 (Sandbox System) is complete. Phase 2 implements the subagent system that enables spawning AI subagents to handle complex tasks in parallel.

### 1.2 Goals

- Dual-layer thread pool architecture (global + per-thread concurrency limits)
- SSE event stream for real-time status updates
- LangGraph integration for agent orchestration
- Configurable concurrency control
- Integration with Phase 1 sandbox tools

### 1.3 Scope

**In Scope:**
- Core framework: executor, manager, event stream, limiter
- LangGraph graph building and templates
- API endpoints for spawn/status/cancel
- SSE endpoint for real-time events

**Out of Scope (Future Phases):**
- Academic-specific agents (researcher, writer, reviewer, analyst)
- Advanced graph templates
- Distributed execution

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                       │
├─────────────────────────────────────────────────────────────────┤
│  GlobalSubagentManager (Singleton)                              │
│  ├── DualLayerLimiter                                          │
│  │   ├── GlobalConcurrencyLimiter (max: 10)                    │
│  │   └── ThreadLimiters[thread_id] (max: 3 each)               │
│  ├── SubagentEventStream ───────────────────► SSE /events      │
│  ├── ThreadRegistry                                            │
│  │   └── ThreadContext[thread_id]                              │
│  │       ├── LocalLimiter                                      │
│  │       ├── TaskQueue                                         │
│  │       └── ResultsCache                                      │
│  ├── SubagentExecutor                                          │
│  │   ├── LangGraph Instance                                    │
│  │   └── Tools (Sandbox Tools)                                 │
│  └── GraphTemplateRegistry                                     │
│      └── Compiled Graph Templates                              │
├─────────────────────────────────────────────────────────────────┤
│  API Routes                                                     │
│  ├── POST /threads/{id}/subagents/spawn                        │
│  ├── GET  /threads/{id}/subagents/{task_id}/status             │
│  ├── POST /threads/{id}/subagents/{task_id}/cancel             │
│  └── GET  /subagents/events (SSE)                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Directory Structure

```
src/subagents/
├── __init__.py              # Public exports
├── models.py                # Data models (Task, Event, Result, Status)
├── config.py                # SubagentConfig with Pydantic Settings
├── limiter.py               # ConcurrencyLimiter, DualLayerLimiter
├── events.py                # SubagentEventStream
├── graph.py                 # GraphTemplateRegistry, create_default_graph
├── executor.py              # SubagentExecutor
└── manager.py               # GlobalSubagentManager, ThreadContext

src/api/
└── subagents.py             # FastAPI routes

tests/subagents/
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

## 3. Data Models

### 3.1 Status Enum

```python
class SubagentStatus(str, Enum):
    PENDING = "pending"       # Waiting for execution slot
    RUNNING = "running"       # Currently executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Execution failed
    CANCELLED = "cancelled"   # Cancelled by user
    TIMEOUT = "timeout"       # Exceeded time limit
```

### 3.2 Task Definition

```python
@dataclass
class SubagentTask:
    task_id: str
    thread_id: str
    prompt: str
    graph_template: str = "default"
    max_turns: int = 10
    timeout: int = 900  # 15 minutes
    created_at: datetime = field(default_factory=datetime.now)
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 3.3 Event Model

```python
@dataclass
class SubagentEvent:
    event_type: str  # task_started, turn_complete, task_completed, task_failed, task_cancelled
    task_id: str
    thread_id: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_sse(self) -> str:
        """Convert to SSE format string"""
        return f"event: {self.event_type}\ndata: {json.dumps(self.to_dict())}\n\n"
```

### 3.4 Result Model

```python
@dataclass
class SubagentResult:
    task_id: str
    status: SubagentStatus
    output: Optional[str] = None
    error: Optional[str] = None
    turns_used: int = 0
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 4. Concurrency Limiter

### 4.1 Single Limiter

```python
class ConcurrencyLimiter:
    """Generic concurrency limiter using semaphore"""

    def __init__(self, max_concurrent: int):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self):
        async with self._semaphore:
            async with self._lock:
                self._active_count += 1
            try:
                yield
            finally:
                async with self._lock:
                    self._active_count -= 1

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def available_slots(self) -> int:
        return self._semaphore._value
```

### 4.2 Dual-Layer Limiter

```python
class DualLayerLimiter:
    """Global + per-thread concurrency control"""

    def __init__(self, global_max: int, per_thread_max: int):
        self._global = ConcurrencyLimiter(global_max)
        self._per_thread_max = per_thread_max
        self._thread_limiters: dict[str, ConcurrencyLimiter] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, thread_id: str):
        # Acquire global slot first
        async with self._global.acquire():
            # Then acquire thread slot
            limiter = await self._get_or_create_thread_limiter(thread_id)
            async with limiter.acquire():
                yield

    async def _get_or_create_thread_limiter(self, thread_id: str) -> ConcurrencyLimiter:
        async with self._lock:
            if thread_id not in self._thread_limiters:
                self._thread_limiters[thread_id] = ConcurrencyLimiter(
                    self._per_thread_max
                )
            return self._thread_limiters[thread_id]

    def cleanup_thread(self, thread_id: str) -> None:
        """Remove thread limiter when thread is cleaned up"""
        if thread_id in self._thread_limiters:
            del self._thread_limiters[thread_id]
```

## 5. SSE Event Stream

```python
class SubagentEventStream:
    """Manages SSE subscriptions with thread filtering"""

    def __init__(self, max_queue_size: int = 100):
        self._subscribers: dict[str, asyncio.Queue[SubagentEvent]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, thread_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Subscribe to event stream.

        Args:
            thread_id: If specified, only receive events for this thread.
                       None means receive all events.
        """
        queue: asyncio.Queue[SubagentEvent | None] = asyncio.Queue(
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
        """Publish event to relevant subscribers"""
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
        """Close all subscriptions"""
        async with self._lock:
            for queue in self._subscribers.values():
                await queue.put(None)
            self._subscribers.clear()
```

## 6. LangGraph Integration

### 6.1 Graph Template Registry

```python
class GraphTemplateRegistry:
    """Registry for compiled graph templates"""

    def __init__(self):
        self._templates: dict[str, CompiledGraph] = {}

    def register(self, name: str, graph: CompiledGraph) -> None:
        self._templates[name] = graph

    def get(self, name: str) -> Optional[CompiledGraph]:
        return self._templates.get(name)

    def has(self, name: str) -> bool:
        return name in self._templates
```

### 6.2 Default Graph Builder

```python
from langgraph.prebuilt import create_react_agent
from typing import TypedDict

class SubagentState(TypedDict):
    """State for subagent graph"""
    messages: list[BaseMessage]
    turn_count: int


def create_default_subagent_graph(
    llm,
    tools: list,
    max_turns: int = 10,
) -> CompiledGraph:
    """
    Create default ReAct-style subagent graph.

    Pattern: Think -> Act -> Observe -> Repeat until complete
    """
    graph = create_react_agent(
        llm,
        tools=tools,
    )
    return graph
```

## 7. Subagent Executor

```python
class SubagentExecutor:
    """Executes individual subagent tasks"""

    def __init__(
        self,
        llm,
        tools: list,
        event_stream: SubagentEventStream,
        graph_registry: GraphTemplateRegistry,
    ):
        self._llm = llm
        self._tools = tools
        self._event_stream = event_stream
        self._graph_registry = graph_registry

    async def execute(self, task: SubagentTask) -> SubagentResult:
        """Execute a subagent task"""
        start_time = datetime.now()

        try:
            # Publish start event
            await self._publish_event(task, "task_started", {"prompt": task.prompt})

            # Get or create graph
            graph = self._get_graph(task.graph_template)

            # Execute with timeout
            result = await asyncio.wait_for(
                graph.ainvoke({
                    "messages": [HumanMessage(content=task.prompt)]
                }),
                timeout=task.timeout,
            )

            # Extract output
            output = result["messages"][-1].content

            # Publish completion event
            await self._publish_event(task, "task_completed", {"output": output})

            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.COMPLETED,
                output=output,
                turns_used=len(result["messages"]) // 2,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except asyncio.TimeoutError:
            await self._publish_event(task, "task_failed", {
                "error": f"Timeout after {task.timeout}s"
            })
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.TIMEOUT,
                error=f"Task timed out after {task.timeout} seconds",
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

    def _get_graph(self, template_name: str) -> CompiledGraph:
        """Get graph from registry or create default"""
        graph = self._graph_registry.get(template_name)
        if graph is None:
            graph = create_default_subagent_graph(self._llm, self._tools)
            self._graph_registry.register(template_name, graph)
        return graph

    async def _publish_event(
        self, task: SubagentTask, event_type: str, data: dict
    ) -> None:
        await self._event_stream.publish(SubagentEvent(
            event_type=event_type,
            task_id=task.task_id,
            thread_id=task.thread_id,
            data=data,
        ))
```

## 8. Global Subagent Manager

### 8.1 Thread Context

```python
@dataclass
class ThreadContext:
    """Context for a single conversation thread"""

    thread_id: str
    max_concurrent: int
    _limiter: ConcurrencyLimiter = field(init=False)
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _results: dict[str, SubagentResult] = field(default_factory=dict)
    _created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self._limiter = ConcurrencyLimiter(self.max_concurrent)

    @property
    def active_count(self) -> int:
        return self._limiter.active_count

    @property
    def total_tasks(self) -> int:
        return len(self._tasks)

    def register_task(self, task_id: str, async_task: asyncio.Task) -> None:
        self._tasks[task_id] = async_task

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
```

### 8.2 Global Manager

```python
class GlobalSubagentManager:
    """Singleton manager for all subagent operations"""

    _instance: Optional["GlobalSubagentManager"] = None

    def __init__(self, config: SubagentConfig):
        self._config = config
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._event_stream = SubagentEventStream(
            max_queue_size=config.event_queue_size
        )
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

    async def spawn(self, task: SubagentTask) -> str:
        """Spawn a new subagent task"""
        async with self._lock:
            ctx = await self._get_or_create_context(task.thread_id)

        async def run_with_limiter():
            async with self._limiter.acquire(task.thread_id):
                result = await self._executor.execute(task)
                ctx.store_result(task.task_id, result)
                return result

        async_task = asyncio.create_task(run_with_limiter())
        ctx.register_task(task.task_id, async_task)

        return task.task_id

    async def cancel(self, thread_id: str, task_id: str) -> bool:
        """Cancel a running task"""
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return False

            if task_id not in ctx._tasks:
                return False

            async_task = ctx._tasks[task_id]
            if not async_task.done():
                async_task.cancel()
                return True
            return False

    async def get_status(
        self, thread_id: str, task_id: str
    ) -> Optional[SubagentStatus]:
        """Get task status"""
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return None
            return ctx.get_task_status(task_id)

    async def get_result(
        self, thread_id: str, task_id: str
    ) -> Optional[SubagentResult]:
        """Get task result"""
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return None
            return ctx.get_result(task_id)

    async def subscribe_events(
        self, thread_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Subscribe to SSE event stream"""
        async for event_str in self._event_stream.subscribe(thread_id):
            yield event_str

    async def cleanup_thread(self, thread_id: str) -> None:
        """Clean up all resources for a thread"""
        async with self._lock:
            if thread_id not in self._threads:
                return

            ctx = self._threads[thread_id]

            # Cancel all active tasks
            for task in ctx._tasks.values():
                if not task.done():
                    task.cancel()

            # Remove thread context
            del self._threads[thread_id]

            # Clean up limiter
            self._limiter.cleanup_thread(thread_id)

    async def _get_or_create_context(self, thread_id: str) -> ThreadContext:
        if thread_id not in self._threads:
            self._threads[thread_id] = ThreadContext(
                thread_id=thread_id,
                max_concurrent=self._config.per_thread_max_concurrent,
            )
        return self._threads[thread_id]
```

## 9. Configuration

```python
from pydantic import BaseSettings, Field
from typing import Any

class SubagentConfig(BaseSettings):
    """Subagent system configuration"""

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

## 10. API Routes

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
):
    """Spawn a new subagent task"""
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
):
    """Get task status and result"""
    status = await manager.get_status(thread_id, task_id)
    if status is None:
        raise HTTPException(404, "Task not found")

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
):
    """Cancel a running task"""
    success = await manager.cancel(thread_id, task_id)
    return CancelResponse(success=success)


@router.get("/events")
async def subscribe_events(
    thread_id: Optional[str] = None,
    manager: GlobalSubagentManager = Depends(get_manager),
):
    """SSE endpoint for real-time event streaming"""
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

## 11. Phase 1 Integration

```python
# In application startup
from src.sandbox import create_sandbox_tools
from src.subagents import GlobalSubagentManager, SubagentConfig

async def startup_event():
    config = SubagentConfig(
        default_tools=create_sandbox_tools(),
    )
    GlobalSubagentManager.initialize(config)
```

## 12. Implementation Tasks

| Task | Files | Description |
|------|-------|-------------|
| 1 | `models.py`, `config.py` | Data models and configuration |
| 2 | `limiter.py` | Dual-layer concurrency limiter |
| 3 | `events.py` | SSE event stream |
| 4 | `graph.py` | LangGraph graph builder |
| 5 | `executor.py` | Subagent executor |
| 6 | `manager.py` | Global manager and thread context |
| 7 | `api/subagents.py` | API routes |
| 8 | Integration tests | End-to-end validation |

## 13. Testing Strategy

### Unit Tests
- `test_models.py`: Model serialization and validation
- `test_limiter.py`: Concurrency control behavior
- `test_events.py`: Event stream subscription and publishing
- `test_graph.py`: Graph creation and compilation
- `test_executor.py`: Task execution, timeout, cancellation

### Integration Tests
- `test_manager.py`: Full manager lifecycle
- `test_api.py`: API endpoints with mock manager

### Concurrency Tests
- Multiple tasks spawning simultaneously
- Global and per-thread limit enforcement
- Task cancellation during execution

## 14. Dependencies

```
langgraph>=0.2.0
langchain-core>=0.3.0
```

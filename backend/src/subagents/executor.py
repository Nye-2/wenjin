"""SubagentExecutor - background task execution with thread pools."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from langchain_core.tools import BaseTool

from src.subagents.events import EventStream, SubagentEvent, SubagentEventType
from src.subagents.registry import SubagentConfig


class SubagentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentResult:
    task_id: str
    status: SubagentStatus = SubagentStatus.PENDING
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ai_messages: list[dict[str, Any]] = field(default_factory=list)


# Global thread pools
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-scheduler-")
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec-")

# Background task tracking
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()

# Event streaming support
_event_streams: dict[str, EventStream] = {}
_event_streams_lock = threading.Lock()


def register_event_stream(task_id: str, stream: EventStream) -> None:
    """Register an event stream for a task."""
    with _event_streams_lock:
        _event_streams[task_id] = stream


def unregister_event_stream(task_id: str) -> None:
    """Unregister an event stream."""
    with _event_streams_lock:
        _event_streams.pop(task_id, None)


def get_event_stream(task_id: str) -> EventStream | None:
    """Get the event stream for a task."""
    with _event_streams_lock:
        return _event_streams.get(task_id)


def get_background_task_result(task_id: str) -> SubagentResult | None:
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def list_background_tasks() -> list[SubagentResult]:
    with _background_tasks_lock:
        return list(_background_tasks.values())


def _filter_tools(
    all_tools: list[BaseTool],
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list[BaseTool]:
    """Filter tools by allowlist/denylist."""
    result = list(all_tools)
    if allowed:
        allowed_set = set(allowed)
        result = [t for t in result if t.name in allowed_set]
    if disallowed:
        disallowed_set = set(disallowed)
        result = [t for t in result if t.name not in disallowed_set]
    return result


class SubagentExecutor:
    """Executes subagent tasks with optional background threading."""

    def __init__(
        self,
        config: SubagentConfig,
        tools: list[BaseTool],
        parent_model: str | None = None,
        thread_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.config = config
        self.parent_model = parent_model
        self.thread_id = thread_id
        self.trace_id = trace_id or str(uuid.uuid4())[:12]
        self.tools = _filter_tools(
            tools,
            list(config.allowed_tools) if config.allowed_tools else None,
            list(config.disallowed_tools) if config.disallowed_tools else None,
        )

    def _create_agent(self):
        """Create a lightweight agent for subagent execution."""
        from src.models.factory import create_chat_model
        model_name = self.parent_model or "gpt-4o"
        model = create_chat_model(model_name, thinking_enabled=False)

        from langgraph.prebuilt import create_react_agent
        return create_react_agent(
            model,
            self.tools,
            prompt=self.config.system_prompt,
        )

    def execute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
        stream: EventStream | None = None,
    ) -> SubagentResult:
        """Synchronous execution with optional event streaming."""
        if result_holder is None:
            result_holder = SubagentResult(task_id=str(uuid.uuid4())[:12])

        # Emit STARTED event
        if stream:
            stream.push(SubagentEvent(
                type=SubagentEventType.STARTED,
                task_id=result_holder.task_id,
                subagent_type=self.config.name,
                message=f"Task started: {task[:50]}...",
            ))

        result_holder.status = SubagentStatus.RUNNING
        result_holder.started_at = datetime.now(UTC)

        # Emit RUNNING event
        if stream:
            stream.push(SubagentEvent(
                type=SubagentEventType.RUNNING,
                task_id=result_holder.task_id,
                subagent_type=self.config.name,
                message="Agent execution in progress",
            ))

        try:
            agent = self._create_agent()
            response = agent.invoke({"messages": [("human", task)]})
            messages = response.get("messages", [])
            last_msg = messages[-1] if messages else None
            result_holder.result = getattr(last_msg, "content", str(last_msg)) if last_msg else ""
            result_holder.status = SubagentStatus.COMPLETED

            # Emit COMPLETED event
            if stream:
                stream.push(SubagentEvent(
                    type=SubagentEventType.COMPLETED,
                    task_id=result_holder.task_id,
                    subagent_type=self.config.name,
                    message="Task completed successfully",
                    data={"result_preview": result_holder.result[:100] if result_holder.result else None},
                ))
        except Exception as e:
            result_holder.error = str(e)
            result_holder.status = SubagentStatus.FAILED

            # Emit FAILED event
            if stream:
                stream.push(SubagentEvent(
                    type=SubagentEventType.FAILED,
                    task_id=result_holder.task_id,
                    subagent_type=self.config.name,
                    message=f"Task failed: {str(e)[:100]}",
                    data={"error": str(e)},
                ))
        finally:
            result_holder.completed_at = datetime.now(UTC)

        return result_holder

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Background execution (returns task_id immediately)."""
        task_id = task_id or str(uuid.uuid4())[:12]
        result = SubagentResult(task_id=task_id)
        stream = EventStream()

        with _background_tasks_lock:
            _background_tasks[task_id] = result
        with _event_streams_lock:
            _event_streams[task_id] = stream

        def _run():
            try:
                self.execute(task, result_holder=result, stream=stream)
            finally:
                # Cleanup: close stream and remove from global dictionaries
                stream.close()
                unregister_event_stream(task_id)
                with _background_tasks_lock:
                    _background_tasks.pop(task_id, None)

        _execution_pool.submit(_run)
        return task_id

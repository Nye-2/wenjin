"""Global subagent manager and thread context."""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .config import SubagentConfig
from .events import SubagentEventStream
from .graph import GraphTemplateRegistry, create_default_subagent_graph
from .limiter import DualLayerLimiter
from .models import SubagentResult, SubagentStatus, SubagentTask

logger = logging.getLogger(__name__)


class SubagentAccessError(PermissionError):
    """Raised when a user tries to access another user's subagent thread."""


@dataclass
class ThreadContext:
    """Context for a single conversation thread."""

    thread_id: str
    max_concurrent: int
    owner_user_id: str | None = None
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _task_defs: dict[str, SubagentTask] = field(default_factory=dict)
    _results: dict[str, SubagentResult] = field(default_factory=dict)
    _active_task_ids: set[str] = field(default_factory=set)

    @property
    def total_tasks(self) -> int:
        """Get total number of tasks."""
        return len(self._tasks)

    def store_result(self, task_id: str, result: SubagentResult) -> None:
        """Store a task result."""
        self._results[task_id] = result

    def store_task_definition(self, task: SubagentTask) -> None:
        """Keep the submitted task definition for timeline and inspection use cases."""
        self._task_defs[task.task_id] = task

    @property
    def active_task_count(self) -> int:
        """Count currently running tasks for the thread."""
        return len(self._active_task_ids)

    def mark_task_active(self, task_id: str) -> None:
        """Mark a task as active for UI-facing status tracking."""
        self._active_task_ids.add(task_id)

    def mark_task_finished(self, task_id: str) -> None:
        """Remove a task from the active set after it terminates."""
        self._active_task_ids.discard(task_id)

    def get_result(self, task_id: str) -> SubagentResult | None:
        """Get a stored result."""
        return self._results.get(task_id)

    def get_task_status(self, task_id: str) -> SubagentStatus | None:
        """Get the status of a task."""
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
    _init_lock = threading.Lock()  # Class-level lock for singleton initialization

    def __init__(self, config: SubagentConfig):
        """Initialize the manager.

        Args:
            config: Subagent configuration.
        """
        self._config = config
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._event_stream = SubagentEventStream(max_queue_size=config.event_queue_size)
        self._graph_registry = GraphTemplateRegistry()
        self._threads: dict[str, ThreadContext] = {}
        self._llm = config.llm
        self._tools = config.default_tools
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "GlobalSubagentManager":
        """Get the singleton instance.

        Returns:
            The GlobalSubagentManager instance.

        Raises:
            RuntimeError: If manager not initialized.
        """
        if cls._instance is None:
            raise RuntimeError("GlobalSubagentManager not initialized")
        return cls._instance

    @classmethod
    def initialize(cls, config: SubagentConfig) -> "GlobalSubagentManager":
        """Initialize the singleton instance.

        Args:
            config: Subagent configuration.

        Returns:
            The initialized GlobalSubagentManager.

        Raises:
            RuntimeError: If already initialized.
        """
        with cls._init_lock:
            if cls._instance is not None:
                raise RuntimeError("GlobalSubagentManager already initialized")
            cls._instance = cls(config)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    async def spawn(self, task: SubagentTask) -> str:
        """Spawn a new subagent task.

        Args:
            task: The task to spawn.

        Returns:
            The task ID.
        """
        logger.info(f"Spawning subagent task {task.task_id} for thread {task.thread_id}")
        owner_user_id = self._get_task_owner_user_id(task)
        async with self._lock:
            ctx = self._get_or_create_context(task.thread_id, owner_user_id)

        async def run_with_limiter():
            terminal_status = "completed"
            try:
                async with self._limiter.acquire(task.thread_id):
                    logger.debug(f"Executing task {task.task_id}")
                    result = await self._execute_task(task)
                    ctx.store_result(task.task_id, result)
                    terminal_status = self._map_result_status(result.status)
                    logger.info(
                        f"Task {task.task_id} completed with status {result.status}"
                    )
                    return result
            except Exception:
                terminal_status = "failed"
                raise
            finally:
                ctx.mark_task_finished(task.task_id)
                await self._sync_thread_agent_status(
                    task.thread_id,
                    status="running" if ctx.active_task_count > 0 else terminal_status,
                    subagent_count=ctx.active_task_count,
                )

        async_task = asyncio.create_task(run_with_limiter())
        ctx._tasks[task.task_id] = async_task
        ctx.store_task_definition(task)
        ctx.mark_task_active(task.task_id)
        await self._sync_thread_agent_status(
            task.thread_id,
            status="running",
            subagent_count=ctx.active_task_count,
        )
        return task.task_id

    async def _execute_task(self, task: SubagentTask) -> SubagentResult:
        """Execute a subagent task using LangGraph.

        Args:
            task: The task to execute.

        Returns:
            Execution result.
        """
        from langchain_core.messages import HumanMessage

        start_time = datetime.now()

        try:
            # Publish task started event
            from .models import SubagentEvent
            await self._event_stream.publish(SubagentEvent(
                event_type="task_started",
                task_id=task.task_id,
                thread_id=task.thread_id,
                data={"prompt": task.prompt},
                timestamp=datetime.now(),
            ))

            # Get or create graph
            graph = self._graph_registry.get(task.graph_template)
            if graph is None:
                graph = create_default_subagent_graph(self._llm, self._tools, task.max_turns)
                self._graph_registry.register(task.graph_template, graph)

            # Execute with timeout
            result = await asyncio.wait_for(
                graph.ainvoke({"messages": [HumanMessage(content=task.prompt)]}),
                timeout=task.timeout,
            )

            messages = result.get("messages", [])
            output = messages[-1].content if messages else ""

            # Publish task completed event
            await self._event_stream.publish(SubagentEvent(
                event_type="task_completed",
                task_id=task.task_id,
                thread_id=task.thread_id,
                data={"output": output},
                timestamp=datetime.now(),
            ))

            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.COMPLETED,
                output=output,
                error=None,
                turns_used=len(messages) // 2,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except TimeoutError:
            from .models import SubagentEvent
            await self._event_stream.publish(SubagentEvent(
                event_type="task_failed",
                task_id=task.task_id,
                thread_id=task.thread_id,
                data={"error": "Timeout"},
                timestamp=datetime.now(),
            ))
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.TIMED_OUT,
                output=None,
                error=f"Timed out after {task.timeout}s",
                duration_seconds=task.timeout,
            )

        except asyncio.CancelledError:
            from .models import SubagentEvent
            await self._event_stream.publish(SubagentEvent(
                event_type="task_cancelled",
                task_id=task.task_id,
                thread_id=task.thread_id,
                data={},
                timestamp=datetime.now(),
            ))
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.CANCELLED,
                output=None,
                error=None,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            from .models import SubagentEvent
            await self._event_stream.publish(SubagentEvent(
                event_type="task_failed",
                task_id=task.task_id,
                thread_id=task.thread_id,
                data={"error": str(e)},
                timestamp=datetime.now(),
            ))
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.FAILED,
                output=None,
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    async def cancel(
        self,
        thread_id: str,
        task_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Cancel a running task.

        Args:
            thread_id: Thread ID.
            task_id: Task ID.

        Returns:
            True if cancelled, False if not found or already done.
        """
        logger.info(f"Attempting to cancel task {task_id} in thread {thread_id}")
        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
            if not ctx or task_id not in ctx._tasks:
                logger.warning(f"Task {task_id} not found for cancellation")
                return False
            async_task = ctx._tasks[task_id]
            if not async_task.done():
                async_task.cancel()
                logger.info(f"Successfully cancelled task {task_id}")
                return True
            logger.debug(f"Task {task_id} already done, cannot cancel")
            return False

    async def get_status(
        self,
        thread_id: str,
        task_id: str,
        user_id: str | None = None,
    ) -> SubagentStatus | None:
        """Get the status of a task.

        Args:
            thread_id: Thread ID.
            task_id: Task ID.

        Returns:
            Task status or None if not found.
        """
        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
            if not ctx:
                return None
            return ctx.get_task_status(task_id)

    async def get_result(
        self,
        thread_id: str,
        task_id: str,
        user_id: str | None = None,
    ) -> SubagentResult | None:
        """Get the result of a completed task.

        Args:
            thread_id: Thread ID.
            task_id: Task ID.

        Returns:
            Task result or None if not found.
        """
        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
            if not ctx:
                return None
            return ctx.get_result(task_id)

    async def list_thread_tasks(
        self,
        thread_id: str,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List recent subagent tasks for a thread."""
        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
            if not ctx:
                return []

            ordered_tasks = sorted(
                ctx._task_defs.values(),
                key=lambda task: task.created_at,
                reverse=True,
            )[:limit]

            items: list[dict] = []
            for task in ordered_tasks:
                result = ctx.get_result(task.task_id)
                status = ctx.get_task_status(task.task_id)
                items.append(
                    {
                        "task_id": task.task_id,
                        "thread_id": task.thread_id,
                        "prompt": task.prompt,
                        "created_at": task.created_at,
                        "status": status.value if isinstance(status, SubagentStatus) else str(status or "pending"),
                        "subagent_type": task.metadata.get("subagent_type"),
                        "error": result.error if result else None,
                        "output_preview": self._truncate_preview(result.output if result else None),
                    }
                )
            return items

    async def subscribe_events(
        self,
        thread_id: str | None = None,
        user_id: str | None = None,
    ):
        """Subscribe to event stream.

        Args:
            thread_id: Optional thread ID to filter events.

        Yields:
            SSE-formatted event strings.
        """
        if thread_id is not None:
            async with self._lock:
                ctx = self._get_accessible_context(thread_id, user_id)
                if ctx is None:
                    raise SubagentAccessError("Thread not found")

        async for event_str in self._event_stream.subscribe(thread_id):
            if thread_id is None and user_id is not None:
                event_thread_id = self._extract_thread_id_from_sse(event_str)
                if event_thread_id is None:
                    continue
                async with self._lock:
                    ctx = self._get_accessible_context(event_thread_id, user_id)
                    if ctx is None:
                        continue
            yield event_str

    async def check_thread_access(self, thread_id: str, user_id: str | None) -> bool:
        """Check whether a user can access a given thread."""
        async with self._lock:
            return self._get_accessible_context(thread_id, user_id) is not None

    async def cleanup_thread(self, thread_id: str) -> None:
        """Clean up a thread and cancel its tasks.

        Args:
            thread_id: Thread ID to clean up.
        """
        logger.info(f"Cleaning up thread {thread_id}")
        async with self._lock:
            if thread_id not in self._threads:
                logger.debug(f"Thread {thread_id} not found for cleanup")
                return
            ctx = self._threads[thread_id]
            cancelled_count = 0
            for task in ctx._tasks.values():
                if not task.done():
                    task.cancel()
                    cancelled_count += 1
            del self._threads[thread_id]
            await self._limiter.cleanup_thread(thread_id)
            logger.info(
                f"Cleaned up thread {thread_id}, cancelled {cancelled_count} tasks"
            )

    async def _sync_thread_agent_status(
        self,
        thread_id: str,
        *,
        status: str,
        subagent_count: int,
    ) -> None:
        """Mirror subagent activity into the thread-scoped status cache."""
        try:
            from src.academic.cache.redis_client import redis_client

            if redis_client._client is None:
                return
            await redis_client.set_agent_status(
                thread_id,
                status,
                subagent_count=subagent_count,
            )
        except Exception:
            logger.debug(
                "Failed to sync subagent status for thread %s",
                thread_id,
                exc_info=True,
            )

    def _get_or_create_context(
        self,
        thread_id: str,
        owner_user_id: str | None = None,
    ) -> ThreadContext:
        """Get or create a thread context.

        Args:
            thread_id: Thread ID.

        Returns:
            Thread context.
        """
        if thread_id not in self._threads:
            self._threads[thread_id] = ThreadContext(
                thread_id=thread_id,
                max_concurrent=self._config.per_thread_max_concurrent,
                owner_user_id=owner_user_id,
            )
            return self._threads[thread_id]

        ctx = self._threads[thread_id]
        if owner_user_id and ctx.owner_user_id and ctx.owner_user_id != owner_user_id:
            raise SubagentAccessError("Thread not found")
        if owner_user_id and ctx.owner_user_id is None:
            ctx.owner_user_id = owner_user_id
        return ctx

    def _get_accessible_context(
        self,
        thread_id: str,
        user_id: str | None,
    ) -> ThreadContext | None:
        """Get a thread context if the user is allowed to access it."""
        ctx = self._threads.get(thread_id)
        if ctx is None:
            return None
        if user_id and ctx.owner_user_id and ctx.owner_user_id != user_id:
            return None
        return ctx

    @staticmethod
    def _get_task_owner_user_id(task: SubagentTask) -> str | None:
        """Extract owner user id from task metadata."""
        user_id = task.metadata.get("user_id")
        return str(user_id) if user_id is not None else None

    @staticmethod
    def _extract_thread_id_from_sse(event_str: str) -> str | None:
        """Extract thread_id from an SSE event payload."""
        for line in event_str.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            thread_id = payload.get("thread_id")
            return str(thread_id) if thread_id is not None else None
        return None

    @staticmethod
    def _map_result_status(status: SubagentStatus) -> str:
        """Normalize subagent terminal states into UI-facing thread states."""
        if status == SubagentStatus.COMPLETED:
            return "completed"
        if status in {SubagentStatus.CANCELLED, SubagentStatus.FAILED, SubagentStatus.TIMED_OUT}:
            return "failed"
        return "running"

    @staticmethod
    def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
        """Collapse task output into a compact single-line preview."""
        normalized = " ".join((content or "").split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

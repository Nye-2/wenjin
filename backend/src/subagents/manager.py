"""Global subagent manager and thread context."""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .config import SubagentConfig
from .events import SubagentEventStream
from .graph import GraphTemplateRegistry, create_default_subagent_graph
from .limiter import DualLayerLimiter
from .models import SubagentResult, SubagentStatus, SubagentTask


logger = logging.getLogger(__name__)


@dataclass
class ThreadContext:
    """Context for a single conversation thread."""

    thread_id: str
    max_concurrent: int
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _results: dict[str, SubagentResult] = field(default_factory=dict)

    @property
    def total_tasks(self) -> int:
        """Get total number of tasks."""
        return len(self._tasks)

    def store_result(self, task_id: str, result: SubagentResult) -> None:
        """Store a task result."""
        self._results[task_id] = result

    def get_result(self, task_id: str) -> Optional[SubagentResult]:
        """Get a stored result."""
        return self._results.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[SubagentStatus]:
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
        async with self._lock:
            ctx = self._get_or_create_context(task.thread_id)

        async def run_with_limiter():
            async with self._limiter.acquire(task.thread_id):
                logger.debug(f"Executing task {task.task_id}")
                result = await self._execute_task(task)
                ctx.store_result(task.task_id, result)
                logger.info(
                    f"Task {task.task_id} completed with status {result.status}"
                )
                return result

        async_task = asyncio.create_task(run_with_limiter())
        ctx._tasks[task.task_id] = async_task
        return task.task_id

    async def _execute_task(self, task: SubagentTask) -> SubagentResult:
        """Execute a subagent task using LangGraph.

        Args:
            task: The task to execute.

        Returns:
            Execution result.
        """
        from datetime import datetime
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

        except asyncio.TimeoutError:
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

    async def cancel(self, thread_id: str, task_id: str) -> bool:
        """Cancel a running task.

        Args:
            thread_id: Thread ID.
            task_id: Task ID.

        Returns:
            True if cancelled, False if not found or already done.
        """
        logger.info(f"Attempting to cancel task {task_id} in thread {thread_id}")
        async with self._lock:
            ctx = self._threads.get(thread_id)
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

    async def get_status(self, thread_id: str, task_id: str) -> Optional[SubagentStatus]:
        """Get the status of a task.

        Args:
            thread_id: Thread ID.
            task_id: Task ID.

        Returns:
            Task status or None if not found.
        """
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return None
            return ctx.get_task_status(task_id)

    async def get_result(self, thread_id: str, task_id: str) -> Optional[SubagentResult]:
        """Get the result of a completed task.

        Args:
            thread_id: Thread ID.
            task_id: Task ID.

        Returns:
            Task result or None if not found.
        """
        async with self._lock:
            ctx = self._threads.get(thread_id)
            if not ctx:
                return None
            return ctx.get_result(task_id)

    async def subscribe_events(self, thread_id: Optional[str] = None):
        """Subscribe to event stream.

        Args:
            thread_id: Optional thread ID to filter events.

        Yields:
            SSE-formatted event strings.
        """
        async for event_str in self._event_stream.subscribe(thread_id):
            yield event_str

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
            self._limiter.cleanup_thread(thread_id)
            logger.info(
                f"Cleaned up thread {thread_id}, cancelled {cancelled_count} tasks"
            )

    def _get_or_create_context(self, thread_id: str) -> ThreadContext:
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
            )
        return self._threads[thread_id]

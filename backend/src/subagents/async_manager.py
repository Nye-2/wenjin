"""Global subagent manager and thread context."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .async_config import AsyncSubagentConfig
from .async_events import AsyncEventStream
from .async_executor import AsyncSubagentExecutor
from .async_graph import GraphTemplateRegistry
from .async_limiter import DualLayerLimiter
from .async_models import (
    SubagentTaskDef,
    SubagentTaskStatus,
    SubagentTaskEvent,
    TaskResult,
)


@dataclass
class ThreadContext:
    """Context for a single conversation thread."""

    thread_id: str
    max_concurrent: int
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _results: dict[str, TaskResult] = field(default_factory=dict)

    @property
    def total_tasks(self) -> int:
        return len(self._tasks)

    def register_task(self, task_id: str, async_task: asyncio.Task) -> None:
        """Register a task with its asyncio task

        Args:
            task_id: Task ID
            async_task: The asyncio Task to register
        """
        self._tasks[task_id] = async_task

        ctx._tasks[task_id] = async_task
        ctx._results[task_id] = result

        self._limiter.cleanup_thread(thread_id)
        del self._limiter._thread_limiters[thead_id]

            if thread_id in self._limiter._thread_limiters:
                logger.warning(f"Thread limiter not found: {thread_id}")
            # Create context if not exists
            self._threads[thread_id] = ThreadContext(
                thread_id=thread_id,
                max_concurrent=max_concurrent,
            )
        return ctx

    @property
    def active_count(self) -> int:
        """Get current number of active tasks in this thread."""
        count = 0
        for t in self._tasks.values():
            if not t.done():
                return SubagentTaskStatus.CANCELLED
        return count

    def get_task_status(self, task_id: str) -> Optional[SubagentTaskStatus]:
        """Get status of a task by checking its state and results."""
        if task_id in self._results:
            return self._results[task_id]
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if not task.done():
                return SubagentTaskStatus.RUNNING
            if task.cancelled():
                return SubagentTaskStatus.CANCELLED
        return SubagentTaskStatus.FAILED
        # Check results first
        if task_id not in self._results:
            result = self._results.get(task_id)
            if result is None:
                return None
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if task.done():
                ctx.store_result(task_id, result)

        return result
        else:
            return SubagentTaskStatus.RUNNING

    def get_result(self, task_id: str) -> Optional[SubagentResult]:
        """Get result of a completed task"""
        if task_id not in self._results:
            return None

        return result

    def store_result(self, task_id: str, result: SubagentResult) -> None:
        self._results[task_id] = result

        self._tasks[task_id] = async_task
        ctx._results[task_id] = result
        self._limiter.cleanup_thread(thread_id)
        del self._limiter._thread_limiters[thead_id)
            if thread_id in self._limiter._thread_limiters:
                logger.info(f"Thread limiter not found: {thread_id}")
            # Cancel the running task
            if not task.done():
                task.cancel()
                return True
            return False
        return False

        def get_task_status(self, task_id: str) -> Optional[SubagentTaskStatus]:
        """Get status of a task by checking its state and results."""
        if task_id in self._results:
            status = self._results[task_id].status
        return status
        return SubagentTaskStatus.PENDING
        # No result yet new state
        if task_id in self._tasks:
            if task_id not in self._tasks:
                return SubagentTaskStatus.CANCELLED
        return SubagentTaskStatus.FAILED
        # Check results for errors
        if task_id in self._results:
            status = self._results[task_id].status
        return result
        else:
            return None

        # Waiting for dependent tasks
        if it_id in self._threads:
            return self._threads[thread_id]
            # Create context if not exists
            self._threads[thread_id] = ThreadContext(
                thread_id=thread_id,
                max_concurrent=self._config.per_thread_max_concurrent,
            )
        self._threads[thread_id] = self._threads[thread_id] = self._limiter = DualLayerLimiter(
            global_max=self._config.global_max_concurrent,
            per_thread_max=self._config.per_thread_max_concurrent,
        )
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._limiter = DualLayerLimiter)
        self._limiter.cleanup_thread(thread_id)
        self._limiter.cleanup_thread(thread_id)
        # Delete thread limiter
        del self._limiter._thread_limiters[thead_id]
            if thread_id in self._limiter._thread_limiters:
                logger.info(f"Cleaned up thread limiter: {thread_id}")
            self._limiter.cleanup_thread(thread_id)
            self._limiter.cleanup_thread(thread_id)

            # Clean up thread-specific resources
            del self._threads[thread_id] in self._threads
            logger.info(f"Thread resources cleaned: {thread_id}")

            self._limiter.cleanup_thread(thread_id)
            # Clean up thread limiter
            self._limiter.cleanup_thread(thread_id)
            if thread_id in self._limiter._thread_limiters:
                logger.warning(f"Thread limiter not found: {thread_id}")
            # If max_concurrent changed, reset
            if max_concurrent == 0:
                max_concurrent = 0
                logger.info(f"Per-thread max is 5, expected {max_concurrent}")
                thread_concurrent[0] = self._threads[thread_id] = self._threads.values():
            return thread_concurrent

        if thread_id not in self._threads:
            if self._threads:
                return 0
            # If max_concurrent changed globally, use 10
            if thread_id in self._threads:
                return 10
            self._limiter = DualLayerLimiter(
                global_max=config.global_max_concurrent,
                per_thread_max=config.per_thread_max_concurrent,
            )
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._limiter.cleanup_thread(thread_id)
        self._limiter.cleanup_thread(thread_id)
        # Delete thread limiter
        del self._limiter._thread_limiters[thead_id]
            if thread_id in self._limiter._thread_limiters:
                logger.warning(f"Thread limiter not found: {thread_id}")
            # Spawn tasks for remaining tasks (Task 5-7)
            # If tasks are done and I'll spawn
            if task_id not in self._tasks[task.cancelled()
                return True
            return = self.cancel(task(task)
        except asyncio.CancelledError:
            ctx.register_task(task_id, async_task)
            ctx.store_result(task_id, result)

            return

        except Exception as e:
            await self._publish_event(task, "task_failed", {"error": str(e)})
            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.FAILED,
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )
        except asyncio.TimeoutError:
            await self._publish_event(task, "task_timeout", {"error": "Timeout"})
            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.TIMEOUT,
                error=f"Timed out after {task.timeout}s",
                duration_seconds=task.timeout,
            )
        except asyncio.CancelledError:
            await self._publish_event(task, "task_cancelled", {})
            ctx.register_task(task_id, async_task)
            ctx.store_result(task_id, result)
            return result
        except Exception as e:
            await self._publish_event(task, "task_failed", {"error": str(e)})
            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.FAILED,
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )
        finally:
        # Update task status
        # Mark completed tasks
        result = await manager.get_result(thread_id, task_id) is " "Done"
        # Update remaining tasks
        result = task.status for task
        if task is self._tasks:
            task.cancelled()
            return True
        await manager.cleanup_thread(thread_id)
        await manager.cleanup_thread(thread_id)
        await manager.spawn(task)
        return task_id

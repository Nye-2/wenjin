"""Global subagent manager and thread context."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.services.thread_billing import (
    extract_persisted_metadata_usage,
    extract_usage_from_agent_result,
)
from src.services.workspace_activity_contracts import (
    build_subagent_activity_item,
    serialize_activity_item,
)

from .config import SubagentConfig
from .graph import (
    GraphTemplateRegistry,
    create_academic_agent_graph,
    create_default_subagent_graph,
)
from .limiter import DualLayerLimiter
from .models import SubagentResult, SubagentStatus, SubagentTask

if TYPE_CHECKING:
    from .parallel import ParallelExecutor

logger = logging.getLogger(__name__)


class SubagentAccessError(PermissionError):
    """Raised when a user tries to access another user's subagent thread."""


@dataclass
class ThreadContext:
    """Context for a single conversation thread."""

    thread_id: str
    max_concurrent: int
    owner_user_id: str | None = None
    workspace_id: str | None = None
    _tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
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

    _instance: GlobalSubagentManager | None = None
    _init_lock = threading.Lock()  # Class-level lock for singleton initialization

    def __init__(self, config: SubagentConfig) -> None:
        """Initialize the manager.

        Args:
            config: Subagent configuration.
        """
        self._config = config
        self._limiter = DualLayerLimiter(
            global_max=config.global_max_concurrent,
            per_thread_max=config.per_thread_max_concurrent,
        )
        self._graph_registry = GraphTemplateRegistry()
        self._threads: dict[str, ThreadContext] = {}
        self._llm = config.llm
        self._tools = config.default_tools
        self._lock = asyncio.Lock()

        # Spec §6.1 — registry mapping run_id (= execution_session_id) to the
        # ParallelExecutor handling that run. Populated by NativeWenjinAgentHarness
        # while a session is in flight; consumed by the runs router (Plan 1 Task 10)
        # to deliver pause/resume/cancel to the right executor.
        self._executors: dict[str, ParallelExecutor] = {}

    def register_executor(self, run_id: str, executor: ParallelExecutor) -> None:
        """Register an executor under run_id for the duration of a run."""
        self._executors[run_id] = executor

    def unregister_executor(self, run_id: str) -> None:
        """Remove an executor from the registry. No-op if unknown."""
        self._executors.pop(run_id, None)

    def pause_run(self, run_id: str) -> None:
        """Pause the executor for run_id at its next phase boundary. No-op if unknown."""
        ex = self._executors.get(run_id)
        if ex is not None:
            ex.pause()

    def resume_run(self, run_id: str) -> None:
        """Resume a paused executor. No-op if unknown."""
        ex = self._executors.get(run_id)
        if ex is not None:
            ex.resume()

    def cancel_run(self, run_id: str) -> None:
        """Cancel and unregister. Terminal — once cancelled, the run is done."""
        ex = self._executors.pop(run_id, None)
        if ex is not None:
            ex.cancel()

    def _resolve_task_tools(self, task: SubagentTask) -> list[Any]:
        """Resolve the task's requested tool names against the configured tool pool."""
        if not task.tools:
            return self._tools

        if isinstance(self._tools, dict):
            return [self._tools[name] for name in task.tools if name in self._tools]

        available_tools = {
            getattr(tool, "name", None): tool
            for tool in self._tools
            if getattr(tool, "name", None)
        }
        return [available_tools[name] for name in task.tools if name in available_tools]

    def _resolve_task_llm(self, task: SubagentTask) -> Any:
        """Resolve the thread model for a specific task."""
        model_name = self._get_task_model_name(task)
        if model_name is None:
            if self._llm is None:
                raise RuntimeError("Subagent manager has no configured thread model")
            return self._llm

        from src.models.factory import create_chat_model

        return create_chat_model(model_name, thinking_enabled=False)

    @staticmethod
    def _build_graph_cache_key(task: SubagentTask) -> str:
        """Build a cache key that isolates per-task graph overrides."""
        system_prompt = task.metadata.get("system_prompt")
        model_name = task.metadata.get("model_name")
        if not system_prompt and not task.tools and model_name is None:
            return task.graph_template

        payload = {
            "template": task.graph_template,
            "system_prompt": system_prompt,
            "tools": list(task.tools),
            "max_turns": task.max_turns,
            "model_name": model_name,
        }
        return f"{task.graph_template}:{json.dumps(payload, sort_keys=True)}"

    def _create_task_graph(self, task: SubagentTask) -> Any:
        """Create a graph tailored to the task-level prompt and tool selection."""
        task_llm = self._resolve_task_llm(task)
        task_tools = self._resolve_task_tools(task)
        system_prompt = task.metadata.get("system_prompt")
        if system_prompt:
            return create_academic_agent_graph(
                task_llm,
                task_tools,
                system_prompt,
                task.max_turns,
            )
        return create_default_subagent_graph(task_llm, task_tools, task.max_turns)

    @classmethod
    def get_instance(cls) -> GlobalSubagentManager:
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
    def initialize(cls, config: SubagentConfig) -> GlobalSubagentManager:
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
        workspace_id = await self._validate_thread_binding(task)
        async with self._lock:
            ctx = self._get_or_create_context(task.thread_id, owner_user_id, workspace_id)

        async def run_with_limiter() -> SubagentResult:
            thread_terminal_status = "completed"
            subagent_status = "completed"
            final_result: SubagentResult | None = None
            try:
                async with self._limiter.acquire(task.thread_id):
                    logger.debug(f"Executing task {task.task_id}")
                    result = await self._execute_task(task)
                    final_result = result
                    ctx.store_result(task.task_id, result)
                    thread_terminal_status = self._map_result_status(result.status)
                    subagent_status = (
                        result.status.value
                        if isinstance(result.status, SubagentStatus)
                        else str(result.status)
                    )
                    logger.info(
                        f"Task {task.task_id} completed with status {result.status}"
                    )
                    return result
            except Exception:
                thread_terminal_status = "failed"
                subagent_status = "failed"
                raise
            finally:
                ctx.mark_task_finished(task.task_id)
                await self._sync_thread_agent_status(
                    ctx.workspace_id,
                    task.thread_id,
                    status="running" if ctx.active_task_count > 0 else thread_terminal_status,
                    subagent_count=ctx.active_task_count,
                )
                activity = await self._persist_subagent_activity(
                    task,
                    status=subagent_status,
                    result=final_result,
                )
                await self._publish_subagent_update(
                    ctx.workspace_id,
                    task,
                    status=subagent_status,
                    result=final_result,
                    activity=activity,
                )

        async_task = asyncio.create_task(run_with_limiter())
        ctx._tasks[task.task_id] = async_task
        ctx.store_task_definition(task)
        ctx.mark_task_active(task.task_id)
        await self._sync_thread_agent_status(
            ctx.workspace_id,
            task.thread_id,
            status="running",
            subagent_count=ctx.active_task_count,
        )
        activity = await self._persist_subagent_activity(task, status="running")
        await self._publish_subagent_update(
            ctx.workspace_id,
            task,
            status="running",
            activity=activity,
        )
        return task.task_id

    async def _validate_thread_binding(
        self,
        task: SubagentTask,
    ) -> str | None:
        """Validate that a task references a real, owned thread.

        When the caller provides a user-scoped thread id, the manager must
        refuse to seed in-memory thread context from an unknown or foreign
        thread. This keeps API and non-API entry points aligned on the same
        ownership invariant.
        """
        owner_user_id = self._get_task_owner_user_id(task)
        workspace_id = self._get_task_workspace_id(task)
        if owner_user_id is None:
            return workspace_id

        binding = await self._load_thread_binding(task.thread_id)
        if binding is None:
            raise SubagentAccessError("Thread not found")

        bound_owner_user_id = binding.get("owner_user_id")
        if bound_owner_user_id is not None and str(bound_owner_user_id) != owner_user_id:
            raise SubagentAccessError("Thread not found")

        bound_workspace_id = binding.get("workspace_id")
        normalized_bound_workspace = (
            str(bound_workspace_id) if bound_workspace_id is not None else None
        )
        if workspace_id is not None and normalized_bound_workspace != workspace_id:
            raise SubagentAccessError("Thread not found")

        return normalized_bound_workspace or workspace_id

    async def _load_thread_binding(
        self,
        thread_id: str,
    ) -> dict[str, str | None] | None:
        """Load canonical thread ownership/workspace facts from the database."""
        from src.database import Thread, get_db_session
        from src.services.workspace_skill_labels import (
            get_workspace_type,
            resolve_workspace_skill_name,
        )

        async with get_db_session() as db:
            thread = await db.get(Thread, thread_id)
            workspace_type = (
                await get_workspace_type(
                    db,
                    str(thread.workspace_id) if thread is not None and thread.workspace_id is not None else None,
                )
                if thread is not None
                else None
            )

        if thread is None:
            return None

        skill_id = (
            str(thread.skill).strip()
            if thread.skill is not None and str(thread.skill).strip()
            else None
        )
        return {
            "owner_user_id": str(thread.user_id),
            "workspace_id": str(thread.workspace_id) if thread.workspace_id is not None else None,
            "skill_id": skill_id,
            "skill_name": resolve_workspace_skill_name(workspace_type, skill_id),
        }

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
            # Get or create graph
            graph_cache_key = self._build_graph_cache_key(task)
            graph = self._graph_registry.get(graph_cache_key)
            if graph is None:
                graph = self._create_task_graph(task)
                self._graph_registry.register(graph_cache_key, graph)

            # Execute with timeout
            configurable: dict[str, object] = {"thread_id": task.thread_id}
            workspace_id = task.metadata.get("workspace_id")
            user_id = task.metadata.get("user_id")
            model_name = task.metadata.get("model_name")
            execution_session_id = task.metadata.get("execution_session_id")
            if workspace_id is not None:
                configurable["workspace_id"] = str(workspace_id)
            if user_id is not None:
                configurable["user_id"] = str(user_id)
            if execution_session_id is not None:
                configurable["execution_session_id"] = str(execution_session_id)
            if model_name is not None:
                configurable["model_name"] = str(model_name)
            run_config: dict[str, object] = {
                "configurable": configurable,
                "recursion_limit": task.max_turns,
            }

            result = await asyncio.wait_for(
                graph.ainvoke(
                    {"messages": [HumanMessage(content=task.prompt)]},
                    config=run_config,
                ),
                timeout=task.timeout,
            )

            messages = result.get("messages", [])
            output = messages[-1].content if messages else ""
            usage = extract_usage_from_agent_result(result)
            result_metadata: dict[str, Any] = {}
            model_name = self._get_task_model_name(task)
            if model_name:
                result_metadata["model_name"] = model_name
            if usage is not None:
                result_metadata["token_usage"] = usage.as_dict()

            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.COMPLETED,
                output=output,
                error=None,
                turns_used=len(messages) // 2,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                metadata=result_metadata,
            )

        except TimeoutError:
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.TIMED_OUT,
                output=None,
                error=f"Timed out after {task.timeout}s",
                duration_seconds=task.timeout,
            )

        except asyncio.CancelledError:
            return SubagentResult(
                task_id=task.task_id,
                status=SubagentStatus.CANCELLED,
                output=None,
                error=None,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
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
            if ctx:
                status = ctx.get_task_status(task_id)
                if status is not None:
                    return status

        persisted = await self._load_persisted_task_record(
            thread_id,
            task_id,
            user_id=user_id,
        )
        if persisted is None:
            return None
        return self._coerce_persisted_status(persisted.status)

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
            if ctx:
                result = ctx.get_result(task_id)
                if result is not None:
                    return result

        persisted = await self._load_persisted_task_record(
            thread_id,
            task_id,
            user_id=user_id,
        )
        if persisted is None:
            return None
        return self._persisted_record_to_result(persisted)

    async def wait_for_completion(
        self,
        thread_id: str,
        task_id: str,
        user_id: str | None = None,
    ) -> SubagentResult | None:
        """Wait for a task to reach a terminal state and return its result."""
        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
            if not ctx:
                persisted = await self._load_persisted_task_record(
                    thread_id,
                    task_id,
                    user_id=user_id,
                )
                return (
                    self._persisted_record_to_result(persisted)
                    if persisted is not None
                    else None
                )

            cached_result = ctx.get_result(task_id)
            if cached_result is not None:
                return cached_result

            async_task = ctx._tasks.get(task_id)

        if async_task is None:
            return None

        try:
            awaited_result = await asyncio.shield(async_task)
        except asyncio.CancelledError:
            if async_task.cancelled():
                cancelled_result = SubagentResult(
                    task_id=task_id,
                    status=SubagentStatus.CANCELLED,
                    output=None,
                    error=None,
                )
                async with self._lock:
                    ctx = self._get_accessible_context(thread_id, user_id)
                    if ctx is not None:
                        ctx.store_result(task_id, cancelled_result)
                return cancelled_result
            raise
        except Exception as exc:
            logger.exception(
                "Subagent task %s failed while waiting for completion",
                task_id,
            )
            failed_result = SubagentResult(
                task_id=task_id,
                status=SubagentStatus.FAILED,
                output=None,
                error=str(exc),
            )
            async with self._lock:
                ctx = self._get_accessible_context(thread_id, user_id)
                if ctx is not None:
                    ctx.store_result(task_id, failed_result)
            return failed_result

        if isinstance(awaited_result, SubagentResult):
            return awaited_result

        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
            if ctx is None:
                return None
            return ctx.get_result(task_id)

    async def list_thread_tasks(
        self,
        thread_id: str,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List recent subagent tasks for a thread."""
        async with self._lock:
            ctx = self._get_accessible_context(thread_id, user_id)
        if not ctx:
            return await self._list_persisted_thread_tasks(thread_id, user_id=user_id, limit=limit)

        ordered_tasks = sorted(
            ctx._task_defs.values(),
            key=lambda task: task.created_at,
            reverse=True,
        )[:limit]

        items: list[dict[str, Any]] = []
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
                    "output": result.output if result else None,
                }
            )
        return items

    async def check_thread_access(self, thread_id: str, user_id: str | None) -> bool:
        """Check whether a user can access a given thread."""
        async with self._lock:
            if self._get_accessible_context(thread_id, user_id) is not None:
                return True

        binding = await self._load_thread_binding(thread_id)
        if binding is None:
            return False
        owner_user_id = binding.get("owner_user_id")
        if user_id and owner_user_id and str(owner_user_id) != user_id:
            return False
        return True

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
        workspace_id: str | None,
        thread_id: str,
        *,
        status: str,
        subagent_count: int,
    ) -> None:
        """Mirror subagent activity into the thread-scoped status cache."""
        try:
            from src.services.thread_events import set_thread_status

            binding = await self._load_thread_binding(thread_id)
            resolved_workspace_id = (
                str(binding.get("workspace_id"))
                if binding is not None and binding.get("workspace_id") is not None
                else workspace_id
            )
            resolved_skill_id = (
                str(binding.get("skill_id"))
                if binding is not None and binding.get("skill_id") is not None
                else None
            )
            resolved_skill_name = (
                str(binding.get("skill_name"))
                if binding is not None and binding.get("skill_name") is not None
                else None
            )
            if binding is None and resolved_workspace_id is None:
                return
            await set_thread_status(
                resolved_workspace_id,
                thread_id,
                status=status,
                skill=resolved_skill_id,
                skill_name=resolved_skill_name,
                subagent_count=subagent_count,
            )
        except Exception:
            logger.debug(
                "Failed to sync subagent status for thread %s",
                thread_id,
                exc_info=True,
            )

    async def _publish_subagent_update(
        self,
        workspace_id: str | None,
        task: SubagentTask,
        *,
        status: str,
        result: SubagentResult | None = None,
        activity: dict[str, object] | None = None,
    ) -> None:
        """Mirror subagent lifecycle into the workspace event stream."""
        execution_session_id = str(
            task.metadata.get("execution_session_id") or ""
        ).strip()
        if not execution_session_id:
            logger.debug(
                "Skipping subagent.updated for task %s because execution_session_id is missing",
                task.task_id,
            )
            return
        try:
            from src.workspace_events import publish_workspace_event

            subagent_payload: dict[str, Any] = {
                "task_id": task.task_id,
                "thread_id": task.thread_id,
                "execution_session_id": execution_session_id,
                "status": status,
                "subagent_type": task.metadata.get("subagent_type"),
                "workflow_phase": task.metadata.get("workflow_phase"),
                "workflow_phase_index": task.metadata.get("workflow_phase_index"),
                "workflow_task_index": task.metadata.get("workflow_task_index"),
                "workflow_strategy": task.metadata.get("workflow_strategy"),
                "output_preview": self._truncate_preview(result.output if result else None),
                "output": result.output if result else None,
                "error": result.error if result else None,
            }
            result_metadata = result.metadata if result and isinstance(result.metadata, dict) else {}
            usage = extract_persisted_metadata_usage(result_metadata)
            if usage is not None:
                subagent_payload["token_usage"] = usage.as_dict()
            model_name = result_metadata.get("model_name")
            if not model_name:
                model_name = task.metadata.get("model_name")
            if isinstance(model_name, str) and model_name.strip():
                subagent_payload["model_name"] = model_name.strip()
            await publish_workspace_event(
                workspace_id,
                "subagent.updated",
                {
                    "subagent": subagent_payload,
                }
                | ({"activity": activity} if activity is not None else {}),
            )
        except Exception:
            logger.debug(
                "Failed to publish subagent update for thread %s",
                task.thread_id,
                exc_info=True,
            )

    async def _persist_subagent_activity(
        self,
        task: SubagentTask,
        *,
        status: str,
        result: SubagentResult | None = None,
    ) -> dict[str, object] | None:
        """Persist durable subagent state and build the canonical activity payload."""
        try:
            from src.database import get_db_session
            from src.subagents.store import SubagentTaskStore

            async with get_db_session() as db:
                record = await SubagentTaskStore(db).upsert_task_record(
                    task=task,
                    status=status,
                    result=result,
                )
        except Exception:
            logger.debug(
                "Failed to persist subagent activity for thread %s",
                task.thread_id,
                exc_info=True,
            )
            return None

        task_metadata = (
            record.task_metadata if isinstance(record.task_metadata, dict) else {}
        )
        usage = extract_persisted_metadata_usage(task_metadata)
        model_name_raw = task_metadata.get("model_name")
        model_name = (
            str(model_name_raw).strip()
            if model_name_raw is not None
            else ""
        )
        return serialize_activity_item(
            build_subagent_activity_item(
                workspace_id=record.workspace_id,
                task_id=str(record.id),
                thread_id=str(record.thread_id),
                status=record.status,
                subagent_type=record.subagent_type,
                prompt=record.prompt,
                output_preview=record.output_preview,
                error=record.error,
                token_usage=usage.as_dict() if usage is not None else None,
                model_name=model_name or None,
                occurred_at=record.completed_at or record.updated_at or record.created_at,
                created_at=record.created_at,
                completed_at=record.completed_at,
            )
        )

    async def _list_persisted_thread_tasks(
        self,
        thread_id: str,
        *,
        user_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        try:
            from src.database import get_db_session
            from src.subagents.store import SubagentTaskStore

            async with get_db_session() as db:
                records = await SubagentTaskStore(db).list_thread_records(
                    thread_id,
                    user_id=user_id,
                    limit=limit,
                )
        except Exception:
            logger.debug(
                "Failed to load persisted subagent records for thread %s",
                thread_id,
                exc_info=True,
            )
            return []

        return [
            {
                "task_id": record.id,
                "thread_id": record.thread_id,
                "prompt": record.prompt,
                "created_at": record.created_at,
                "status": record.status,
                "subagent_type": record.subagent_type,
                "execution_session_id": record.execution_session_id,
                "error": record.error,
                "output_preview": record.output_preview,
                "output": record.output,
            }
            for record in records
        ]

    async def _load_persisted_task_record(
        self,
        thread_id: str,
        task_id: str,
        *,
        user_id: str | None,
    ) -> Any | None:
        try:
            from src.database import get_db_session
            from src.subagents.store import SubagentTaskStore

            async with get_db_session() as db:
                record = await SubagentTaskStore(db).get_task_record(task_id)
        except Exception:
            logger.debug(
                "Failed to load persisted subagent record %s for thread %s",
                task_id,
                thread_id,
                exc_info=True,
            )
            return None

        if record is None or str(record.thread_id) != thread_id:
            return None
        if user_id and record.user_id and str(record.user_id) != user_id:
            return None
        return record

    def _get_or_create_context(
        self,
        thread_id: str,
        owner_user_id: str | None = None,
        workspace_id: str | None = None,
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
                workspace_id=workspace_id,
            )
            return self._threads[thread_id]

        ctx = self._threads[thread_id]
        if owner_user_id and ctx.owner_user_id and ctx.owner_user_id != owner_user_id:
            raise SubagentAccessError("Thread not found")
        if owner_user_id and ctx.owner_user_id is None:
            ctx.owner_user_id = owner_user_id
        if workspace_id and ctx.workspace_id is None:
            ctx.workspace_id = workspace_id
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
    def _get_task_workspace_id(task: SubagentTask) -> str | None:
        """Extract workspace id from task metadata."""
        workspace_id = task.metadata.get("workspace_id")
        return str(workspace_id) if workspace_id is not None else None

    @staticmethod
    def _get_task_model_name(task: SubagentTask) -> str | None:
        """Extract model id from task metadata."""
        model_name = task.metadata.get("model_name")
        return str(model_name) if model_name is not None else None

    @staticmethod
    def _map_result_status(status: SubagentStatus) -> str:
        """Normalize subagent terminal states into UI-facing thread states."""
        if status == SubagentStatus.COMPLETED:
            return "completed"
        if status in {SubagentStatus.CANCELLED, SubagentStatus.FAILED, SubagentStatus.TIMED_OUT}:
            return "failed"
        return "running"

    @staticmethod
    def _coerce_persisted_status(value: str | None) -> SubagentStatus | None:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        try:
            return SubagentStatus(normalized)
        except ValueError:
            return None

    @classmethod
    def _persisted_record_to_result(cls, record: Any) -> SubagentResult | None:
        status = cls._coerce_persisted_status(getattr(record, "status", None))
        if status is None:
            return None
        return SubagentResult(
            task_id=str(record.id),
            status=status,
            output=(
                str(record.output)
                if getattr(record, "output", None) is not None
                else str(record.output_preview)
                if getattr(record, "output_preview", None) is not None
                else None
            ),
            error=(
                str(record.error)
                if getattr(record, "error", None) is not None
                else None
            ),
            metadata={"durable_preview": True},
        )

    @staticmethod
    def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
        """Collapse task output into a compact single-line preview."""
        normalized = " ".join((content or "").split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

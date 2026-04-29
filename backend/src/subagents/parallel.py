"""Parallel subagent execution with phased dependencies."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from src.services.token_usage_collector import record_token_usage
from src.subagents.academic.registry import get_subagent_config
from src.subagents.context_snapshot import build_subagent_context_snapshot
from src.subagents.manager import SubagentAccessError
from src.subagents.model_routing import route_subagent_model
from src.subagents.models import SubagentStatus
from src.subagents.runtime import get_manager
from src.subagents.task_builder import (
    SubagentRuntimeContext,
    build_subagent_metadata,
    build_subagent_task,
)


@dataclass
class ExecutionPhase:
    """A phase of subagent execution with optional dependencies."""

    name: str
    tasks: list[dict[str, str]]
    depends_on: list[str] = field(default_factory=list)

    def is_parallel(self) -> bool:
        """Check if this phase has parallel tasks."""
        return len(self.tasks) > 1


@dataclass
class PhaseResult:
    """Result from executing a phase."""

    phase_name: str
    task_results: list[dict[str, Any]]
    success: bool = True
    error: str | None = None

    def __post_init__(self) -> None:
        """Calculate success based on task results."""
        if not self.task_results:
            # Empty results default to success unless an error is present
            self.success = True
        else:
            # Check each result for success, handling cases where 'success' key might be missing
            self.success = True
            for result in self.task_results:
                if isinstance(result, dict):
                    # If success key is False, phase fails
                    if result.get("success") is False:
                        self.success = False
                        break
                    # If success key is missing or None, treat as failure
                    elif result.get("success") is None:
                        self.success = False
                        break
                else:
                    # If result is not a dict, treat as failure
                    self.success = False
                    break

        # An explicit error always means the phase failed
        if self.error is not None:
            self.success = False


@dataclass
class PhasedPlan:
    """A plan with multiple execution phases."""

    phases: list[ExecutionPhase]
    context: dict[str, Any] = field(default_factory=dict)


class ParallelExecutor:
    """Executes subagent tasks in parallel with phased dependencies."""

    def __init__(self, max_concurrent: int = 4, phase_timeout: float | None = None, fail_fast: bool = False):
        """Initialize parallel executor.

        Args:
            max_concurrent: Maximum concurrent subagent executions
            phase_timeout: Optional timeout in seconds for each phase execution.
                          If ``None`` (the default), phases run without a timeout.
            fail_fast: If ``True``, phases whose dependencies failed will be
                      skipped immediately instead of being executed.
        """
        self.max_concurrent = max_concurrent
        self.phase_timeout = phase_timeout
        self.fail_fast = fail_fast
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._phase_events: dict[str, asyncio.Event] = {}

    async def execute_plan(
        self,
        plan: PhasedPlan,
        context: dict[str, Any] | None = None,
        phase_callback: Callable[[PhaseResult], Awaitable[None]] | None = None,
    ) -> list[PhaseResult]:
        """Execute a phased plan.

        Args:
            plan: The phased execution plan
            context: Execution context (workspace_id, etc.)

        Returns:
            List of phase results in execution order
        """
        context = dict(plan.context) | dict(context or {})
        results: dict[str, PhaseResult] = {}
        self._phase_events = {
            phase.name: asyncio.Event()
            for phase in plan.phases
        }

        missing_dependencies = sorted(
            {
                dep
                for phase in plan.phases
                for dep in phase.depends_on
                if dep not in self._phase_events
            }
        )
        if missing_dependencies:
            raise ValueError(
                "Unknown phase dependencies: "
                + ", ".join(missing_dependencies)
            )

        if context.get("thread_id"):
            context["_subagent_thread_id"] = str(context["thread_id"])
        else:
            trace_suffix = context.get("trace_id") or uuid4()
            context["_subagent_thread_id"] = f"parallel-plan-{trace_suffix}"

        failed_phases: set[str] = set()

        for phase_index, phase in enumerate(plan.phases):
            # Wait for dependencies
            for dep in phase.depends_on:
                await self._phase_events[dep].wait()

            # If fail_fast is enabled, skip phases whose dependencies failed
            if self.fail_fast:
                failed_deps = [dep for dep in phase.depends_on if dep in failed_phases]
                if failed_deps:
                    phase_result = PhaseResult(
                        phase_name=phase.name,
                        task_results=[],
                        error=f"Skipped: dependency phase(s) {', '.join(failed_deps)} failed",
                    )
                    results[phase.name] = phase_result
                    failed_phases.add(phase.name)

                    if phase_callback is not None:
                        await phase_callback(phase_result)

                    self._phase_events[phase.name].set()
                    continue

            # Execute phase
            phase_result = await self._execute_phase(phase, phase_index, context)
            results[phase.name] = phase_result

            if not phase_result.success:
                failed_phases.add(phase.name)

            if phase_callback is not None:
                await phase_callback(phase_result)

            self._phase_events[phase.name].set()

        return list(results.values())

    async def _execute_phase(
        self,
        phase: ExecutionPhase,
        phase_index: int,
        context: dict[str, Any],
    ) -> PhaseResult:
        """Execute a single phase, applying the phase timeout if configured."""
        if self.phase_timeout is None:
            return await self._execute_phase_inner(phase, phase_index, context)

        try:
            return await asyncio.wait_for(
                self._execute_phase_inner(phase, phase_index, context),
                timeout=self.phase_timeout,
            )
        except TimeoutError:
            return PhaseResult(
                phase_name=phase.name,
                task_results=[],
                error=f"Phase '{phase.name}' timed out after {self.phase_timeout}s",
            )

    async def _execute_phase_inner(
        self,
        phase: ExecutionPhase,
        phase_index: int,
        context: dict[str, Any],
    ) -> PhaseResult:
        """Execute a single phase (possibly with parallel tasks)."""
        task_results = []

        if phase.is_parallel():
            # Execute tasks in parallel
            tasks = [
                self._execute_task(
                    task,
                    phase_name=phase.name,
                    phase_index=phase_index,
                    task_index=task_index,
                    context=context,
                )
                for task_index, task in enumerate(phase.tasks)
            ]
            task_results = await asyncio.gather(*tasks)
        else:
            # Execute sequentially
            for task_index, task in enumerate(phase.tasks):
                result = await self._execute_task(
                    task,
                    phase_name=phase.name,
                    phase_index=phase_index,
                    task_index=task_index,
                    context=context,
                )
                task_results.append(result)

        return PhaseResult(
            phase_name=phase.name,
            task_results=list(task_results),
        )

    async def _execute_task(
        self,
        task: dict[str, Any],
        *,
        phase_name: str,
        phase_index: int,
        task_index: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single subagent task."""
        async with self._semaphore:
            subagent_type = task.get("subagent_type", "general")
            prompt = task.get("prompt", "")

            try:
                subagent_config = get_subagent_config(
                    subagent_type,
                    apply_runtime_overrides=True,
                )
            except ValueError:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": f"Unknown subagent type: {subagent_type}",
                }

            manager = get_manager()
            runtime_context = SubagentRuntimeContext.from_mapping(context)
            if runtime_context.execution_session_id is None:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": "Missing execution_session_id in runtime context",
                }
            routed_model_name = route_subagent_model(
                thread_model=runtime_context.model_name
            )
            context_snapshot = await build_subagent_context_snapshot(
                runtime_context=runtime_context,
                state=context,
            )
            if manager._llm is None and routed_model_name is None:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": "Subagent manager is unavailable because no thread model is configured.",
                }

            metadata: dict[str, str] = {
                "workflow_phase": phase_name,
                "workflow_phase_index": str(phase_index),
                "workflow_task_index": str(task_index),
                "workflow_strategy": str(context.get("workflow_strategy") or ""),
            }
            if routed_model_name is not None:
                metadata["model_name"] = routed_model_name

            subagent_task = build_subagent_task(
                manager._config,
                prompt=prompt,
                thread_id=str(context["_subagent_thread_id"]),
                fallback_max_turns=subagent_config.max_turns,
                requested_timeout=subagent_config.timeout,
                tools=subagent_config.tools,
                metadata=build_subagent_metadata(
                    subagent_type=subagent_type,
                    system_prompt=subagent_config.system_prompt,
                    context_snapshot=context_snapshot,
                    runtime_context=runtime_context,
                    include_workspace=True,
                    include_user=runtime_context.thread_id is not None,
                    extra_metadata=metadata,
                ),
            )

            try:
                await manager.spawn(subagent_task)
                result = await manager.wait_for_completion(
                    subagent_task.thread_id,
                    subagent_task.task_id,
                    user_id=subagent_task.metadata.get("user_id"),
                )
            except SubagentAccessError:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": "Thread not found",
                }
            except Exception as exc:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": str(exc),
                }

            if result is None:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": "Subagent task could not be loaded",
                }

            token_usage = None
            if isinstance(result.metadata, dict):
                token_usage = result.metadata.get("token_usage")
                record_token_usage(token_usage)

            payload = {
                "subagent_type": subagent_type,
                "success": result.status == SubagentStatus.COMPLETED,
                "result": self._normalize_result_payload(result.output),
                "error": result.error,
            }
            if isinstance(token_usage, dict):
                payload["token_usage"] = token_usage
            return payload

    @classmethod
    def _normalize_result_payload(cls, payload: Any) -> Any:
        """Normalize structured subagent output into native Python values."""
        if not isinstance(payload, str):
            return payload

        normalized = payload.strip()
        if not normalized:
            return normalized

        for candidate in cls._json_candidates(normalized):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        return normalized

    @staticmethod
    def _json_candidates(payload: str) -> list[str]:
        """Generate candidate JSON snippets from a model response."""
        candidates: list[str] = [payload]
        seen = {payload}

        for match in re.findall(r"```(?:json)?\s*(.*?)```", payload, flags=re.IGNORECASE | re.DOTALL):
            candidate = match.strip()
            if candidate and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)

        for opener, closer in (("{", "}"), ("[", "]")):
            start = payload.find(opener)
            end = payload.rfind(closer)
            if start == -1 or end <= start:
                continue
            candidate = payload[start : end + 1].strip()
            if candidate and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)

        return candidates

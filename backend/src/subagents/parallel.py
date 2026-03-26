"""Parallel subagent execution with phased dependencies."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from src.subagents.academic.registry import registry
from src.subagents.executor import SubagentExecutor, SubagentStatus


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

    def __post_init__(self):
        """Calculate success based on task results."""
        if not self.task_results:
            self.success = True
            return

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


@dataclass
class PhasedPlan:
    """A plan with multiple execution phases."""

    phases: list[ExecutionPhase]
    context: dict[str, Any] = field(default_factory=dict)


class ParallelExecutor:
    """Executes subagent tasks in parallel with phased dependencies."""

    def __init__(self, max_concurrent: int = 4):
        """Initialize parallel executor.

        Args:
            max_concurrent: Maximum concurrent subagent executions
        """
        self.max_concurrent = max_concurrent
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
        context = context or {}
        results: dict[str, PhaseResult] = {}
        completed_phases: set[str] = set()

        for phase in plan.phases:
            # Wait for dependencies
            for dep in phase.depends_on:
                # Wait for the dependency phase to complete
                event = self._phase_events.get(dep)
                if event:
                    await event.wait()
                else:
                    # If event doesn't exist, check if it's in completed_phases
                    while dep not in completed_phases:
                        await asyncio.sleep(0.01)

            # Execute phase
            phase_result = await self._execute_phase(phase, context)
            results[phase.name] = phase_result
            completed_phases.add(phase.name)

            if phase_callback is not None:
                await phase_callback(phase_result)

            # Create and set event for this phase
            if phase.name not in self._phase_events:
                self._phase_events[phase.name] = asyncio.Event()
            self._phase_events[phase.name].set()

        return list(results.values())

    async def _execute_phase(
        self,
        phase: ExecutionPhase,
        context: dict[str, Any],
    ) -> PhaseResult:
        """Execute a single phase (possibly with parallel tasks)."""
        task_results = []

        if phase.is_parallel():
            # Execute tasks in parallel
            tasks = [
                self._execute_task(task, context)
                for task in phase.tasks
            ]
            task_results = await asyncio.gather(*tasks)
        else:
            # Execute sequentially
            for task in phase.tasks:
                result = await self._execute_task(task, context)
                task_results.append(result)

        return PhaseResult(
            phase_name=phase.name,
            task_results=list(task_results),
        )

    async def _execute_task(
        self,
        task: dict[str, str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single subagent task."""
        async with self._semaphore:
            subagent_type = task.get("subagent_type", "general")
            prompt = task.get("prompt", "")

            config = registry.get(subagent_type)
            if not config:
                return {
                    "subagent_type": subagent_type,
                    "success": False,
                    "error": f"Unknown subagent type: {subagent_type}",
                }

            executor = SubagentExecutor(
                config=config,
                tools=[],  # Tools will be loaded by executor
                thread_id=context.get("thread_id"),
                trace_id=context.get("trace_id"),
            )

            result = await executor.aexecute(prompt)

            return {
                "subagent_type": subagent_type,
                "success": result.status == SubagentStatus.COMPLETED,
                "result": result.result,
                "error": result.error,
            }

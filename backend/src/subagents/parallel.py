"""Parallel subagent execution with phased dependencies."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.subagents.registry import registry


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

    async def execute_plan(
        self,
        plan: PhasedPlan,
        context: dict[str, Any] | None = None,
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
                while dep not in completed_phases:
                    await asyncio.sleep(0.1)

            # Execute phase
            phase_result = await self._execute_phase(phase, context)
            results[phase.name] = phase_result
            completed_phases.add(phase.name)

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
            success=all(r.get("success", False) for r in task_results),
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

            # Run in thread pool since execute is synchronous
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: executor.execute(prompt),
            )

            return {
                "subagent_type": subagent_type,
                "success": result.status == SubagentStatus.COMPLETED,
                "result": result.result,
                "error": result.error,
            }

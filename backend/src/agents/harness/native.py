"""Native Wenjin AgentHarness provider backed by managed subagents."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.config.config_loader import get_app_config
from src.subagents.parallel import ExecutionPhase, ParallelExecutor, PhasedPlan

from .contracts import (
    AgentSessionRequest,
    AgentSessionResult,
    SubtaskRequest,
    SubtaskResult,
)

logger = logging.getLogger(__name__)


def _normalize_positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _require_execution_session_id(context: Any) -> str:
    if not isinstance(context, dict):
        context = dict(context or {})
    execution_session_id = str(context.get("execution_session_id") or "").strip()
    if not execution_session_id:
        raise ValueError("execution_session_id is required for AgentHarness execution")
    return execution_session_id


class NativeWenjinAgentHarness:
    """Default provider that delegates to Wenjin's managed subagent runtime."""

    provider = "native_wenjin"

    def __init__(
        self,
        *,
        max_concurrent: int | None = None,
        phase_timeout: float | None = None,
        fail_fast: bool = True,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._phase_timeout = phase_timeout
        self._fail_fast = fail_fast

    def _resolve_max_concurrent(self) -> int:
        if self._max_concurrent is not None:
            return _normalize_positive_int(self._max_concurrent, default=3)
        try:
            return _normalize_positive_int(
                getattr(get_app_config().subagents, "max_concurrent", 3),
                default=3,
            )
        except Exception:
            logger.debug("Failed to read max_concurrent from app config", exc_info=True)
            return 3

    def _build_executor(self) -> ParallelExecutor:
        return ParallelExecutor(
            max_concurrent=self._resolve_max_concurrent(),
            phase_timeout=self._phase_timeout,
            fail_fast=self._fail_fast,
        )

    async def run_subtask(self, request: SubtaskRequest) -> SubtaskResult:
        _require_execution_session_id(request.context)
        session_result = await self.run_session(
            AgentSessionRequest(
                strategy=str(request.metadata.get("strategy") or "single_subtask"),
                phased_plan=PhasedPlan(
                    phases=[
                        ExecutionPhase(
                            name="subtask",
                            tasks=[
                                {
                                    "subagent_type": request.subagent_type,
                                    "prompt": request.prompt,
                                }
                            ],
                        )
                    ]
                ),
                context=dict(request.context),
            )
        )
        task_results = (
            session_result.phase_results[0].task_results
            if session_result.phase_results
            else []
        )
        first_result = task_results[0] if task_results else {}
        if not isinstance(first_result, dict):
            return SubtaskResult(
                subagent_type=request.subagent_type,
                success=False,
                error="invalid_subtask_result",
            )
        return SubtaskResult(
            subagent_type=str(first_result.get("subagent_type") or request.subagent_type),
            success=bool(first_result.get("success")),
            result=first_result.get("result"),
            error=(
                str(first_result.get("error"))
                if first_result.get("error") is not None
                else None
            ),
        )

    async def run_session(self, request: AgentSessionRequest) -> AgentSessionResult:
        run_id = _require_execution_session_id(request.context)
        executor = self._build_executor()

        # Spec §6.2 B3 — persist workspace_run row at run start so the row
        # exists before any SSE events arrive.  Failures are non-fatal: a
        # missing row degrades gracefully (no history entry).
        context = dict(request.context) if request.context else {}
        try:
            from src.database.session import get_db_session
            from src.services.workspace_run_service import WorkspaceRunService

            workspace_id = str(context.get("workspace_id") or "").strip()
            thread_id = str(context.get("thread_id") or "").strip()
            title = str(context.get("title") or "").strip() or "untitled run"
            if workspace_id and thread_id:
                async with get_db_session() as db:
                    svc = WorkspaceRunService(db)
                    await svc.create_run(
                        run_id=run_id,
                        workspace_id=workspace_id,
                        thread_id=thread_id,
                        title=title,
                        started_at=datetime.now(UTC),
                    )
        except Exception:
            logger.warning(
                "workspace_run.create_run failed for run_id=%s — continuing without persistence",
                run_id,
                exc_info=True,
            )

        # Spec §6.1 — register the executor so the runs router can deliver
        # pause/resume/cancel signals while this session is in flight.
        from src.subagents.manager import GlobalSubagentManager
        try:
            mgr = GlobalSubagentManager.get_instance()
        except RuntimeError:
            mgr = None  # In tests / standalone usage the singleton may not exist.
        if mgr is not None:
            mgr.register_executor(run_id, executor)

        # Emit graph structure if execution_id is available
        execution_id = context.get("execution_id")
        if execution_id:
            try:
                from src.services.execution_event_publisher import publish_execution_event

                graph_nodes = []
                graph_edges = []
                for phase_idx, phase in enumerate(request.phased_plan.phases):
                    for task_idx, task in enumerate(phase.tasks):
                        # Unique node ID: phase index + task index ensures no collision
                        node_id = f"phase{phase_idx}:task{task_idx}"
                        graph_nodes.append({
                            "id": node_id,
                            "type": task.get("subagent_type", "task"),
                            "label": task.get("label") or task.get("subagent_type", "task"),
                            "metadata": {
                                "phase": phase_idx,
                                "phase_name": phase.name,
                                "task_index": task_idx,
                                "subagent_type": task.get("subagent_type", "task"),
                            },
                        })
                    # Add edges from dependencies (phase-level, not task-level)
                    for dep in phase.depends_on:
                        for prev_phase_idx, prev_phase in enumerate(request.phased_plan.phases):
                            if prev_phase.name == dep:
                                for prev_task_idx in range(len(prev_phase.tasks)):
                                    for task_idx in range(len(phase.tasks)):
                                        graph_edges.append({
                                            "from": f"phase{prev_phase_idx}:task{prev_task_idx}",
                                            "to": f"phase{phase_idx}:task{task_idx}",
                                        })
                await publish_execution_event(
                    str(execution_id),
                    "execution.graph_structure",
                    {
                        "graph_structure": {
                            "nodes": graph_nodes,
                            "edges": graph_edges,
                        }
                    },
                    workspace_id=str(context.get("workspace_id") or "").strip() or None,
                )
            except Exception:
                logger.debug(
                    "Failed to emit graph structure for execution_id=%s",
                    execution_id,
                    exc_info=True,
                )

        try:
            phase_results = await executor.execute_plan(
                request.phased_plan,
                context=dict(request.context),
                phase_callback=request.phase_callback,
            )
        finally:
            if mgr is not None:
                mgr.unregister_executor(run_id)

        return AgentSessionResult(
            provider=self.provider,
            strategy=request.strategy,
            phase_results=list(phase_results),
        )

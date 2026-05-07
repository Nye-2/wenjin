"""Native Wenjin AgentHarness provider backed by managed subagents."""

from __future__ import annotations

import logging
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

        # Spec §6.1 — register the executor so the runs router can deliver
        # pause/resume/cancel signals while this session is in flight.
        from src.subagents.manager import GlobalSubagentManager
        try:
            mgr = GlobalSubagentManager.get_instance()
        except RuntimeError:
            mgr = None  # In tests / standalone usage the singleton may not exist.
        if mgr is not None:
            mgr.register_executor(run_id, executor)

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

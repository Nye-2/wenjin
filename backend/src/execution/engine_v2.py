"""ExecutionEngineV2 — unified execution path via LeadAgentRuntime.

Spec §4.2.6: All executions (chat-triggered or feature-triggered) flow through
LeadAgentRuntime via this single engine. The engine is the unit-testable boundary
between Celery task dispatch and the runtime; Celery wiring is Phase 4 cutover work.
"""

from __future__ import annotations

import logging

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime

logger = logging.getLogger(__name__)


class ExecutionEngineV2:
    """V2 execution engine: unified path replacing ChatExecutionEngine + FeatureExecutionEngine.

    Responsibilities:
    - Fetch ExecutionRecord by ID
    - Mark it running via ExecutionService.start_execution()
    - Invoke LeadAgentRuntime.run_session()
    - Persist result via ExecutionService.complete_execution()
    - Record run history via RunHistoryService.record()
    - On any failure: mark execution as failed and re-raise
    """

    def __init__(
        self,
        *,
        runtime: LeadAgentRuntime,
        execution_service,
        run_history_service,
    ) -> None:
        """
        Args:
            runtime: LeadAgentRuntime instance.
            execution_service: ExecutionService (backend/src/services/execution_service.py).
                Used methods: get_by_id(), start_execution(), complete_execution().
            run_history_service: RunHistoryService
                (backend/src/services/rooms/run_history_service.py).
                Used method: record().
        """
        self.runtime = runtime
        self.execution_service = execution_service
        self.run_history_service = run_history_service

    async def run(self, execution_id: str) -> None:
        """Execute a capability run identified by execution_id.

        Fetches the ExecutionRecord, invokes the runtime, persists the result,
        and records run history.

        Args:
            execution_id: ID of an existing ExecutionRecord in "pending" status.

        Raises:
            ValueError: If no ExecutionRecord exists for execution_id.
            Exception: Re-raises any exception from the runtime after marking failed.
        """
        # Note: ExecutionService exposes get_by_id(), not get().
        execution = await self.execution_service.get_by_id(execution_id)
        if execution is None:
            raise ValueError(f"execution {execution_id} not found")

        await self._mark_running(execution_id)

        try:
            brief = TaskBrief.model_validate(execution.params["brief"])
            report = await self.runtime.run_session(
                execution_id=execution_id,
                brief=brief,
            )

            await self._mark_complete(execution_id, report)
            await self.run_history_service.record(
                execution.workspace_id,
                execution_id,
                execution.feature_id or report.capability_id,
                report.narrative[:200],
                report.narrative,
                report.status,
                report.duration_seconds,
                token_usage=report.token_usage,
                artifact_count=len(report.outputs),
            )

        except Exception as exc:
            logger.exception(
                "execution failed",
                extra={"execution_id": execution_id},
            )
            await self._mark_failed(execution_id, str(exc))
            raise

    async def _mark_running(self, execution_id: str) -> None:
        await self.execution_service.start_execution(execution_id)

    async def _mark_complete(self, execution_id: str, report: TaskReport) -> None:
        # complete_execution signature: (execution_id, *, status, result, error, result_summary, commit)
        await self.execution_service.complete_execution(
            execution_id,
            status=report.status,
            result={"task_report": report.model_dump(mode="json")},
        )

    async def _mark_failed(self, execution_id: str, error: str) -> None:
        await self.execution_service.complete_execution(
            execution_id,
            status="failed",
            error=error,
        )

"""ExecutionEngineV2 — unified execution path via LeadAgentRuntime.

Spec §4.2.6: All executions (chat-triggered or feature-triggered) flow through
LeadAgentRuntime via this single engine. The engine is the unit-testable boundary
between Celery task dispatch and the runtime; Celery wiring is Phase 4 cutover work.
"""

from __future__ import annotations

import logging
from inspect import isawaitable

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.services.workspace_prism_service import WorkspacePrismService

logger = logging.getLogger(__name__)


class ExecutionEngineV2:
    """V2 execution engine: unified path replacing ChatExecutionEngine + FeatureExecutionEngine.

    Responsibilities:
    - Fetch ExecutionRecord by ID
    - Mark it running via ExecutionService.start_execution()
    - Invoke LeadAgentRuntime.run_session()
    - Persist result via ExecutionService.complete_execution()
    - Record run history as a DataService execution event
    - On any failure: mark execution as failed and re-raise
    """

    def __init__(
        self,
        *,
        runtime: LeadAgentRuntime,
        execution_service,
    ) -> None:
        """
        Args:
            runtime: LeadAgentRuntime instance.
            execution_service: ExecutionService (backend/src/services/execution_service.py).
                Used methods: get_by_id(), start_execution(), complete_execution().
        """
        self.runtime = runtime
        self.execution_service = execution_service

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
        await self._append_execution_event(
            execution_id,
            "execution.status",
            workspace_id=execution.workspace_id,
            payload_json={"status": "running"},
        )

        # Wire the runtime's graph_structure persistence callback
        self.runtime.set_graph_structure = (
            lambda gs: self.execution_service.set_graph_structure(execution_id, gs)
        )

        try:
            brief = TaskBrief.model_validate(execution.params["brief"])
            brief = await self._attach_manuscript_context(brief, execution)
            report = await self.runtime.run_session(
                execution_id=execution_id,
                brief=brief,
            )

            await self._mark_complete(execution_id, report)
            await self._append_execution_event(
                execution_id,
                "execution.status",
                workspace_id=execution.workspace_id,
                payload_json={"status": report.status},
            )
            await self._append_execution_event(
                execution_id,
                "execution.run_history",
                workspace_id=execution.workspace_id,
                payload_json={
                    "capability_id": execution.feature_id or report.capability_id,
                    "title": report.narrative[:200],
                    "summary": report.narrative,
                    "status": report.status,
                    "duration_seconds": report.duration_seconds,
                    "token_usage": report.token_usage or {},
                    "artifact_count": len(report.outputs),
                },
            )

        except Exception as exc:
            logger.exception(
                "execution failed",
                extra={"execution_id": execution_id},
            )
            await self._mark_failed(execution_id, str(exc))
            await self._append_execution_event(
                execution_id,
                "execution.status",
                workspace_id=execution.workspace_id,
                payload_json={"status": "failed", "error": str(exc)},
            )
            raise

    async def _mark_running(self, execution_id: str) -> None:
        await self.execution_service.start_execution(execution_id)

    async def _attach_manuscript_context(
        self,
        brief: TaskBrief,
        execution,
    ) -> TaskBrief:
        if brief.manuscript_context:
            return brief

        db = getattr(self.execution_service, "db", None)
        workspace_id = str(brief.workspace_id or getattr(execution, "workspace_id", "") or "")
        user_id = str(getattr(execution, "user_id", "") or "")
        if not isinstance(db, AsyncSession) or not workspace_id or not user_id:
            return brief

        try:
            manuscript_context = await WorkspacePrismService(
                db
            ).get_launch_context_projection(
                workspace_id,
                user_id=user_id,
            )
        except ValueError:
            return brief

        return brief.model_copy(update={"manuscript_context": manuscript_context})

    async def _mark_complete(self, execution_id: str, report: TaskReport) -> None:
        # complete_execution signature: (execution_id, *, status, result, error, result_summary, commit)
        await self.execution_service.complete_execution(
            execution_id,
            status=report.status,
            result={"task_report": report.model_dump(mode="json")},
            result_summary=report.narrative[:200] if report.narrative else None,
        )

    async def _mark_failed(self, execution_id: str, error: str) -> None:
        await self.execution_service.complete_execution(
            execution_id,
            status="failed",
            error=error,
        )

    async def _append_execution_event(
        self,
        execution_id: str,
        event_type: str,
        *,
        workspace_id: str | None,
        payload_json: dict,
        node_id: str | None = None,
    ) -> None:
        append_event = getattr(self.execution_service, "append_execution_event", None)
        if not callable(append_event):
            return
        try:
            result = append_event(
                execution_id,
                event_type,
                workspace_id=workspace_id,
                node_id=node_id,
                payload_json=payload_json,
            )
            if isawaitable(result):
                await result
        except Exception:
            logger.warning("append_execution_event failed", exc_info=True)

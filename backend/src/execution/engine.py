"""ExecutionEngineV2 — unified execution path via LeadAgentRuntime.

Spec §4.2.6: All executions (chat-triggered or feature-triggered) flow through
LeadAgentRuntime via this single engine. The engine is the unit-testable boundary
between Celery task dispatch and the runtime; Celery wiring is Phase 4 cutover work.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from inspect import isawaitable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.dataservice_client.provider import dataservice_client
from src.services.thread_billing import normalize_token_usage
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
            if not brief.user_id and getattr(execution, "user_id", None):
                brief = brief.model_copy(update={"user_id": str(execution.user_id)})
            brief = await self._attach_manuscript_context(brief, execution)
            report = await self.runtime.run_session(
                execution_id=execution_id,
                brief=brief,
            )

            billing_metadata = await self._settle_feature_billing(execution, report)
            try:
                await self._mark_complete(
                    execution_id,
                    report,
                    billing_metadata=billing_metadata,
                )
            except Exception:
                await self._refund_feature_billing(
                    execution,
                    billing_metadata=billing_metadata,
                    reason="执行结果持久化失败退款",
                )
                raise
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
        explicit_context = self._explicit_manuscript_context_from_brief(brief)
        if explicit_context is not None:
            return brief.model_copy(update={"manuscript_context": explicit_context})

        db = getattr(self.execution_service, "db", None)
        workspace_id = str(brief.workspace_id or getattr(execution, "workspace_id", "") or "")
        user_id = str(getattr(execution, "user_id", "") or "")
        if not isinstance(db, AsyncSession) or not workspace_id or not user_id:
            return brief

        prism_required = await self._requires_prism_surface(brief, execution)
        prism_service = WorkspacePrismService(db)
        try:
            manuscript_context = await prism_service.get_launch_context_projection(
                workspace_id,
                user_id=user_id,
            )
        except ValueError:
            if not prism_required:
                return brief
            await prism_service.ensure_primary_project(
                workspace_id,
                user_id=user_id,
                project_name=await self._workspace_project_name(workspace_id),
            )
            manuscript_context = await prism_service.get_launch_context_projection(
                workspace_id,
                user_id=user_id,
            )

        return brief.model_copy(update={"manuscript_context": manuscript_context})

    @staticmethod
    def _explicit_manuscript_context_from_brief(brief: TaskBrief) -> dict[str, Any] | None:
        params = brief.brief if isinstance(brief.brief, Mapping) else {}
        latex_project_id = str(
            params.get("latex_project_id")
            or params.get("project_id")
            or "",
        ).strip()
        if not latex_project_id:
            return None
        main_file = str(params.get("main_file") or "main.tex").strip() or "main.tex"
        target_files: list[str] = []
        file_path = str(params.get("file_path") or "").strip()
        if file_path:
            target_files.append(file_path)
        if main_file and main_file not in target_files:
            target_files.insert(0, main_file)
        return {
            "latex_project_id": latex_project_id,
            "main_file": main_file,
            "target_files": target_files,
            "source": "explicit_launch_params",
        }

    async def _requires_prism_surface(self, brief: TaskBrief, execution) -> bool:
        """Return whether this capability needs a workspace-owned Prism surface."""
        workspace_type = str(getattr(execution, "workspace_type", "") or "").strip()
        capability_id = str(brief.capability_id or getattr(execution, "feature_id", "") or "").strip()
        if not workspace_type or not capability_id:
            return False

        try:
            async with dataservice_client() as client:
                capability = await client.get_catalog_capability(
                    workspace_type=workspace_type,
                    capability_id=capability_id,
                    enabled_only=True,
                )
        except Exception:
            logger.warning(
                "failed to resolve capability prism requirement",
                extra={
                    "workspace_type": workspace_type,
                    "capability_id": capability_id,
                },
                exc_info=True,
            )
            return False
        if capability is None:
            return False

        definition = capability.definition_json if isinstance(capability.definition_json, dict) else {}
        mission = definition.get("mission") if isinstance(definition.get("mission"), dict) else {}
        if mission.get("primary_surface") == "prism":
            return True
        if mission.get("document_role") == "primary_manuscript":
            return True

        graph_template = capability.graph_template if isinstance(capability.graph_template, dict) else {}
        for phase in graph_template.get("phases", []):
            if not isinstance(phase, dict):
                continue
            for task in phase.get("tasks", []):
                if not isinstance(task, dict):
                    continue
                for output in task.get("outputs", []):
                    if isinstance(output, dict) and output.get("kind") == "prism_file_change":
                        return True
        return False

    async def _workspace_project_name(self, workspace_id: str) -> str:
        try:
            async with dataservice_client() as client:
                workspace = await client.get_workspace(workspace_id)
        except Exception:
            logger.warning(
                "failed to resolve workspace name for Prism project",
                extra={"workspace_id": workspace_id},
                exc_info=True,
            )
            return "Workspace Manuscript"
        if workspace is None:
            return "Workspace Manuscript"
        return str(workspace.name or "Workspace Manuscript")

    async def _settle_feature_billing(
        self,
        execution: Any,
        report: TaskReport,
    ) -> dict[str, Any] | None:
        """Settle completed feature executions against measured token usage."""
        if report.status != "completed" or not report.token_usage:
            return None

        from src.services.credit_service import CreditService

        credit_service = CreditService()
        billing = await credit_service.consume_for_feature_usage(
            user_id=str(execution.user_id),
            feature_id=str(execution.feature_id or report.capability_id),
            token_usage=report.token_usage,
            workspace_id=str(execution.workspace_id) if execution.workspace_id else None,
            task_id=str(execution.id),
            metadata={
                "execution_id": str(execution.id),
                "workspace_type": getattr(execution, "workspace_type", None),
                "source": "execution_engine",
            },
        )
        billing_metadata: dict[str, Any] = dict(billing.as_metadata())
        return billing_metadata

    async def _refund_feature_billing(
        self,
        execution: Any,
        *,
        billing_metadata: dict[str, Any] | None,
        reason: str,
    ) -> None:
        transaction_id = (
            str(billing_metadata.get("transaction_id"))
            if isinstance(billing_metadata, dict) and billing_metadata.get("transaction_id")
            else None
        )
        if not transaction_id:
            return

        from src.services.credit_service import CreditService

        credit_service = CreditService()
        await credit_service.refund_consumption(
            user_id=str(execution.user_id),
            original_transaction_id=transaction_id,
            reason=reason,
            task_id=str(execution.id),
        )

    async def _mark_complete(
        self,
        execution_id: str,
        report: TaskReport,
        *,
        billing_metadata: dict[str, Any] | None = None,
    ) -> None:
        # complete_execution signature: (execution_id, *, status, result, error, result_summary, commit)
        result_payload: dict[str, Any] = {"task_report": report.model_dump(mode="json")}
        normalized_usage = normalize_token_usage(report.token_usage)
        if normalized_usage is not None:
            result_payload["token_usage"] = normalized_usage.as_dict()
        if billing_metadata is not None:
            result_payload["billing"] = dict(billing_metadata)
        await self.execution_service.complete_execution(
            execution_id,
            status=report.status,
            result=result_payload,
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
        payload_json: dict[str, Any],
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

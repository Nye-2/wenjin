"""Application handler for deprecated thesis API compatibility routes."""

from __future__ import annotations

import logging
from typing import Any

from src.application.errors import (
    BadRequestError,
    ConflictError,
    InternalServiceError,
    NotFoundError,
    PaymentRequiredError,
    TooManyRequestsError,
)
from src.application.handlers.feature_execution_handler import FeatureExecutionHandler
from src.application.results import (
    FeatureExecutionAdvisory,
    FeatureTaskSubmission,
    ThesisCancelResult,
    ThesisPreviewResult,
    ThesisStatusResult,
)
from src.task.service import TaskService

logger = logging.getLogger(__name__)


class ThesisApiHandler:
    """Request-level orchestration for legacy thesis API endpoints."""

    def __init__(
        self,
        *,
        task_service: TaskService,
        feature_execution_handler: FeatureExecutionHandler,
    ) -> None:
        self.task_service = task_service
        self.feature_execution_handler = feature_execution_handler

    async def generate(
        self,
        request: Any,
        *,
        idempotency_key: str | None = None,
        redis_client: Any | None = None,
    ) -> ThesisStatusResult:
        """Queue thesis generation through the unified feature execution chain."""
        result = await self.feature_execution_handler.execute(
            request.workspace_id,
            "thesis_writing",
            {
                **request.model_dump(),
                "action": "write_all",
            },
            None,
            idempotency_key=idempotency_key,
            redis_client=redis_client,
        )

        if isinstance(result, FeatureExecutionAdvisory) or (
            isinstance(result, dict) and result.get("status") == "warning"
        ):
            raise self._map_warning_to_exception(result)

        if isinstance(result, dict):
            task_id = result.get("task_id")
            message = result.get("message") or "Task submitted"
        elif isinstance(result, FeatureTaskSubmission):
            task_id = result.task_id
            message = result.message
        else:
            task_id = None
            message = "Task submitted"

        if not task_id:
            raise InternalServiceError("Failed to queue thesis generation task")

        logger.info("[Thesis] Submitted unified task %s for workspace %s", task_id, request.workspace_id)
        return ThesisStatusResult(
            task_id=task_id,
            status="pending",
            progress=0.0,
            current_phase="init",
            message=message,
        )

    async def get_status(self, task_id: str, user_id: str) -> ThesisStatusResult:
        """Get thesis task status."""
        task_status = await self.task_service.get_task_status(task_id, user_id)
        if not task_status:
            raise NotFoundError(f"Task not found: {task_id}")
        return self._to_thesis_status_response(task_status)

    async def cancel(self, task_id: str, user_id: str) -> ThesisCancelResult:
        """Cancel a thesis task."""
        success = await self.task_service.cancel_task(task_id, user_id)
        if not success:
            raise NotFoundError("Task not found or cannot be cancelled")

        logger.info("[Thesis] Cancelled task %s", task_id)
        return ThesisCancelResult(
            task_id=task_id,
            status="cancelled",
            message="Task cancelled",
        )

    async def get_preview(self, task_id: str, user_id: str) -> ThesisPreviewResult:
        """Get preview payload for a thesis task."""
        task_status = await self.task_service.get_task_status(task_id, user_id)
        if not task_status:
            raise NotFoundError(f"Task not found: {task_id}")

        details = self._merge_task_details(task_status)
        return ThesisPreviewResult(
            task_id=task_id,
            latex_content=details.get("latex_content", ""),
            sections_completed=details.get("sections_completed", 0),
            sections_total=details.get("sections_total", 0),
        )

    async def list_tasks(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ) -> list[ThesisStatusResult]:
        """List thesis tasks for a user, optionally filtered by workspace."""
        task_records = await self.task_service.list_task_records(
            user_id=user_id,
            limit=100,
        )

        filtered_records = [
            record
            for record in task_records
            if self._is_legacy_or_unified_thesis_task(record)
            and (
                workspace_id is None
                or ((record.payload or {}).get("workspace_id") == workspace_id)
            )
        ]

        results: list[ThesisStatusResult] = []
        for record in filtered_records:
            task_status = await self.task_service.get_task_status(record.id, user_id)
            if task_status:
                results.append(self._to_thesis_status_response(task_status))
        return results

    @staticmethod
    def _map_task_status(status: str) -> str:
        if status == "success":
            return "completed"
        return status

    @staticmethod
    def _merge_task_details(task_status: dict[str, Any]) -> dict[str, Any]:
        details: dict[str, Any] = {}
        metadata = task_status.get("metadata")
        result = task_status.get("result")
        if isinstance(metadata, dict):
            details.update(metadata)
        if isinstance(result, dict):
            details.update(result)
        return details

    @staticmethod
    def _is_legacy_or_unified_thesis_task(record: Any) -> bool:
        """Accept both historical and unified thesis-writing task records."""
        task_type = str(getattr(record, "task_type", ""))
        payload = getattr(record, "payload", {}) or {}
        feature_id = str(payload.get("feature_id", ""))
        handler_key = str(payload.get("handler_key", ""))

        return (
            task_type == "thesis_generation"
            or (task_type == "workspace_feature" and feature_id == "thesis_writing")
            or handler_key == "thesis.thesis_writing"
        )

    @classmethod
    def _to_thesis_status_response(cls, task_status: dict[str, Any]) -> ThesisStatusResult:
        details = cls._merge_task_details(task_status)
        progress = float(task_status.get("progress", 0)) / 100
        return ThesisStatusResult(
            task_id=task_status["task_id"],
            status=cls._map_task_status(task_status["status"]),
            progress=max(0.0, min(progress, 1.0)),
            current_phase=details.get("current_phase"),
            message=task_status.get("message"),
            pdf_path=details.get("pdf_path"),
            error=task_status.get("error"),
        )

    @staticmethod
    def _map_warning_to_exception(result: FeatureExecutionAdvisory | dict[str, Any]) -> Exception:
        """Translate unified feature warnings to application-layer exceptions."""
        if isinstance(result, FeatureExecutionAdvisory):
            warning = result.code
            detail = result.message
        else:
            warning = result.get("warning")
            detail = result.get("message") or "Request cannot be processed"

        if warning == "insufficient_credits":
            return PaymentRequiredError(detail)
        if warning == "concurrency_limit":
            return TooManyRequestsError(detail)
        if warning in {"workspace_locked", "literature_insufficient"}:
            return ConflictError(detail)
        return BadRequestError(detail)

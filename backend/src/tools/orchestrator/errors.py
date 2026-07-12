"""Explicit ToolOrchestrator failures; none downgrade to model prose."""

from __future__ import annotations

from src.tools.orchestrator.contracts import ToolErrorType


class ToolOrchestratorError(RuntimeError):
    pass


class UnknownToolError(ToolOrchestratorError):
    pass


class MalformedToolArgumentsError(ToolOrchestratorError):
    pass


class StaleToolLeaseError(ToolOrchestratorError):
    pass


class ToolOperationInProgressError(ToolOrchestratorError):
    pass


class ToolDispatchError(ToolOrchestratorError):
    def __init__(
        self,
        error_type: ToolErrorType,
        user_safe_summary: str,
        *,
        recoverable_by_model: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(user_safe_summary)
        self.error_type = error_type
        self.user_safe_summary = user_safe_summary
        self.recoverable_by_model = recoverable_by_model
        self.retry_after_seconds = retry_after_seconds


__all__ = [
    "MalformedToolArgumentsError",
    "StaleToolLeaseError",
    "ToolDispatchError",
    "ToolOperationInProgressError",
    "ToolOrchestratorError",
    "UnknownToolError",
]

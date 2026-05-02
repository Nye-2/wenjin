"""Chat → Compute bridge service.

This module provides the canonical dispatch layer from the Chat/Agent control
plane to the Compute work-plane.  All execution tool calls that originate in
Agent middleware must route through this service so that Compute operations are
not scattered across the control plane.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.execution.types import ExecutionRequest, ExecutionResult

if TYPE_CHECKING:
    from src.execution.base import ExecutionService


class ComputeDispatchService:
    """Bridge from Chat control plane to Compute work-plane.

    Wraps the underlying ``ExecutionService`` to provide a single, named entry
    point for all compute dispatches.  This makes the control-plane →
    work-plane boundary explicit and auditable.
    """

    def __init__(self, execution_service: "ExecutionService") -> None:
        """Initialize with an execution service instance.

        Args:
            execution_service: Concrete ``ExecutionService`` implementation.
        """
        self._execution_service = execution_service

    async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
        """Dispatch an execution request to the Compute work-plane.

        Args:
            request: Structured execution request.

        Returns:
            Execution result from the provider.
        """
        return await self._execution_service.execute(request)

"""Run history projection service backed by DataService executions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.execution_api import (
    ExecutionDataService,
    ExecutionRunHistoryProjection,
)


class RunHistoryService:
    """Read run history as a projection from canonical execution state."""

    def __init__(
        self,
        db: AsyncSession,
        model: Any | None = None,
    ) -> None:
        self.db = db
        self._execution = ExecutionDataService(db, autocommit=True)

    async def record(
        self,
        workspace_id: str,
        execution_id: str,
        capability_id: str,
        title: str,
        summary: str,
        status: str,
        duration_seconds: int,
        token_usage: dict[str, Any] | None = None,
        artifact_count: int = 0,
    ) -> ExecutionRunHistoryProjection | None:
        """Record a run-history event and return the derived projection."""
        await self._execution.record_event(
            execution_id=execution_id,
            workspace_id=workspace_id,
            event_type="execution.run_history",
            payload_json={
                "capability_id": capability_id,
                "title": title,
                "summary": summary,
                "status": status,
                "duration_seconds": duration_seconds,
                "token_usage": token_usage or {},
                "artifact_count": artifact_count,
            },
        )
        return await self.get(workspace_id, execution_id)

    async def list(
        self,
        workspace_id: str,
        limit: int = 50,
    ) -> list[ExecutionRunHistoryProjection]:
        """List run history projection rows ordered by execution creation."""
        return await self._execution.list_run_history(
            workspace_id=workspace_id,
            limit=limit,
        )

    async def get(
        self,
        workspace_id: str,
        run_id: str,
    ) -> ExecutionRunHistoryProjection | None:
        """Get one run history projection row by execution id."""
        return await self._execution.get_run_history_item(
            workspace_id=workspace_id,
            run_id=run_id,
        )

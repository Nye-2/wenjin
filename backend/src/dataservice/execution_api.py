"""Public in-process execution API for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.execution.contracts import (
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionEventProjection,
    ExecutionNodeProjection,
    ExecutionRecordProjection,
    ExecutionUpdateCommand,
)
from src.dataservice.domains.execution.service import DataServiceExecutionService


class ExecutionDataService:
    """Execution API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceExecutionService(session, autocommit=autocommit)

    async def create_execution(self, command: ExecutionCreateCommand) -> ExecutionRecordProjection:
        return await self._domain.create_execution(command)

    async def get_execution(self, execution_id: str) -> ExecutionRecordProjection | None:
        return await self._domain.get_execution(execution_id)

    async def list_executions(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        execution_type: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ExecutionRecordProjection]:
        return await self._domain.list_executions(
            user_id=user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            execution_type=execution_type,
            status=status,
            limit=limit,
        )

    async def update_execution(
        self,
        execution_id: str,
        command: ExecutionUpdateCommand,
    ) -> ExecutionRecordProjection | None:
        return await self._domain.update_execution(execution_id, command)

    async def list_nodes(self, execution_id: str) -> list[ExecutionNodeProjection]:
        return await self._domain.list_nodes(execution_id)

    async def append_event(
        self,
        execution_id: str,
        command: ExecutionEventCreateCommand,
    ) -> ExecutionEventProjection:
        return await self._domain.append_event(execution_id, command)

    async def record_event(
        self,
        *,
        execution_id: str,
        event_type: str,
        workspace_id: str | None = None,
        node_id: str | None = None,
        payload_json: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> ExecutionEventProjection:
        return await self._domain.append_event(
            execution_id,
            ExecutionEventCreateCommand(
                event_type=event_type,
                workspace_id=workspace_id,
                node_id=node_id,
                payload_json=dict(payload_json or {}),
                occurred_at=occurred_at,
            ),
        )

    async def list_events(self, execution_id: str) -> list[ExecutionEventProjection]:
        return await self._domain.list_events(execution_id)

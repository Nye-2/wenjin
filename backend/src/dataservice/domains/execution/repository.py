"""Execution aggregate repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.execution import ExecutionRecord
from src.database.models.execution_node import ExecutionNodeRecord
from src.dataservice.domains.execution.models import ExecutionEventRecord


class ExecutionRepository:
    """Persistence operations for execution aggregate rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_execution(self, values: dict[str, Any]) -> ExecutionRecord:
        record = ExecutionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        result = await self.session.execute(
            select(ExecutionRecord).where(ExecutionRecord.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        execution_type: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ExecutionRecord]:
        query = select(ExecutionRecord).order_by(ExecutionRecord.created_at.desc()).limit(limit)
        if user_id is not None:
            query = query.where(ExecutionRecord.user_id == user_id)
        if workspace_id is not None:
            query = query.where(ExecutionRecord.workspace_id == workspace_id)
        if thread_id is not None:
            query = query.where(ExecutionRecord.thread_id == thread_id)
        if execution_type is not None:
            query = query.where(ExecutionRecord.execution_type == execution_type)
        if status is not None:
            query = query.where(ExecutionRecord.status.in_(status))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_nodes(self, execution_id: str) -> list[ExecutionNodeRecord]:
        result = await self.session.execute(
            select(ExecutionNodeRecord)
            .where(ExecutionNodeRecord.execution_id == execution_id)
            .order_by(ExecutionNodeRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_events(self, execution_id: str) -> list[ExecutionEventRecord]:
        result = await self.session.execute(
            select(ExecutionEventRecord)
            .where(ExecutionEventRecord.execution_id == execution_id)
            .order_by(ExecutionEventRecord.sequence_index.asc())
        )
        return list(result.scalars().all())

    async def next_event_sequence(self, execution_id: str) -> int:
        result = await self.session.execute(
            select(func.max(ExecutionEventRecord.sequence_index)).where(
                ExecutionEventRecord.execution_id == execution_id
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def append_event(
        self,
        *,
        execution_id: str,
        workspace_id: str | None,
        node_id: str | None,
        event_type: str,
        payload_json: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> ExecutionEventRecord:
        record = ExecutionEventRecord(
            id=generate_uuid(),
            execution_id=execution_id,
            workspace_id=workspace_id,
            node_id=node_id,
            event_type=event_type,
            sequence_index=await self.next_event_sequence(execution_id),
            payload_json=payload_json,
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self.session.add(record)
        return record

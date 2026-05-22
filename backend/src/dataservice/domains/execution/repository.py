"""Execution aggregate repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.compute_session import ComputeSessionRecord
from src.database.models.execution import ExecutionRecord
from src.database.models.execution_node import ExecutionNodeRecord
from src.database.models.generation import GenerationRecord
from src.dataservice.domains.execution.models import ExecutionEventRecord


class ExecutionRepository:
    """Persistence operations for execution aggregate rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_execution(self, values: dict[str, Any]) -> ExecutionRecord:
        record = ExecutionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_compute_session(self, values: dict[str, Any]) -> ComputeSessionRecord:
        record = ComputeSessionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_generation_record(self, values: dict[str, Any]) -> GenerationRecord:
        record = GenerationRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_generation_record(self, record_id: str) -> GenerationRecord | None:
        result = await self.session.execute(
            select(GenerationRecord).where(GenerationRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_generation_records(
        self,
        *,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecord]:
        query = (
            select(GenerationRecord)
            .where(GenerationRecord.workspace_id == workspace_id)
            .order_by(GenerationRecord.created_at.desc())
            .limit(limit)
        )
        if skill_name:
            query = query.where(GenerationRecord.skill_name == skill_name)
        if status:
            query = query.where(GenerationRecord.status == status)
        if since:
            query = query.where(GenerationRecord.created_at >= since)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_generation_records_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecord]:
        result = await self.session.execute(
            select(GenerationRecord)
            .where(GenerationRecord.thread_id == thread_id)
            .order_by(GenerationRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_generation_records_before(
        self,
        *,
        cutoff: datetime,
        workspace_id: str | None = None,
    ) -> int:
        query = select(GenerationRecord).where(GenerationRecord.created_at < cutoff)
        if workspace_id is not None:
            query = query.where(GenerationRecord.workspace_id == workspace_id)
        result = await self.session.execute(query)
        records = list(result.scalars().all())
        for record in records:
            await self.session.delete(record)
        return len(records)

    async def get_compute_session(self, compute_session_id: str) -> ComputeSessionRecord | None:
        result = await self.session.execute(
            select(ComputeSessionRecord).where(ComputeSessionRecord.id == compute_session_id)
        )
        return result.scalar_one_or_none()

    async def get_compute_session_by_execution(self, execution_id: str) -> ComputeSessionRecord | None:
        result = await self.session.execute(
            select(ComputeSessionRecord).where(ComputeSessionRecord.execution_id == execution_id)
        )
        return result.scalar_one_or_none()

    async def list_compute_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionRecord]:
        result = await self.session.execute(
            select(ComputeSessionRecord)
            .where(
                ComputeSessionRecord.workspace_id == workspace_id,
                ComputeSessionRecord.user_id == user_id,
            )
            .order_by(ComputeSessionRecord.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        result = await self.session.execute(
            select(ExecutionRecord).where(ExecutionRecord.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def lock_execution(self, execution_id: str) -> None:
        await self.session.execute(
            select(ExecutionRecord)
            .where(ExecutionRecord.id == execution_id)
            .with_for_update()
        )

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

    async def list_executions_by_status(
        self,
        statuses: list[str],
    ) -> list[ExecutionRecord]:
        if not statuses:
            return []
        result = await self.session.execute(
            select(ExecutionRecord)
            .where(ExecutionRecord.status.in_(statuses))
            .order_by(ExecutionRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def count_executions(
        self,
        *,
        user_id: str | None = None,
        status: list[str] | None = None,
        created_since: datetime | None = None,
    ) -> int:
        query = select(func.count()).select_from(ExecutionRecord)
        if user_id is not None:
            query = query.where(ExecutionRecord.user_id == user_id)
        if status is not None:
            query = query.where(ExecutionRecord.status.in_(status))
        if created_since is not None:
            query = query.where(ExecutionRecord.created_at >= created_since)
        result = await self.session.execute(query)
        return int(result.scalar() or 0)

    async def count_executions_by_status(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, int]:
        query = select(ExecutionRecord.status, func.count()).group_by(ExecutionRecord.status)
        if user_id is not None:
            query = query.where(ExecutionRecord.user_id == user_id)
        result = await self.session.execute(query)
        return {str(status): int(count) for status, count in result.all()}

    async def count_executions_by_user_ids(
        self,
        user_ids: list[str],
    ) -> dict[str, int]:
        if not user_ids:
            return {}
        result = await self.session.execute(
            select(ExecutionRecord.user_id, func.count())
            .where(ExecutionRecord.user_id.in_(user_ids))
            .group_by(ExecutionRecord.user_id)
        )
        return {str(user_id): int(count) for user_id, count in result.all()}

    async def count_distinct_execution_users(
        self,
        *,
        created_since: datetime,
    ) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(ExecutionRecord.user_id))).where(
                ExecutionRecord.created_at >= created_since
            )
        )
        return int(result.scalar() or 0)

    async def list_execution_stat_buckets(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ) -> list[Any]:
        bucket_col = func.date_trunc(granularity, ExecutionRecord.created_at).label("bucket")
        workspace_type_col = ExecutionRecord.workspace_type.label("workspace_type")
        status_col = ExecutionRecord.status.label("status")
        result = await self.session.execute(
            select(
                bucket_col,
                workspace_type_col,
                status_col,
                func.count().label("count"),
            )
            .where(ExecutionRecord.created_at >= created_since)
            .group_by(bucket_col, workspace_type_col, status_col)
            .order_by(bucket_col)
        )
        return list(result.all())

    async def count_executions_by_workspace_type(
        self,
        *,
        created_since: datetime,
    ) -> dict[str, int]:
        result = await self.session.execute(
            select(ExecutionRecord.workspace_type, func.count())
            .where(ExecutionRecord.created_at >= created_since)
            .group_by(ExecutionRecord.workspace_type)
        )
        return {
            str(workspace_type or "unknown"): int(count)
            for workspace_type, count in result.all()
        }

    async def count_running_feature_executions(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ExecutionRecord)
            .where(ExecutionRecord.workspace_id == workspace_id)
            .where(ExecutionRecord.feature_id == capability_id)
            .where(ExecutionRecord.execution_type == "feature")
            .where(ExecutionRecord.status.in_(["pending", "running", "awaiting_user_input"]))
        )
        return int(result.scalar() or 0)

    async def get_latest_feature_execution_status(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> str | None:
        result = await self.session.execute(
            select(ExecutionRecord.status)
            .where(ExecutionRecord.workspace_id == workspace_id)
            .where(ExecutionRecord.feature_id == capability_id)
            .where(ExecutionRecord.execution_type == "feature")
            .order_by(ExecutionRecord.created_at.desc())
            .limit(1)
        )
        status = result.scalar_one_or_none()
        return str(status) if status is not None else None

    async def list_nodes(self, execution_id: str) -> list[ExecutionNodeRecord]:
        result = await self.session.execute(
            select(ExecutionNodeRecord)
            .where(ExecutionNodeRecord.execution_id == execution_id)
            .order_by(ExecutionNodeRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_nodes_by_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[ExecutionNodeRecord]:
        if not execution_ids:
            return []
        result = await self.session.execute(
            select(ExecutionNodeRecord)
            .where(ExecutionNodeRecord.execution_id.in_(execution_ids))
            .order_by(ExecutionNodeRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_node_by_node_id(
        self,
        *,
        execution_id: str,
        node_id: str,
    ) -> ExecutionNodeRecord | None:
        result = await self.session.execute(
            select(ExecutionNodeRecord).where(
                ExecutionNodeRecord.execution_id == execution_id,
                ExecutionNodeRecord.node_id == node_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_node_by_record_id(self, node_record_id: str) -> ExecutionNodeRecord | None:
        result = await self.session.execute(
            select(ExecutionNodeRecord).where(ExecutionNodeRecord.id == node_record_id)
        )
        return result.scalar_one_or_none()

    def create_node(self, values: dict[str, Any]) -> ExecutionNodeRecord:
        record = ExecutionNodeRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

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

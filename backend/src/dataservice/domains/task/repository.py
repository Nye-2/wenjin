"""Task persistence repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.task import TaskRecord


class TaskRepository:
    """DataService-owned persistence operations for task records."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        record_model: Any | None = None,
    ) -> None:
        self.session = session
        self.record_model = record_model or TaskRecord

    def create_task_record(self, values: dict[str, Any]) -> Any:
        record = self.record_model(**values)
        self.session.add(record)
        return record

    async def get_task_record(self, task_id: str) -> Any | None:
        result = await self.session.execute(
            select(self.record_model).where(self.record_model.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_user_tasks(
        self,
        *,
        user_id: str,
        status: str | list[str] | tuple[str, ...] | None = None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
        feature_id: str | None = None,
        action: str | None = None,
    ) -> list[Any]:
        query = select(self.record_model).where(self.record_model.user_id == user_id)

        if isinstance(status, str):
            normalized_status = status.strip()
            if normalized_status:
                query = query.where(self.record_model.status == normalized_status)
        elif isinstance(status, (list, tuple)):
            normalized_statuses = [
                str(item).strip()
                for item in status
                if isinstance(item, str) and str(item).strip()
            ]
            if normalized_statuses:
                query = query.where(self.record_model.status.in_(normalized_statuses))
        if task_type:
            query = query.where(self.record_model.task_type == task_type)
        if workspace_id is not None:
            query = query.where(self.record_model.workspace_id == workspace_id)
        if feature_id is not None:
            query = query.where(self.record_model.feature_id == feature_id)
        if action is not None:
            query = query.where(self.record_model.action == action)

        result = await self.session.execute(
            query.order_by(self.record_model.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def count_tasks(
        self,
        *,
        user_id: str,
        statuses: list[str],
    ) -> int:
        result = await self.session.execute(
            select(sa_func.count())
            .select_from(self.record_model)
            .where(
                self.record_model.user_id == user_id,
                self.record_model.status.in_(statuses),
            )
        )
        return int(result.scalar() or 0)

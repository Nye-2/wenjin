"""Public in-process task persistence API for DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.task.contracts import (
    TaskRecordCreateCommand,
    TaskRecordPatchCommand,
    TaskRecordProjection,
)
from src.dataservice.domains.task.service import DataServiceTaskService


class TaskDataService:
    """Task-record API exposed by DataService to runtime modules."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        autocommit: bool = True,
        record_model: Any | None = None,
    ) -> None:
        self._domain = DataServiceTaskService(
            session,
            autocommit=autocommit,
            record_model=record_model,
        )

    async def create_task_record(
        self,
        *,
        task_id: str,
        user_id: str,
        task_type: str,
        priority: int,
        payload: dict[str, Any],
    ) -> TaskRecordProjection:
        return await self._domain.create_task_record(
            TaskRecordCreateCommand(
                task_id=task_id,
                user_id=user_id,
                task_type=task_type,
                priority=priority,
                payload=dict(payload or {}),
            )
        )

    async def create_task_record_guarded(
        self,
        *,
        task_id: str,
        user_id: str,
        task_type: str,
        priority: int,
        payload: dict[str, Any],
        concurrency_limit: int,
        active_statuses: list[str],
    ) -> tuple[TaskRecordProjection | None, int]:
        return await self._domain.create_task_record_guarded(
            command=TaskRecordCreateCommand(
                task_id=task_id,
                user_id=user_id,
                task_type=task_type,
                priority=priority,
                payload=dict(payload or {}),
            ),
            concurrency_limit=concurrency_limit,
            active_statuses=active_statuses,
        )

    async def get_task_record(self, task_id: str) -> TaskRecordProjection | None:
        return await self._domain.get_task_record(task_id)

    async def update_task_record(
        self,
        task_id: str,
        **updates: Any,
    ) -> TaskRecordProjection | None:
        return await self._domain.update_task_record(
            task_id,
            TaskRecordPatchCommand(**updates),
        )

    async def list_user_tasks(
        self,
        *,
        user_id: str,
        status: str | list[str] | tuple[str, ...] | None = None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
    ) -> list[TaskRecordProjection]:
        return await self._domain.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
            workspace_id=workspace_id,
        )

    async def count_active_tasks(
        self,
        *,
        user_id: str,
        active_statuses: list[str],
    ) -> int:
        return await self._domain.count_active_tasks(
            user_id=user_id,
            active_statuses=active_statuses,
        )

    async def mark_task_started(
        self,
        *,
        task_id: str,
        started_at: datetime,
    ) -> TaskRecordProjection | None:
        return await self._domain.update_task_record(
            task_id,
            TaskRecordPatchCommand(status="running", started_at=started_at),
        )

    async def persist_runtime_state(
        self,
        *,
        task_id: str,
        runtime_state: dict[str, Any] | None,
    ) -> TaskRecordProjection | None:
        updates: dict[str, Any] = {}
        if runtime_state is not None:
            updates["runtime_state"] = runtime_state
        return await self._domain.update_task_record(
            task_id,
            TaskRecordPatchCommand(**updates),
        )

    async def mark_task_completed(
        self,
        *,
        task_id: str,
        status: str,
        result: dict[str, Any] | None,
        error: str | None,
        completed_at: datetime,
        progress: int,
        message: str | None,
        runtime_state: dict[str, Any] | None,
    ) -> TaskRecordProjection | None:
        return await self._domain.update_task_record(
            task_id,
            TaskRecordPatchCommand(
                status=status,
                result=result,
                error=error,
                completed_at=completed_at,
                progress=progress,
                message=message,
                runtime_state=runtime_state,
            ),
        )

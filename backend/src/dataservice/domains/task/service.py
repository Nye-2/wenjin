"""Task persistence command/query service."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.task.contracts import (
    TaskRecordCreateCommand,
    TaskRecordPatchCommand,
    TaskRecordProjection,
)
from src.dataservice.domains.task.projection import task_record_to_projection
from src.dataservice.domains.task.repository import TaskRepository


class DataServiceTaskService:
    """DataService-owned task-record operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        autocommit: bool = True,
        record_model: Any | None = None,
    ) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = TaskRepository(session, record_model=record_model)

    @staticmethod
    def advisory_lock_key(user_id: str) -> int:
        """Derive a stable signed bigint lock key for per-user task submission."""
        digest = hashlib.blake2b(user_id.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    async def create_task_record(
        self,
        command: TaskRecordCreateCommand,
    ) -> TaskRecordProjection:
        values = self._create_values(command)
        record = self.repository.create_task_record(values)
        await self._finish(record)
        return task_record_to_projection(record)

    async def create_task_record_guarded(
        self,
        *,
        command: TaskRecordCreateCommand,
        concurrency_limit: int,
        active_statuses: list[str],
    ) -> tuple[TaskRecordProjection | None, int]:
        tx = self.session.begin_nested() if self.session.in_transaction() else self.session.begin()
        async with tx:
            bind = self.session.get_bind()
            if bind is not None and bind.dialect.name == "postgresql":
                await self.session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": self.advisory_lock_key(command.user_id)},
                )

            active_count = await self.repository.count_tasks(
                user_id=command.user_id,
                statuses=active_statuses,
            )
            if active_count >= concurrency_limit:
                return None, active_count

            record = self.repository.create_task_record(self._create_values(command))
            await self.session.flush()

        await self.session.refresh(record)
        return task_record_to_projection(record), active_count

    async def get_task_record(self, task_id: str) -> TaskRecordProjection | None:
        record = await self.repository.get_task_record(task_id)
        return task_record_to_projection(record) if record else None

    async def update_task_record(
        self,
        task_id: str,
        patch: TaskRecordPatchCommand,
    ) -> TaskRecordProjection | None:
        record = await self.repository.get_task_record(task_id)
        if record is None:
            return None

        self._apply_patch(record, patch)
        await self._finish(record)
        return task_record_to_projection(record)

    async def list_user_tasks(
        self,
        *,
        user_id: str,
        status: str | list[str] | tuple[str, ...] | None = None,
        task_type: str | None = None,
        limit: int = 20,
        workspace_id: str | None = None,
    ) -> list[TaskRecordProjection]:
        return [
            task_record_to_projection(record)
            for record in await self.repository.list_user_tasks(
                user_id=user_id,
                status=status,
                task_type=task_type,
                limit=limit,
                workspace_id=workspace_id,
            )
        ]

    async def count_active_tasks(
        self,
        *,
        user_id: str,
        active_statuses: list[str],
    ) -> int:
        return await self.repository.count_tasks(
            user_id=user_id,
            statuses=active_statuses,
        )

    @staticmethod
    def _create_values(command: TaskRecordCreateCommand) -> dict[str, Any]:
        payload = command.payload or {}
        return {
            "id": command.task_id,
            "user_id": command.user_id,
            "task_type": command.task_type,
            "status": command.status,
            "priority": command.priority,
            "payload": payload,
            "workspace_id": payload.get("workspace_id"),
            "thread_id": payload.get("thread_id"),
            "mission_id": payload.get("mission_id"),
        }

    @staticmethod
    def _apply_patch(record: Any, patch: TaskRecordPatchCommand) -> None:
        for key, value in patch.model_dump(exclude_unset=True).items():
            if hasattr(record, key):
                setattr(record, key, value)

    async def _finish(self, record: Any) -> None:
        if self.autocommit:
            await self.session.commit()
            await self.session.refresh(record)
            return
        await self.session.flush()

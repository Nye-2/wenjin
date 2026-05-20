"""Execution aggregate command/query service."""

from __future__ import annotations

from datetime import UTC, datetime
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
from src.dataservice.domains.execution.projection import (
    event_to_projection,
    execution_to_projection,
    node_to_projection,
)
from src.dataservice.domains.execution.repository import ExecutionRepository


class DataServiceExecutionService:
    """DataService-owned execution operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ExecutionRepository(session)

    async def create_execution(self, command: ExecutionCreateCommand) -> ExecutionRecordProjection:
        now = datetime.now(UTC)
        record = self.repository.create_execution(
            {
                "user_id": command.user_id,
                "workspace_id": command.workspace_id,
                "thread_id": command.thread_id,
                "execution_type": command.execution_type,
                "feature_id": command.capability_id,
                "entry_skill_id": command.entry_skill_id,
                "workspace_type": command.workspace_type,
                "display_name": command.display_name,
                "status": "pending",
                "params": dict(command.task_brief_json or {}),
                "parent_execution_id": command.parent_execution_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._finish()
        return execution_to_projection(record)

    async def get_execution(self, execution_id: str) -> ExecutionRecordProjection | None:
        record = await self.repository.get_execution(execution_id)
        return execution_to_projection(record) if record else None

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
        return [
            execution_to_projection(record)
            for record in await self.repository.list_executions(
                user_id=user_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                execution_type=execution_type,
                status=status,
                limit=limit,
            )
        ]

    async def update_execution(
        self,
        execution_id: str,
        command: ExecutionUpdateCommand,
    ) -> ExecutionRecordProjection | None:
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return None
        changed = self._apply_update(record, command)
        if changed:
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return execution_to_projection(record)

    async def list_nodes(self, execution_id: str) -> list[ExecutionNodeProjection]:
        return [
            node_to_projection(record)
            for record in await self.repository.list_nodes(execution_id)
        ]

    async def append_event(
        self,
        execution_id: str,
        command: ExecutionEventCreateCommand,
    ) -> ExecutionEventProjection:
        record = await self.repository.append_event(
            execution_id=execution_id,
            workspace_id=command.workspace_id,
            node_id=command.node_id,
            event_type=command.event_type,
            payload_json=dict(command.payload_json or {}),
            occurred_at=command.occurred_at,
        )
        await self._finish()
        return event_to_projection(record)

    async def list_events(self, execution_id: str) -> list[ExecutionEventProjection]:
        return [
            event_to_projection(record)
            for record in await self.repository.list_events(execution_id)
        ]

    @staticmethod
    def _apply_update(record: Any, command: ExecutionUpdateCommand) -> bool:
        changed = False
        mapping = {
            "status": "status",
            "thread_id": "thread_id",
            "entry_skill_id": "entry_skill_id",
            "workspace_type": "workspace_type",
            "display_name": "display_name",
            "task_brief_json": "params",
            "result_json": "result",
            "error_text": "error",
            "result_summary": "result_summary",
            "graph_json": "graph_structure",
            "node_states_json": "node_states",
            "runtime_state_json": "runtime_state",
            "progress": "progress",
            "message": "message",
            "artifact_ids": "artifact_ids",
            "next_actions": "next_actions",
            "advisory_code": "advisory_code",
            "last_error": "last_error",
            "dispatch_mode": "dispatch_mode",
            "worker_task_id": "worker_task_id",
            "started_at": "started_at",
            "completed_at": "completed_at",
        }
        data = command.model_dump(exclude_unset=True)
        for command_key, record_key in mapping.items():
            if command_key not in data:
                continue
            value = data[command_key]
            if getattr(record, record_key) != value:
                setattr(record, record_key, value)
                changed = True
        return changed

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

"""Execution aggregate command/query service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.execution.contracts import (
    ComputeSessionEnsureCommand,
    ComputeSessionProjection,
    ComputeSessionUpdateCommand,
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionEventProjection,
    ExecutionNodePatchCommand,
    ExecutionNodeProjection,
    ExecutionNodeUpsertCommand,
    ExecutionRecordProjection,
    ExecutionRunHistoryProjection,
    ExecutionUpdateCommand,
)
from src.dataservice.domains.execution.projection import (
    compute_session_to_projection,
    event_to_projection,
    execution_to_projection,
    execution_to_run_history_projection,
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
                "node_states": {},
                "progress": 0,
                "artifact_ids": [],
                "next_actions": [],
                "child_execution_ids": [],
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

    async def count_executions(
        self,
        *,
        user_id: str | None = None,
        status: list[str] | None = None,
        created_since: datetime | None = None,
    ) -> int:
        return await self.repository.count_executions(
            user_id=user_id,
            status=status,
            created_since=created_since,
        )

    async def count_executions_by_status(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, int]:
        return await self.repository.count_executions_by_status(user_id=user_id)

    async def count_executions_by_user_ids(
        self,
        user_ids: list[str],
    ) -> dict[str, int]:
        return await self.repository.count_executions_by_user_ids(user_ids)

    async def reconcile_interrupted_executions(self) -> int:
        """Mark stale in-flight executions terminal after process restart."""
        records = await self.repository.list_executions_by_status(
            ["pending", "running", "cancelling"]
        )
        if not records:
            return 0

        now = datetime.now(UTC)
        interrupted_summary = "Execution interrupted by process restart"
        for record in records:
            if record.status == "cancelling":
                record.status = "cancelled"
                if not record.result_summary:
                    record.result_summary = interrupted_summary
                if not record.error:
                    record.error = interrupted_summary
                if not record.last_error:
                    record.last_error = interrupted_summary
            else:
                record.status = "failed"
                record.error = interrupted_summary
                record.last_error = interrupted_summary
                record.result_summary = interrupted_summary
            record.completed_at = record.completed_at or now
            record.updated_at = now

        await self._finish()
        return len(records)

    async def ensure_compute_session(
        self,
        command: ComputeSessionEnsureCommand,
    ) -> tuple[ComputeSessionProjection, bool]:
        existing = await self.repository.get_compute_session_by_execution(command.execution_id)
        if existing is not None:
            changed = False
            if command.sandbox_session_id and existing.sandbox_session_id != command.sandbox_session_id:
                existing.sandbox_session_id = command.sandbox_session_id
                existing.updated_at = datetime.now(UTC)
                changed = True
            if changed:
                await self._finish()
            return compute_session_to_projection(existing), changed

        now = datetime.now(UTC)
        record = self.repository.create_compute_session(
            {
                "execution_id": command.execution_id,
                "workspace_id": command.workspace_id,
                "user_id": command.user_id,
                "sandbox_session_id": command.sandbox_session_id,
                "active_view": "overview",
                "ui_state": {},
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._finish()
        return compute_session_to_projection(record), True

    async def get_compute_session(
        self,
        compute_session_id: str,
    ) -> ComputeSessionProjection | None:
        record = await self.repository.get_compute_session(compute_session_id)
        return compute_session_to_projection(record) if record is not None else None

    async def get_compute_session_by_execution(
        self,
        execution_id: str,
    ) -> ComputeSessionProjection | None:
        record = await self.repository.get_compute_session_by_execution(execution_id)
        return compute_session_to_projection(record) if record is not None else None

    async def list_compute_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionProjection]:
        return [
            compute_session_to_projection(record)
            for record in await self.repository.list_compute_sessions(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=limit,
            )
        ]

    async def update_compute_session(
        self,
        compute_session_id: str,
        command: ComputeSessionUpdateCommand,
    ) -> ComputeSessionProjection | None:
        record = await self.repository.get_compute_session(compute_session_id)
        if record is None:
            return None
        changed = False
        if "sandbox_session_id" in command.model_fields_set and command.sandbox_session_id != record.sandbox_session_id:
            record.sandbox_session_id = command.sandbox_session_id
            changed = True
        if command.active_view is not None and command.active_view != record.active_view:
            record.active_view = command.active_view
            changed = True
        if command.ui_state is not None and command.ui_state != dict(record.ui_state or {}):
            record.ui_state = dict(command.ui_state)
            changed = True
        if "ui_state_delta" in command.model_fields_set:
            current_ui = dict(record.ui_state or {})
            current_ui.update(command.ui_state_delta or {})
            record.ui_state = current_ui
            changed = True
        if changed:
            record.updated_at = datetime.now(UTC)
            await self._finish()
        return compute_session_to_projection(record)

    async def list_run_history(
        self,
        *,
        workspace_id: str,
        limit: int = 50,
    ) -> list[ExecutionRunHistoryProjection]:
        return [
            execution_to_run_history_projection(record)
            for record in await self.repository.list_executions(
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    async def get_run_history_item(
        self,
        *,
        workspace_id: str,
        run_id: str,
    ) -> ExecutionRunHistoryProjection | None:
        record = await self.repository.get_execution(run_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        return execution_to_run_history_projection(record)

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

    async def list_nodes_by_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[ExecutionNodeProjection]:
        return [
            node_to_projection(record)
            for record in await self.repository.list_nodes_by_execution_ids(execution_ids)
        ]

    async def get_node_by_record_id(
        self,
        node_record_id: str,
    ) -> ExecutionNodeProjection | None:
        record = await self.repository.get_node_by_record_id(node_record_id)
        return node_to_projection(record) if record else None

    async def find_node_by_node_id(
        self,
        *,
        execution_id: str,
        node_id: str,
    ) -> ExecutionNodeProjection | None:
        record = await self.repository.get_node_by_node_id(
            execution_id=execution_id,
            node_id=node_id,
        )
        return node_to_projection(record) if record else None

    async def upsert_node(
        self,
        execution_id: str,
        command: ExecutionNodeUpsertCommand,
    ) -> ExecutionNodeProjection:
        record = await self.repository.get_node_by_node_id(
            execution_id=execution_id,
            node_id=command.node_id,
        )
        now = datetime.now(UTC)
        if record is None:
            record = self.repository.create_node(
                {
                    "execution_id": execution_id,
                    "parent_node_id": command.parent_node_id,
                    "node_id": command.node_id,
                    "node_type": command.node_type,
                    "label": command.label,
                    "status": command.status,
                    "input_data": command.input_data,
                    "output_data": command.output_data,
                    "thinking": command.thinking,
                    "tool_calls": command.tool_calls,
                    "token_usage": command.token_usage,
                    "node_metadata": command.node_metadata,
                    "started_at": command.started_at,
                    "completed_at": command.completed_at,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        else:
            self._apply_node_upsert(record, command)
            record.updated_at = now
        await self._finish()
        return node_to_projection(record)

    async def update_node(
        self,
        node_record_id: str,
        command: ExecutionNodePatchCommand,
    ) -> ExecutionNodeProjection | None:
        record = await self.repository.get_node_by_record_id(node_record_id)
        if record is None:
            return None
        changed = self._apply_node_patch(record, command)
        if changed:
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return node_to_projection(record)

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

    @staticmethod
    def _apply_node_upsert(record: Any, command: ExecutionNodeUpsertCommand) -> None:
        record.node_type = command.node_type
        if command.label is not None:
            record.label = command.label
        if command.parent_node_id is not None:
            record.parent_node_id = command.parent_node_id
        record.status = command.status
        if command.input_data is not None:
            record.input_data = command.input_data
        if command.output_data is not None:
            record.output_data = command.output_data
        if command.thinking is not None:
            record.thinking = command.thinking
        if command.tool_calls is not None:
            record.tool_calls = command.tool_calls
        if command.token_usage is not None:
            record.token_usage = command.token_usage
        if command.node_metadata is not None:
            record.node_metadata = command.node_metadata
        if command.started_at is not None and record.started_at is None:
            record.started_at = command.started_at
        if command.completed_at is not None:
            record.completed_at = command.completed_at

    @staticmethod
    def _apply_node_patch(record: Any, command: ExecutionNodePatchCommand) -> bool:
        changed = False
        data = command.model_dump(exclude_unset=True)
        for key, value in data.items():
            if getattr(record, key) != value:
                setattr(record, key, value)
                changed = True
        return changed

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

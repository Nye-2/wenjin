"""Public in-process execution API for DataService."""

from __future__ import annotations

from datetime import datetime
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
    GenerationRecordCreateCommand,
    GenerationRecordProjection,
)
from src.dataservice.domains.execution.service import DataServiceExecutionService


class ExecutionDataService:
    """Execution API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceExecutionService(session, autocommit=autocommit)

    async def create_execution(self, command: ExecutionCreateCommand) -> ExecutionRecordProjection:
        return await self._domain.create_execution(command)

    async def create_record(
        self,
        *,
        execution_type: str,
        user_id: str,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        capability_id: str | None = None,
        entry_skill_id: str | None = None,
        workspace_type: str | None = None,
        display_name: str | None = None,
        task_brief_json: dict[str, Any] | None = None,
        parent_execution_id: str | None = None,
    ) -> ExecutionRecordProjection:
        return await self._domain.create_execution(
            ExecutionCreateCommand(
                execution_type=execution_type,
                user_id=user_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                capability_id=capability_id,
                entry_skill_id=entry_skill_id,
                workspace_type=workspace_type,
                display_name=display_name,
                task_brief_json=dict(task_brief_json or {}),
                parent_execution_id=parent_execution_id,
            )
        )

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

    async def count_executions(
        self,
        *,
        user_id: str | None = None,
        status: list[str] | None = None,
        created_since: datetime | None = None,
    ) -> int:
        return await self._domain.count_executions(
            user_id=user_id,
            status=status,
            created_since=created_since,
        )

    async def count_executions_by_status(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, int]:
        return await self._domain.count_executions_by_status(user_id=user_id)

    async def count_executions_by_user_ids(
        self,
        user_ids: list[str],
    ) -> dict[str, int]:
        return await self._domain.count_executions_by_user_ids(user_ids)

    async def count_active_execution_users(self, *, created_since: datetime) -> int:
        return await self._domain.count_active_execution_users(created_since=created_since)

    async def aggregate_execution_stats(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ) -> dict[str, Any]:
        return await self._domain.aggregate_execution_stats(
            created_since=created_since,
            granularity=granularity,
        )

    async def count_running_feature_executions(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> int:
        return await self._domain.count_running_feature_executions(
            workspace_id=workspace_id,
            capability_id=capability_id,
        )

    async def get_latest_feature_execution_status(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> str | None:
        return await self._domain.get_latest_feature_execution_status(
            workspace_id=workspace_id,
            capability_id=capability_id,
        )

    async def reconcile_interrupted_executions(self) -> int:
        return await self._domain.reconcile_interrupted_executions()

    async def create_generation_record(
        self,
        command: GenerationRecordCreateCommand,
    ) -> GenerationRecordProjection:
        return await self._domain.create_generation_record(command)

    async def create_generation_usage(
        self,
        *,
        workspace_id: str,
        skill_name: str,
        thread_id: str | None = None,
        model_name: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        duration_ms: int | None = None,
        token_usage: dict[str, Any] | None = None,
        status: str = "success",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationRecordProjection:
        return await self._domain.create_generation_record(
            GenerationRecordCreateCommand(
                workspace_id=workspace_id,
                skill_name=skill_name,
                thread_id=thread_id,
                model_name=model_name,
                input_summary=input_summary,
                output_summary=output_summary,
                duration_ms=duration_ms,
                token_usage=token_usage,
                status=status,
                error_message=error_message,
                metadata=dict(metadata or {}),
            )
        )

    async def get_generation_record(
        self,
        record_id: str,
    ) -> GenerationRecordProjection | None:
        return await self._domain.get_generation_record(record_id)

    async def list_generation_records(
        self,
        *,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecordProjection]:
        return await self._domain.list_generation_records(
            workspace_id=workspace_id,
            skill_name=skill_name,
            status=status,
            since=since,
            limit=limit,
        )

    async def list_generation_records_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecordProjection]:
        return await self._domain.list_generation_records_by_thread(thread_id)

    async def get_generation_usage_stats(
        self,
        *,
        workspace_id: str,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        return await self._domain.get_generation_usage_stats(
            workspace_id=workspace_id,
            since=since,
        )

    async def cleanup_old_generation_records(
        self,
        *,
        days_old: int = 90,
        workspace_id: str | None = None,
    ) -> int:
        return await self._domain.cleanup_old_generation_records(
            days_old=days_old,
            workspace_id=workspace_id,
        )

    async def ensure_compute_session(
        self,
        *,
        execution_id: str,
        workspace_id: str,
        user_id: str,
        sandbox_session_id: str | None = None,
    ) -> tuple[ComputeSessionProjection, bool]:
        return await self._domain.ensure_compute_session(
            ComputeSessionEnsureCommand(
                execution_id=execution_id,
                workspace_id=workspace_id,
                user_id=user_id,
                sandbox_session_id=sandbox_session_id,
            )
        )

    async def get_compute_session(self, compute_session_id: str) -> ComputeSessionProjection | None:
        return await self._domain.get_compute_session(compute_session_id)

    async def get_compute_session_by_execution(
        self,
        execution_id: str,
    ) -> ComputeSessionProjection | None:
        return await self._domain.get_compute_session_by_execution(execution_id)

    async def list_compute_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionProjection]:
        return await self._domain.list_compute_sessions(
            workspace_id=workspace_id,
            user_id=user_id,
            limit=limit,
        )

    async def update_compute_session(
        self,
        compute_session_id: str,
        **fields: Any,
    ) -> ComputeSessionProjection | None:
        return await self._domain.update_compute_session(
            compute_session_id,
            ComputeSessionUpdateCommand(**fields),
        )

    async def list_run_history(
        self,
        *,
        workspace_id: str,
        limit: int = 50,
    ) -> list[ExecutionRunHistoryProjection]:
        return await self._domain.list_run_history(
            workspace_id=workspace_id,
            limit=limit,
        )

    async def get_run_history_item(
        self,
        *,
        workspace_id: str,
        run_id: str,
    ) -> ExecutionRunHistoryProjection | None:
        return await self._domain.get_run_history_item(
            workspace_id=workspace_id,
            run_id=run_id,
        )

    async def update_execution(
        self,
        execution_id: str,
        command: ExecutionUpdateCommand,
    ) -> ExecutionRecordProjection | None:
        return await self._domain.update_execution(execution_id, command)

    async def update_record(
        self,
        execution_id: str,
        **fields: Any,
    ) -> ExecutionRecordProjection | None:
        return await self._domain.update_execution(
            execution_id,
            ExecutionUpdateCommand(**fields),
        )

    async def list_nodes(self, execution_id: str) -> list[ExecutionNodeProjection]:
        return await self._domain.list_nodes(execution_id)

    async def list_nodes_by_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[ExecutionNodeProjection]:
        return await self._domain.list_nodes_by_execution_ids(execution_ids)

    async def get_node_by_record_id(self, node_record_id: str) -> ExecutionNodeProjection | None:
        return await self._domain.get_node_by_record_id(node_record_id)

    async def find_node_by_node_id(
        self,
        *,
        execution_id: str,
        node_id: str,
    ) -> ExecutionNodeProjection | None:
        return await self._domain.find_node_by_node_id(
            execution_id=execution_id,
            node_id=node_id,
        )

    async def upsert_node(
        self,
        execution_id: str,
        command: ExecutionNodeUpsertCommand,
    ) -> ExecutionNodeProjection:
        return await self._domain.upsert_node(execution_id, command)

    async def upsert_node_record(
        self,
        execution_id: str,
        **fields: Any,
    ) -> ExecutionNodeProjection:
        return await self._domain.upsert_node(
            execution_id,
            ExecutionNodeUpsertCommand(**fields),
        )

    async def update_node(
        self,
        node_record_id: str,
        **fields: Any,
    ) -> ExecutionNodeProjection | None:
        return await self._domain.update_node(
            node_record_id,
            ExecutionNodePatchCommand(**fields),
        )

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

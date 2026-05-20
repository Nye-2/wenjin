"""Execution service — unified lifecycle management for all execution types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.execution import ExecutionRecord
from src.database.models.execution_node import ExecutionNodeRecord
from src.dataservice.execution_api import ExecutionDataService

_UNSET = object()


def _normalize_str_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
      item = str(value or "").strip()
      if not item or item in seen:
          continue
      normalized.append(item)
      seen.add(item)
    return normalized


def _normalize_action_list(values: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for value in values or []:
        if isinstance(value, dict):
            normalized.append(dict(value))
    return normalized


def serialize_execution_record(record: ExecutionRecord) -> dict[str, Any]:
    """Serialize an execution record into the canonical API shape."""
    return {
        "id": record.id,
        "user_id": record.user_id,
        "workspace_id": record.workspace_id,
        "thread_id": record.thread_id,
        "execution_type": record.execution_type,
        "feature_id": record.feature_id,
        "entry_skill_id": record.entry_skill_id,
        "workspace_type": record.workspace_type,
        "display_name": record.display_name,
        "status": record.status,
        "params": dict(record.params or {}),
        "result": record.result,
        "error": record.error,
        "result_summary": record.result_summary,
        "graph_structure": record.graph_structure,
        "node_states": dict(record.node_states or {}),
        "runtime_state": record.runtime_state,
        "progress": record.progress,
        "message": record.message,
        "artifact_ids": list(record.artifact_ids or []),
        "next_actions": list(record.next_actions or []),
        "advisory_code": record.advisory_code,
        "last_error": record.last_error,
        "parent_execution_id": record.parent_execution_id,
        "child_execution_ids": list(record.child_execution_ids or []),
        "dispatch_mode": record.dispatch_mode,
        "worker_task_id": record.worker_task_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


class ExecutionService:
    """CRUD and lifecycle helpers for unified execution records."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        redis: Any | None = None,
        publish_event: Any | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.publish_event = publish_event

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    async def create_execution(
        self,
        *,
        execution_type: str,
        user_id: str,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        feature_id: str | None = None,
        entry_skill_id: str | None = None,
        workspace_type: str | None = None,
        display_name: str | None = None,
        params: dict[str, Any] | None = None,
        parent_execution_id: str | None = None,
        commit: bool = True,
    ):
        return await ExecutionDataService(self.db, autocommit=commit).create_record(
            execution_type=execution_type,
            user_id=user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            capability_id=feature_id,
            entry_skill_id=entry_skill_id,
            workspace_type=workspace_type,
            display_name=display_name,
            task_brief_json=dict(params or {}),
            parent_execution_id=parent_execution_id,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def get_by_id(self, execution_id: str):
        return await ExecutionDataService(self.db, autocommit=False).get_execution(execution_id)

    async def list_executions(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        execution_type: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list:
        return await ExecutionDataService(self.db, autocommit=False).list_executions(
            user_id=user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            execution_type=execution_type,
            status=status,
            limit=limit,
        )

    async def reconcile_interrupted_executions(self) -> int:
        """Mark stale in-flight executions terminal after process restart.

        Current execution workers do not support ownership-based resume, so any
        execution left in a non-terminal state after restart is treated as
        interrupted and closed out conservatively.
        """
        result = await self.db.execute(
            select(ExecutionRecord).where(
                ExecutionRecord.status.in_(["pending", "running", "cancelling"])
            )
        )
        records = list(result.scalars().all())
        if not records:
            return 0

        now = datetime.now(UTC)
        reconciled = 0
        for record in records:
            interrupted_summary = "Execution interrupted by process restart"
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
            reconciled += 1

        await self.db.commit()
        return reconciled

    async def get_execution_graph(self, execution_id: str) -> dict[str, Any]:
        record = await self.get_by_id(execution_id)
        if record is None:
            return {"nodes": [], "edges": []}

        graph_structure = record.graph_structure or {"nodes": [], "edges": []}
        node_states = record.node_states or {}

        # Merge static topology with dynamic node states
        nodes = []
        for node in graph_structure.get("nodes", []):
            node_id = node.get("id")
            state = node_states.get(node_id, {})
            nodes.append({**node, **state})

        return {
            "nodes": nodes,
            "edges": graph_structure.get("edges", []),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def update_execution(
        self,
        execution_id: str,
        *,
        commit: bool = True,
        status: str | None = None,
        thread_id: str | None = None,
        entry_skill_id: str | None = None,
        workspace_type: str | None = None,
        display_name: str | None = None,
        params: dict[str, Any] | None = None,
        result: dict[str, Any] | None | object = _UNSET,
        error: str | None | object = _UNSET,
        result_summary: str | None | object = _UNSET,
        graph_structure: dict[str, Any] | None | object = _UNSET,
        runtime_state: dict[str, Any] | None | object = _UNSET,
        progress: int | None = None,
        message: str | None | object = _UNSET,
        artifact_ids: list[str] | None = None,
        next_actions: list[dict[str, Any]] | None = None,
        advisory_code: str | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
        dispatch_mode: str | None | object = _UNSET,
        worker_task_id: str | None | object = _UNSET,
        started_at: datetime | None | object = _UNSET,
        completed_at: datetime | None | object = _UNSET,
    ) -> ExecutionRecord | None:
        """Update business-state fields on an execution record."""
        fields: dict[str, Any] = {}
        if status is not None:
            fields["status"] = status
        if thread_id is not None:
            fields["thread_id"] = thread_id
        if entry_skill_id is not None:
            fields["entry_skill_id"] = entry_skill_id
        if workspace_type is not None:
            fields["workspace_type"] = workspace_type
        if display_name is not None:
            fields["display_name"] = display_name
        if params is not None:
            fields["task_brief_json"] = dict(params)
        if result is not _UNSET:
            fields["result_json"] = result
        if error is not _UNSET:
            fields["error_text"] = error
        if result_summary is not _UNSET:
            fields["result_summary"] = result_summary
        if graph_structure is not _UNSET:
            fields["graph_json"] = graph_structure
        if runtime_state is not _UNSET:
            fields["runtime_state_json"] = runtime_state
        if progress is not None:
            fields["progress"] = progress
        if message is not _UNSET:
            fields["message"] = message
        if artifact_ids is not None:
            fields["artifact_ids"] = _normalize_str_list(artifact_ids)
        if next_actions is not None:
            fields["next_actions"] = _normalize_action_list(next_actions)
        if advisory_code is not _UNSET:
            fields["advisory_code"] = advisory_code
        if last_error is not _UNSET:
            fields["last_error"] = last_error
        if dispatch_mode is not _UNSET:
            fields["dispatch_mode"] = dispatch_mode
        if worker_task_id is not _UNSET:
            fields["worker_task_id"] = worker_task_id
        if started_at is not _UNSET:
            fields["started_at"] = started_at
        if completed_at is not _UNSET:
            fields["completed_at"] = completed_at
        if not fields:
            return await self.get_by_id(execution_id)
        return await ExecutionDataService(self.db, autocommit=commit).update_record(
            execution_id,
            **fields,
        )

    async def apply_task_transition(
        self,
        execution_id: str,
        *,
        status: str,
        runtime_state: dict[str, Any] | None | object = _UNSET,
        result_summary: str | None | object = _UNSET,
        artifact_ids: list[str] | None = None,
        next_actions: list[dict[str, Any]] | None = None,
        advisory_code: str | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
        started_at: datetime | None | object = _UNSET,
        completed_at: datetime | None | object = _UNSET,
        message: str | None | object = _UNSET,
        progress: int | None = None,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        """Apply task-driven lifecycle updates to the canonical execution record."""
        return await self.update_execution(
            execution_id,
            status=status,
            runtime_state=runtime_state,
            result_summary=result_summary,
            artifact_ids=artifact_ids,
            next_actions=next_actions,
            advisory_code=advisory_code,
            last_error=last_error,
            started_at=started_at,
            completed_at=completed_at,
            message=message,
            progress=progress,
            commit=commit,
        )

    async def start_execution(
        self,
        execution_id: str,
        *,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        return await self.update_execution(
            execution_id,
            status="running",
            started_at=datetime.now(UTC),
            commit=commit,
        )

    async def append_execution_event(
        self,
        execution_id: str,
        event_type: str,
        *,
        workspace_id: str | None = None,
        node_id: str | None = None,
        payload_json: dict[str, Any] | None = None,
        commit: bool = True,
    ):
        """Append an ordered canonical execution event."""
        return await ExecutionDataService(self.db, autocommit=commit).record_event(
            execution_id=execution_id,
            event_type=event_type,
            workspace_id=workspace_id,
            node_id=node_id,
            payload_json=dict(payload_json or {}),
        )

    async def update_node_state(
        self,
        execution_id: str,
        node_id: str,
        *,
        status: str | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        output_preview: str | None = None,
        token_usage: dict[str, Any] | None = None,
        thinking: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        record = await self.get_by_id(execution_id)
        if record is None:
            return None

        node_states = dict(record.node_states or {})
        node_state = dict(node_states.get(node_id, {}))

        if status is not None:
            node_state["status"] = status
        # Full input / output payloads — keys mirror what the
        # ``GET /executions/{id}/nodes/{node_id}`` endpoint returns to the FE.
        if input_data is not None:
            node_state["input"] = input_data
        if output_data is not None:
            node_state["output"] = output_data
        if output_preview is not None:
            node_state["output_preview"] = output_preview
        if token_usage is not None:
            node_state["token_usage"] = token_usage
        if thinking is not None:
            node_state["thinking"] = thinking
        if tool_calls is not None:
            node_state["tool_calls"] = tool_calls
        if started_at is not None:
            node_state["started_at"] = started_at.isoformat()
        if completed_at is not None:
            node_state["completed_at"] = completed_at.isoformat()

        node_states[node_id] = node_state
        return await ExecutionDataService(self.db, autocommit=commit).update_record(
            execution_id,
            node_states_json=node_states,
        )

    async def complete_execution(
        self,
        execution_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        result_summary: str | None = None,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        return await self.update_execution(
            execution_id,
            status=status,
            result=result if result is not None else _UNSET,
            error=error if error is not None else _UNSET,
            result_summary=result_summary if result_summary is not None else _UNSET,
            completed_at=datetime.now(UTC),
            commit=commit,
        )

    async def set_graph_structure(
        self,
        execution_id: str,
        graph_structure: dict[str, Any],
    ) -> None:
        """Persist the computed graph_structure onto the ExecutionRecord."""
        await self.update_execution(execution_id, graph_structure=graph_structure)

    async def append_artifact_id(
        self,
        execution_id: str,
        artifact_id: str,
        *,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        """Associate a newly created artifact with an execution record."""
        record = await self.get_by_id(execution_id)
        if record is None:
            return None

        artifact_ids = list(record.artifact_ids or [])
        normalized_artifact_id = str(artifact_id).strip()
        if normalized_artifact_id and normalized_artifact_id not in artifact_ids:
            artifact_ids.append(normalized_artifact_id)
        return await self.update_execution(
            execution_id,
            artifact_ids=artifact_ids,
            commit=commit,
        )

    async def cancel_execution(
        self,
        execution_id: str,
        *,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        record = await self.get_by_id(execution_id)
        if record is None:
            return None
        if record.status not in ("pending", "running"):
            return record
        updated = await self.update_execution(
            execution_id,
            status="cancelling",
            commit=commit,
        )
        # Write Redis abort signal so the runtime can detect cancellation
        if self.redis is not None:
            try:
                await self.redis.set(f"abort:exec:{execution_id}", "1", ex=300)
            except Exception:
                pass
        # Publish status event
        if self.publish_event is not None:
            try:
                await self.publish_event(
                    execution_id,
                    "execution.status",
                    {"status": "cancelling"},
                )
            except Exception:
                pass
        return updated

    # ------------------------------------------------------------------
    # ExecutionNodeRecord (optional granular persistence)
    # ------------------------------------------------------------------
    async def create_execution_node(
        self,
        *,
        execution_id: str,
        node_id: str,
        node_type: str,
        label: str | None = None,
        input_data: dict[str, Any] | None = None,
        parent_node_id: str | None = None,
        commit: bool = True,
    ) -> ExecutionNodeRecord:
        record = ExecutionNodeRecord(
            id=generate_uuid(),
            execution_id=execution_id,
            node_id=node_id,
            node_type=node_type,
            label=label,
            input_data=input_data,
            parent_node_id=parent_node_id,
            status="pending",
        )
        self.db.add(record)
        if commit:
            await self.db.commit()
            await self.db.refresh(record)
        else:
            await self.db.flush()
        return record

    async def update_execution_node(
        self,
        node_db_id: str,
        *,
        status: str | None = None,
        output_data: dict[str, Any] | None = None,
        thinking: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        token_usage: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        commit: bool = True,
    ) -> ExecutionNodeRecord | None:
        result = await self.db.execute(
            select(ExecutionNodeRecord).where(ExecutionNodeRecord.id == node_db_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        if status is not None:
            record.status = status
        if output_data is not None:
            record.output_data = output_data
        if thinking is not None:
            record.thinking = thinking
        if tool_calls is not None:
            record.tool_calls = tool_calls
        if token_usage is not None:
            record.token_usage = token_usage
        if started_at is not None:
            record.started_at = started_at
        if completed_at is not None:
            record.completed_at = completed_at

        if commit:
            await self.db.commit()
            await self.db.refresh(record)
        return record

    async def find_node_by_node_id(
        self,
        execution_id: str,
        node_id: str,
    ) -> ExecutionNodeRecord | None:
        """Look up an ExecutionNodeRecord by (execution_id, node_id) tuple."""
        result = await self.db.execute(
            select(ExecutionNodeRecord).where(
                ExecutionNodeRecord.execution_id == execution_id,
                ExecutionNodeRecord.node_id == node_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_node_event(
        self,
        *,
        execution_id: str,
        node_id: str,
        node_type: str,
        label: str | None = None,
        status: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        thinking: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        token_usage: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> ExecutionNodeRecord:
        """Upsert an ExecutionNodeRecord for one lifecycle event.

        Used by ``LeadAgentRuntime``'s runner to record running/completed/failed
        transitions so the FE node-detail endpoint returns real state.
        """
        existing = await self.find_node_by_node_id(execution_id, node_id)
        if existing is None:
            record = ExecutionNodeRecord(
                id=generate_uuid(),
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                label=label,
                input_data=input_data,
                status=status,
                output_data=output_data,
                thinking=thinking,
                tool_calls=tool_calls,
                token_usage=token_usage,
                started_at=started_at,
                completed_at=completed_at,
            )
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)
            return record

        if status:
            existing.status = status
        if input_data is not None:
            existing.input_data = input_data
        if output_data is not None:
            existing.output_data = output_data
        if thinking is not None:
            existing.thinking = thinking
        if tool_calls is not None:
            existing.tool_calls = tool_calls
        if token_usage is not None:
            existing.token_usage = token_usage
        if started_at is not None and existing.started_at is None:
            existing.started_at = started_at
        if completed_at is not None:
            existing.completed_at = completed_at
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

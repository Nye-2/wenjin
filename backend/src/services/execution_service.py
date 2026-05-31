"""Execution service — unified lifecycle management for all execution types."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.execution import (
    ExecutionCreatePayload,
    ExecutionEventCreatePayload,
    ExecutionNodePatchPayload,
    ExecutionNodeUpsertPayload,
    ExecutionUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client

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


def _timestamp_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _execution_node_state(record: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "status": record.status,
        "node_type": record.node_type,
        "input": record.input_data,
        "output": record.output_data,
        "thinking": record.thinking,
        "tool_calls": record.tool_calls,
        "token_usage": record.token_usage,
        "node_metadata": record.node_metadata,
        "started_at": _timestamp_or_none(record.started_at),
        "completed_at": _timestamp_or_none(record.completed_at),
    }
    if record.label is not None:
        state["label"] = record.label
    return state


def serialize_execution_record(record: Any) -> dict[str, Any]:
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
        *,
        dataservice: AsyncDataServiceClient | None = None,
        redis: Any | None = None,
        publish_event: Any | None = None,
    ) -> None:
        self._dataservice = dataservice
        self.redis = redis
        self.publish_event = publish_event

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

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
        _ = commit
        async with self._client() as client:
            return await client.create_execution(
                ExecutionCreatePayload(
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
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def get_by_id(self, execution_id: str):
        async with self._client() as client:
            return await client.get_execution(execution_id)

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
        async with self._client() as client:
            return await client.list_executions(
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
        async with self._client() as client:
            return await client.reconcile_interrupted_executions()

    async def get_execution_graph(self, execution_id: str) -> dict[str, Any]:
        record = await self.get_by_id(execution_id)
        if record is None:
            return {"nodes": [], "edges": []}

        graph_structure = record.graph_structure or {"nodes": [], "edges": []}
        async with self._client() as client:
            node_records = await client.list_execution_nodes(execution_id)
        node_states = {node.node_id: _execution_node_state(node) for node in node_records}

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
    ) -> Any | None:
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
        _ = commit
        async with self._client() as client:
            return await client.update_execution(
                execution_id,
                ExecutionUpdatePayload(**fields),
            )

    async def apply_task_transition(
        self,
        execution_id: str,
        *,
        status: str,
        result: dict[str, Any] | None | object = _UNSET,
        error: str | None | object = _UNSET,
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
    ) -> Any | None:
        """Apply task-driven lifecycle updates to the canonical execution record."""
        return await self.update_execution(
            execution_id,
            status=status,
            result=result,
            error=error,
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
    ) -> Any | None:
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
        _ = commit
        async with self._client() as client:
            return await client.append_execution_event(
                execution_id,
                ExecutionEventCreatePayload(
                    event_type=event_type,
                    workspace_id=workspace_id,
                    node_id=node_id,
                    payload_json=dict(payload_json or {}),
                ),
            )

    async def update_node_state(
        self,
        execution_id: str,
        node_id: str,
        *,
        status: str | None = None,
        node_type: str | None = None,
        label: str | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        output_preview: str | None = None,
        token_usage: dict[str, Any] | None = None,
        thinking: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        node_metadata: dict[str, Any] | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        commit: bool = True,
    ) -> Any | None:
        record = await self.get_by_id(execution_id)
        if record is None:
            return None

        node_states = dict(record.node_states or {})
        node_state = dict(node_states.get(node_id, {}))

        if status is not None:
            node_state["status"] = status
        if node_type is not None:
            node_state["node_type"] = node_type
        if label is not None:
            node_state["label"] = label
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
        if node_metadata is not None:
            node_state["node_metadata"] = node_metadata
        if error is not None:
            node_state["error"] = error
        if started_at is not None:
            node_state["started_at"] = started_at.isoformat()
        if completed_at is not None:
            node_state["completed_at"] = completed_at.isoformat()

        node_states[node_id] = node_state
        _ = commit
        async with self._client() as client:
            return await client.update_execution(
                execution_id,
                ExecutionUpdatePayload(node_states_json=node_states),
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
    ) -> Any | None:
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
        """Persist the computed graph_structure onto the canonical execution."""
        await self.update_execution(execution_id, graph_structure=graph_structure)

    async def append_artifact_id(
        self,
        execution_id: str,
        artifact_id: str,
        *,
        commit: bool = True,
    ) -> Any | None:
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
    ) -> Any | None:
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
    # Execution node lifecycle snapshots
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
    ) -> Any:
        _ = commit
        async with self._client() as client:
            return await client.upsert_execution_node(
                execution_id,
                ExecutionNodeUpsertPayload(
                    node_id=node_id,
                    node_type=node_type,
                    label=label,
                    input_data=input_data,
                    parent_node_id=parent_node_id,
                    status="pending",
                ),
            )

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
    ) -> Any | None:
        fields: dict[str, Any] = {}
        if status is not None:
            fields["status"] = status
        if output_data is not None:
            fields["output_data"] = output_data
        if thinking is not None:
            fields["thinking"] = thinking
        if tool_calls is not None:
            fields["tool_calls"] = tool_calls
        if token_usage is not None:
            fields["token_usage"] = token_usage
        if started_at is not None:
            fields["started_at"] = started_at
        if completed_at is not None:
            fields["completed_at"] = completed_at
        _ = commit
        async with self._client() as client:
            if not fields:
                return await client.get_execution_node(node_db_id)
            return await client.update_execution_node(
                node_db_id,
                ExecutionNodePatchPayload(**fields),
            )

    async def find_node_by_node_id(
        self,
        execution_id: str,
        node_id: str,
    ) -> Any | None:
        """Look up an execution node by (execution_id, node_id) tuple."""
        async with self._client() as client:
            return await client.find_execution_node(
                execution_id=execution_id,
                node_id=node_id,
            )

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
        node_metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ):
        """Upsert an execution node lifecycle snapshot.

        Used by ``LeadAgentRuntime``'s runner to record running/completed/failed
        transitions so the FE node-detail endpoint returns real state.
        """
        async with self._client() as client:
            return await client.upsert_execution_node(
                execution_id,
                ExecutionNodeUpsertPayload(
                    node_id=node_id,
                    node_type=node_type,
                    label=label,
                    status=status,
                    input_data=input_data,
                    output_data=output_data,
                    thinking=thinking,
                    tool_calls=tool_calls,
                    token_usage=token_usage,
                    node_metadata=node_metadata,
                    started_at=started_at,
                    completed_at=completed_at,
                ),
            )

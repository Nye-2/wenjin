"""Execution service — unified lifecycle management for all execution types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.execution import ExecutionRecord
from src.database.models.execution_node import ExecutionNodeRecord


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
        params: dict[str, Any] | None = None,
        parent_execution_id: str | None = None,
        commit: bool = True,
    ) -> ExecutionRecord:
        now = datetime.now(UTC)
        record = ExecutionRecord(
            id=generate_uuid(),
            user_id=user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            execution_type=execution_type,
            feature_id=feature_id,
            entry_skill_id=entry_skill_id,
            workspace_type=workspace_type,
            status="pending",
            params=dict(params or {}),
            parent_execution_id=parent_execution_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        if commit:
            await self.db.commit()
            await self.db.refresh(record)
        else:
            await self.db.flush()
        return record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def get_by_id(self, execution_id: str) -> ExecutionRecord | None:
        result = await self.db.execute(
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
        stmt = select(ExecutionRecord).order_by(ExecutionRecord.created_at.desc()).limit(limit)

        if user_id is not None:
            stmt = stmt.where(ExecutionRecord.user_id == user_id)
        if workspace_id is not None:
            stmt = stmt.where(ExecutionRecord.workspace_id == workspace_id)
        if thread_id is not None:
            stmt = stmt.where(ExecutionRecord.thread_id == thread_id)
        if execution_type is not None:
            stmt = stmt.where(ExecutionRecord.execution_type == execution_type)
        if status is not None:
            stmt = stmt.where(ExecutionRecord.status.in_(status))

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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
    async def start_execution(
        self,
        execution_id: str,
        *,
        commit: bool = True,
    ) -> ExecutionRecord | None:
        record = await self.get_by_id(execution_id)
        if record is None:
            return None
        record.status = "running"
        record.started_at = datetime.now(UTC)
        record.updated_at = datetime.now(UTC)
        if commit:
            await self.db.commit()
            await self.db.refresh(record)
        return record

    async def update_node_state(
        self,
        execution_id: str,
        node_id: str,
        *,
        status: str | None = None,
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
        record.node_states = node_states
        record.updated_at = datetime.now(UTC)

        if commit:
            await self.db.commit()
            await self.db.refresh(record)
        return record

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
        record = await self.get_by_id(execution_id)
        if record is None:
            return None
        record.status = status
        if result is not None:
            record.result = result
        if error is not None:
            record.error = error
        if result_summary is not None:
            record.result_summary = result_summary
        record.completed_at = datetime.now(UTC)
        record.updated_at = datetime.now(UTC)
        if commit:
            await self.db.commit()
            await self.db.refresh(record)
        return record

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
        record.status = "cancelling"
        record.updated_at = datetime.now(UTC)
        if commit:
            await self.db.commit()
            await self.db.refresh(record)
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
        return record

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

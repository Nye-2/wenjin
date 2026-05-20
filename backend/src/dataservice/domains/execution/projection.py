"""Execution projection helpers."""

from __future__ import annotations

from src.database.models.execution import ExecutionRecord
from src.database.models.execution_node import ExecutionNodeRecord
from src.dataservice.domains.execution.contracts import (
    ExecutionEventProjection,
    ExecutionNodeProjection,
    ExecutionRecordProjection,
)
from src.dataservice.domains.execution.models import ExecutionEventRecord


def execution_to_projection(record: ExecutionRecord) -> ExecutionRecordProjection:
    return ExecutionRecordProjection(
        id=str(record.id),
        user_id=str(record.user_id),
        workspace_id=record.workspace_id,
        thread_id=record.thread_id,
        execution_type=record.execution_type,
        capability_id=record.feature_id,
        entry_skill_id=record.entry_skill_id,
        workspace_type=record.workspace_type,
        display_name=record.display_name,
        status=record.status,
        task_brief_json=dict(record.params or {}),
        result_json=record.result,
        error_text=record.error,
        result_summary=record.result_summary,
        graph_json=record.graph_structure,
        node_states_json=dict(record.node_states or {}),
        runtime_state_json=record.runtime_state,
        progress=record.progress,
        message=record.message,
        artifact_ids=list(record.artifact_ids or []),
        next_actions=list(record.next_actions or []),
        advisory_code=record.advisory_code,
        last_error=record.last_error,
        parent_execution_id=record.parent_execution_id,
        child_execution_ids=list(record.child_execution_ids or []),
        dispatch_mode=record.dispatch_mode,
        worker_task_id=record.worker_task_id,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
    )


def node_to_projection(record: ExecutionNodeRecord) -> ExecutionNodeProjection:
    return ExecutionNodeProjection(
        id=str(record.id),
        execution_id=str(record.execution_id),
        parent_node_id=record.parent_node_id,
        node_id=record.node_id,
        node_type=record.node_type,
        label=record.label,
        status=record.status,
        input_data=record.input_data,
        output_data=record.output_data,
        thinking=record.thinking,
        tool_calls=record.tool_calls,
        token_usage=record.token_usage,
        node_metadata=record.node_metadata,
        started_at=record.started_at,
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def event_to_projection(record: ExecutionEventRecord) -> ExecutionEventProjection:
    return ExecutionEventProjection(
        id=str(record.id),
        execution_id=str(record.execution_id),
        workspace_id=record.workspace_id,
        node_id=record.node_id,
        event_type=record.event_type,
        sequence_index=record.sequence_index,
        payload_json=dict(record.payload_json or {}),
        occurred_at=record.occurred_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

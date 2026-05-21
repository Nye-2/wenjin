"""Task projection helpers."""

from __future__ import annotations

from typing import Any

from src.dataservice.domains.task.contracts import TaskRecordProjection


def task_record_to_projection(record: Any) -> TaskRecordProjection:
    """Project a task ORM row into the runtime-safe DataService contract."""
    return TaskRecordProjection(
        id=str(record.id),
        user_id=str(record.user_id),
        task_type=str(record.task_type),
        workspace_id=record.workspace_id,
        feature_id=record.feature_id,
        thread_id=record.thread_id,
        execution_id=record.execution_id,
        action=record.action,
        status=str(record.status),
        priority=int(record.priority),
        payload=dict(record.payload or {}),
        result=record.result,
        error=record.error,
        runtime_state=record.runtime_state,
        progress=int(record.progress or 0),
        message=record.message,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )

"""Workspace rooms projection helpers."""

from __future__ import annotations

from src.dataservice.domains.rooms.contracts import (
    DecisionProjection,
    WorkspaceTaskProjection,
)
from src.dataservice.domains.rooms.models import (
    DecisionRecord,
    WorkspaceTaskRecord,
)


def decision_to_projection(record: DecisionRecord) -> DecisionProjection:
    return DecisionProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        key=record.key,
        value=record.value,
        confidence=float(record.confidence),
        source_message_id=record.source_message_id,
        extracted_by=record.extracted_by,
        superseded_by=record.superseded_by,
        source_review_batch_id=getattr(record, "source_review_batch_id", None),
        source_review_item_id=getattr(record, "source_review_item_id", None),
        created_at=record.created_at,
        deleted_at=record.deleted_at,
    )


def workspace_task_to_projection(record: WorkspaceTaskRecord) -> WorkspaceTaskProjection:
    return WorkspaceTaskProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        title=record.title,
        description=record.description,
        status=record.status,
        priority=int(record.priority or 0),
        related_execution_ids=list(record.related_execution_ids or []),
        created_by=record.created_by,
        source_review_batch_id=getattr(record, "source_review_batch_id", None),
        source_review_item_id=getattr(record, "source_review_item_id", None),
        completed_at=record.completed_at,
        deleted_at=record.deleted_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

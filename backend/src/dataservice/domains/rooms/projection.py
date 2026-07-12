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
        source_mission_id=getattr(record, "source_mission_id", None),
        source_mission_item_seq=getattr(record, "source_mission_item_seq", None),
        source_mission_commit_id=getattr(record, "source_mission_commit_id", None),
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
        related_mission_ids=list(record.related_mission_ids or []),
        created_by=record.created_by,
        source_mission_id=getattr(record, "source_mission_id", None),
        source_mission_item_seq=getattr(record, "source_mission_item_seq", None),
        source_mission_commit_id=getattr(record, "source_mission_commit_id", None),
        completed_at=record.completed_at,
        deleted_at=record.deleted_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

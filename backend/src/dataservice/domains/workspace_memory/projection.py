"""Projection helpers for hidden workspace memory documents."""

from __future__ import annotations

from src.dataservice.domains.workspace_memory.contracts import (
    WorkspaceMemoryDocumentProjection,
    WorkspaceMemoryRevisionProjection,
)
from src.dataservice.domains.workspace_memory.models import (
    WorkspaceMemoryDocumentRecord,
    WorkspaceMemoryRevisionRecord,
)


def document_to_projection(record: WorkspaceMemoryDocumentRecord) -> WorkspaceMemoryDocumentProjection:
    return WorkspaceMemoryDocumentProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        content_markdown=record.content_markdown,
        content_hash=record.content_hash,
        revision=int(record.revision or 1),
        updated_by=record.updated_by,
        source_mission_id=record.source_mission_id,
        source_mission_commit_id=record.source_mission_commit_id,
        source_thread_id=record.source_thread_id,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def revision_to_projection(record: WorkspaceMemoryRevisionRecord) -> WorkspaceMemoryRevisionProjection:
    return WorkspaceMemoryRevisionProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        document_id=str(record.document_id),
        revision=int(record.revision or 1),
        content_markdown=record.content_markdown,
        content_hash=record.content_hash,
        update_reason=record.update_reason,
        source_mission_id=record.source_mission_id,
        source_mission_commit_id=record.source_mission_commit_id,
        source_thread_id=record.source_thread_id,
        created_by=record.created_by,
        created_at=record.created_at,
    )

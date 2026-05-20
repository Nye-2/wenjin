"""Review domain projection helpers."""

from __future__ import annotations

from src.dataservice.domains.review.contracts import (
    ReviewActionLogProjection,
    ReviewBatchProjection,
    ReviewItemProjection,
)
from src.dataservice.domains.review.models import (
    ReviewActionLogRecord,
    ReviewBatchRecord,
    ReviewItemRecord,
)


def batch_to_projection(record: ReviewBatchRecord) -> ReviewBatchProjection:
    return ReviewBatchProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        execution_id=record.execution_id,
        source_type=record.source_type,
        source_id=record.source_id,
        review_kind=record.review_kind,
        status=record.status,
        title=record.title,
        summary=record.summary,
        schema_version=record.schema_version,
        item_count=int(record.item_count or 0),
        accepted_count=int(record.accepted_count or 0),
        rejected_count=int(record.rejected_count or 0),
        applied_count=int(record.applied_count or 0),
        failed_count=int(record.failed_count or 0),
        payload_json=dict(record.payload_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def item_to_projection(record: ReviewItemRecord) -> ReviewItemProjection:
    return ReviewItemProjection(
        id=str(record.id),
        batch_id=str(record.batch_id),
        workspace_id=str(record.workspace_id),
        source_item_id=record.source_item_id,
        item_kind=record.item_kind,
        target_domain=record.target_domain,
        target_kind=record.target_kind,
        target_ref_json=dict(record.target_ref_json or {}),
        status=record.status,
        title=record.title,
        summary=record.summary,
        payload_json=dict(record.payload_json or {}),
        preview_json=dict(record.preview_json or {}),
        result_json=record.result_json,
        error_text=record.error_text,
        provenance_json=dict(record.provenance_json or {}),
        sort_order=int(record.sort_order or 0),
        applied_at=record.applied_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def action_log_to_projection(record: ReviewActionLogRecord) -> ReviewActionLogProjection:
    return ReviewActionLogProjection(
        id=str(record.id),
        batch_id=str(record.batch_id),
        item_id=record.item_id,
        workspace_id=str(record.workspace_id),
        action=record.action,
        actor_id=record.actor_id,
        status_from=record.status_from,
        status_to=record.status_to,
        payload_json=dict(record.payload_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

"""Prism projection helpers."""

from __future__ import annotations

from src.dataservice.domains.prism.contracts import (
    PrismDocumentProjection,
    PrismFileProjection,
    PrismFileVersionProjection,
    PrismProjectProjection,
    PrismProtectedScopeProjection,
)
from src.dataservice.domains.prism.models import (
    PrismDocumentRecord,
    PrismFileRecord,
    PrismFileVersionRecord,
    PrismProjectRecord,
    PrismProtectedScopeRecord,
)


def project_to_projection(record: PrismProjectRecord) -> PrismProjectProjection:
    return PrismProjectProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        role=record.role,
        title=record.title,
        adapter_kind=record.adapter_kind,
        adapter_ref_id=record.adapter_ref_id,
        status=record.status,
        settings_json=dict(record.settings_json or {}),
        adapter_metadata_json=dict(record.adapter_metadata_json or {}),
        trashed_at=record.trashed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def document_to_projection(record: PrismDocumentRecord) -> PrismDocumentProjection:
    return PrismDocumentProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        project_id=str(record.project_id),
        document_kind=record.document_kind,
        title=record.title,
        adapter_kind=record.adapter_kind,
        status=record.status,
        root_file_id=record.root_file_id,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def file_to_projection(record: PrismFileRecord) -> PrismFileProjection:
    return PrismFileProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        document_id=str(record.document_id),
        path=record.path,
        file_role=record.file_role,
        mime_type=record.mime_type,
        current_version_id=record.current_version_id,
        content_hash=record.content_hash,
        sort_order=int(record.sort_order or 0),
        metadata_json=dict(record.metadata_json or {}),
        deleted_at=record.deleted_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def version_to_projection(record: PrismFileVersionRecord) -> PrismFileVersionProjection:
    return PrismFileVersionProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        file_id=str(record.file_id),
        version_no=int(record.version_no),
        mission_review_item_id=record.mission_review_item_id,
        mission_commit_id=record.mission_commit_id,
        content_inline=record.content_inline,
        content_asset_id=record.content_asset_id,
        content_hash=record.content_hash,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def protected_scope_to_projection(
    record: PrismProtectedScopeRecord,
) -> PrismProtectedScopeProjection:
    return PrismProtectedScopeProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        project_id=str(record.project_id),
        document_id=record.document_id,
        file_id=record.file_id,
        file_path=record.file_path,
        section_key=record.section_key,
        scope=record.scope,
        reason=record.reason,
        source=record.source,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

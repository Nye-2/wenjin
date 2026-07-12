"""Source projection helpers."""

from __future__ import annotations

from src.dataservice.domains.source.contracts import (
    SourceBibliographySnapshotProjection,
    SourceProjection,
)
from src.dataservice.domains.source.models import SourceBibtexSnapshotRecord, SourceRecord


def source_to_projection(record: SourceRecord) -> SourceProjection:
    return SourceProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        source_kind=record.source_kind,
        title=record.title,
        normalized_title=record.normalized_title,
        authors_json=list(record.authors_json or []),
        year=record.year,
        venue=record.venue,
        publication_type=record.publication_type,
        doi=record.doi,
        url=record.url,
        abstract=record.abstract,
        citation_count=record.citation_count,
        ingest_kind=record.ingest_kind,
        ingest_label=record.ingest_label,
        ingest_mission_id=record.ingest_mission_id,
        ingest_mission_commit_id=record.ingest_mission_commit_id,
        verified_at=record.verified_at,
        library_status=record.library_status,
        evidence_level=record.evidence_level,
        fulltext_status=record.fulltext_status,
        citation_key=record.citation_key,
        bibtex_entry_type=record.bibtex_entry_type,
        bibtex_fields_json=dict(record.bibtex_fields_json or {}),
        read_status=record.read_status,
        tags_json=list(record.tags_json or []),
        notes=record.notes,
        is_deleted=bool(record.is_deleted),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def source_bibtex_snapshot_to_projection(
    record: SourceBibtexSnapshotRecord,
) -> SourceBibliographySnapshotProjection:
    return SourceBibliographySnapshotProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        prism_project_id=record.prism_project_id,
        scope=record.scope,
        content=record.content,
        reference_count=record.reference_count,
        checksum=record.checksum,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

"""Canonical user-facing projection for workspace sources."""

from __future__ import annotations

from typing import Protocol


class SourceProjectionLike(Protocol):
    id: object
    workspace_id: object
    title: object
    normalized_title: object
    authors_json: object
    year: object
    venue: object
    publication_type: object
    doi: object
    url: object
    abstract: object
    citation_count: object
    ingest_kind: object
    ingest_label: object
    ingest_mission_id: object
    ingest_mission_commit_id: object
    verified_at: object
    library_status: object
    evidence_level: object
    fulltext_status: object
    citation_key: object
    bibtex_entry_type: object
    bibtex_fields_json: object
    read_status: object
    tags_json: object
    notes: object
    is_deleted: object
    created_at: object
    updated_at: object


def serialize_source_projection(source: SourceProjectionLike) -> dict[str, object]:
    verified_at = source.verified_at
    created_at = source.created_at
    updated_at = source.updated_at
    return {
        "id": str(source.id),
        "workspace_id": str(source.workspace_id),
        "title": source.title,
        "normalized_title": source.normalized_title,
        "authors": list(source.authors_json or []),
        "year": source.year,
        "venue": source.venue,
        "publication_type": source.publication_type,
        "doi": source.doi,
        "url": source.url,
        "abstract": source.abstract,
        "citation_count": source.citation_count,
        "source_type": source.ingest_kind,
        "source_label": source.ingest_label,
        "source_run_id": source.ingest_mission_id,
        "source_artifact_id": source.ingest_mission_commit_id,
        "verified_at": verified_at.isoformat() if hasattr(verified_at, "isoformat") else None,
        "library_status": source.library_status,
        "evidence_level": source.evidence_level,
        "fulltext_status": source.fulltext_status,
        "citation_key": source.citation_key,
        "bibtex_entry_type": source.bibtex_entry_type,
        "bibtex_fields": dict(source.bibtex_fields_json or {}),
        "read_status": source.read_status,
        "tags": list(source.tags_json or []),
        "notes": source.notes,
        "is_deleted": bool(source.is_deleted),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else None,
    }

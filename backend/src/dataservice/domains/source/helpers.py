"""Pure helpers for Source domain services."""

from __future__ import annotations

from src.dataservice.domains.source.contracts import SourceProjection

_PROCEEDINGS_BIBTEX_TYPES = {"conference", "inproceedings", "proceedings"}


def normalize_citation_keys(citation_keys: list[str]) -> list[str]:
    return [key for key in dict.fromkeys(str(item).strip() for item in citation_keys) if key]


def normalize_ids(ids: list[str]) -> list[str]:
    return [item for item in dict.fromkeys(str(raw).strip() for raw in ids) if item]


def max_ranked_value(current: object, incoming: object, ranks: dict[str, int]) -> str:
    current_value = str(current or "")
    incoming_value = str(incoming or "")
    return incoming_value if ranks.get(incoming_value, 0) > ranks.get(current_value, 0) else current_value


def format_bibtex_entry(record: object) -> str:
    fields = dict(getattr(record, "bibtex_fields_json", None) or {})
    fields.setdefault("title", getattr(record, "title", None))
    authors = getattr(record, "authors_json", None) or []
    if authors:
        fields.setdefault("author", " and ".join(str(author) for author in authors if author))
    year = getattr(record, "year", None)
    if year:
        fields.setdefault("year", str(year))
    venue = getattr(record, "venue", None)
    entry_type = str(getattr(record, "bibtex_entry_type", None) or "article").strip() or "article"
    if venue:
        field_name = "booktitle" if entry_type in _PROCEEDINGS_BIBTEX_TYPES else "journal"
        fields.setdefault(field_name, venue)
    doi = getattr(record, "doi", None)
    if doi:
        fields.setdefault("doi", doi)
    url = getattr(record, "url", None)
    if url:
        fields.setdefault("url", url)

    rendered_fields = []
    for key in sorted(fields):
        value = clean_bibtex_value(fields[key])
        if value:
            rendered_fields.append(f"  {key} = {{{value}}}")
    citation_key = clean_citation_key(
        getattr(record, "citation_key", None),
        default_key=str(getattr(record, "id", "source")),
    )
    joined = ",\n".join(rendered_fields)
    return f"@{entry_type}{{{citation_key},\n{joined}\n}}"


def clean_bibtex_value(value: object) -> str:
    return str(value or "").replace("{", "").replace("}", "").strip()


def clean_citation_key(value: object, *, default_key: str) -> str:
    cleaned = str(value or "").strip().replace("{", "").replace("}", "")
    return cleaned or default_key


def normalize_doi(value: object) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    lower = normalized.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lower.startswith(prefix):
            return normalized[len(prefix) :].strip().lower() or None
    return normalized.lower()


def serialize_reference_projection(source: SourceProjection) -> dict[str, object]:
    return {
        "id": source.id,
        "workspace_id": source.workspace_id,
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
        "source_artifact_id": None,
        "verified_at": source.verified_at.isoformat() if source.verified_at else None,
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
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


def serialize_source_asset(source_asset: object, workspace_asset: object | None) -> dict[str, object]:
    metadata = dict(getattr(source_asset, "metadata_json", None) or {})
    created_at = getattr(source_asset, "created_at", None)
    updated_at = getattr(source_asset, "updated_at", None)
    return {
        "id": str(source_asset.id),
        "workspace_id": str(source_asset.workspace_id),
        "reference_id": str(source_asset.source_id),
        "source_id": str(source_asset.source_id),
        "workspace_asset_id": str(source_asset.workspace_asset_id),
        "source_asset_id": metadata.get("source_asset_id"),
        "asset_type": getattr(source_asset, "asset_type", None),
        "file_path": getattr(workspace_asset, "storage_path", None) if workspace_asset else metadata.get("file_path"),
        "virtual_path": metadata.get("virtual_path"),
        "public_url": metadata.get("public_url"),
        "content_type": getattr(workspace_asset, "mime_type", None) if workspace_asset else metadata.get("content_type"),
        "file_size": getattr(workspace_asset, "size_bytes", None) if workspace_asset else metadata.get("file_size"),
        "file_hash": getattr(workspace_asset, "content_hash", None) if workspace_asset else metadata.get("file_hash"),
        "page_count": metadata.get("page_count"),
        "language": metadata.get("language"),
        "preprocess_status": getattr(source_asset, "preprocess_status", None),
        "preprocess_task_id": metadata.get("preprocess_task_id"),
        "preprocess_error": metadata.get("preprocess_error"),
        "manifest_path": metadata.get("manifest_path"),
        "markdown_paths": list(metadata.get("markdown_paths") or []),
        "metadata": metadata,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def serialize_external_id(record: object) -> dict[str, object]:
    created_at = getattr(record, "created_at", None)
    updated_at = getattr(record, "updated_at", None)
    provider = getattr(record, "provider", None)
    return {
        "id": str(record.id),
        "workspace_id": str(record.workspace_id),
        "source_id": str(record.source_id),
        "provider": provider,
        "source": provider,
        "external_id": record.external_id,
        "url": getattr(record, "url", None),
        "metadata": dict(getattr(record, "metadata_json", None) or {}),
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def serialize_outline_node(record: object) -> dict[str, object]:
    return {
        "id": str(record.id),
        "workspace_id": str(record.workspace_id),
        "source_id": str(record.source_id),
        "reference_id": str(record.source_id),
        "parent_id": getattr(record, "parent_id", None),
        "section_path": getattr(record, "section_path", None),
        "title": getattr(record, "title", None),
        "level": getattr(record, "level", None),
        "sort_order": getattr(record, "sort_order", None),
        "page_start": getattr(record, "page_start", None),
        "page_end": getattr(record, "page_end", None),
        "summary": getattr(record, "summary", None),
        "keywords": list(getattr(record, "keywords_json", None) or []),
    }


def serialize_text_unit(record: object) -> dict[str, object]:
    return {
        "id": str(record.id),
        "workspace_id": str(record.workspace_id),
        "source_id": str(record.source_id),
        "reference_id": str(record.source_id),
        "outline_node_id": getattr(record, "outline_node_id", None),
        "asset_id": getattr(record, "source_asset_id", None),
        "unit_type": getattr(record, "unit_type", None),
        "unit_index": getattr(record, "unit_index", None),
        "page_start": getattr(record, "page_start", None),
        "page_end": getattr(record, "page_end", None),
        "content": getattr(record, "content", None),
        "token_count": getattr(record, "token_count", None),
        "metadata": dict(getattr(record, "metadata_json", None) or {}),
        "created_at": getattr(record, "created_at", None),
        "updated_at": getattr(record, "updated_at", None),
    }

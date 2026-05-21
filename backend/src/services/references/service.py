"""Services for the workspace-scoped reference library."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.citation.bibtex.parser import BibTeXParser
from src.academic.literature.search_service import LiteratureSearchService
from src.database import (
    Artifact,
    ReferenceAcceptedStatus,
    ReferenceAsset,
    ReferenceAssetType,
    ReferenceBibtexScope,
    ReferenceBibtexSnapshot,
    ReferenceEvidenceLevel,
    ReferenceExternalId,
    ReferenceFulltextStatus,
    ReferenceLibraryStatus,
    ReferenceOutlineNode,
    ReferencePreprocessStatus,
    ReferenceReadStatus,
    ReferenceSourceType,
    ReferenceTextUnit,
    ReferenceTextUnitType,
    ReferenceUsageEvent,
    ReferenceUsageType,
    Workspace,
    WorkspaceReference,
)
from src.dataservice.asset_api import AssetDataService
from src.dataservice.source_api import (
    SourceBibliographyCreateCommand,
    SourceCreateCommand,
    SourceDataService,
)
from src.services.latex.project_service import LatexProjectService
from src.services.upload_preprocessor import UploadPreprocessResult, get_upload_preprocessor_service
from src.services.workspace_latex_projects import WorkspaceLatexProjectService
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    extract_document_preview,
    is_pdf_upload,
    next_available_path,
    resolve_workspace_upload_stored_path,
    sanitize_upload_filename,
    workspace_upload_dir,
    workspace_upload_public_url,
)

from .utils import (
    build_citation_key_base,
    clean_bibtex_value,
    guess_bibtex_entry_type,
    normalize_doi,
    normalize_title,
    parse_authors,
    safe_int,
    sha256_bytes,
    utc_now,
)

logger = logging.getLogger(__name__)

REFERENCE_PREPROCESS_THRESHOLD_BYTES = 5 * 1024 * 1024
REFERENCE_UPLOAD_BUCKET = "references"


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _coerce_enum_value(enum_cls: type[Any], value: Any, field_name: str) -> str:
    normalized = _enum_value(value).strip()
    for item in enum_cls:
        if normalized == item.value:
            return str(item.value)
    allowed = ", ".join(item.value for item in enum_cls)
    raise ValueError(f"Invalid {field_name}: {normalized}. Allowed values: {allowed}")


def _serialize_datetime(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_reference(reference: WorkspaceReference) -> dict[str, Any]:
    """Serialize a reference for HTTP/API/tool consumers."""
    return {
        "id": str(reference.id),
        "workspace_id": str(reference.workspace_id),
        "title": reference.title,
        "normalized_title": reference.normalized_title,
        "authors": list(reference.authors or []),
        "year": reference.year,
        "venue": reference.venue,
        "publication_type": reference.publication_type,
        "doi": reference.doi,
        "url": reference.url,
        "abstract": reference.abstract,
        "citation_count": reference.citation_count,
        "source_type": _enum_value(reference.source_type),
        "source_label": reference.source_label,
        "source_run_id": reference.source_run_id,
        "source_artifact_id": reference.source_artifact_id,
        "verified_at": _serialize_datetime(reference.verified_at),
        "library_status": _enum_value(reference.library_status),
        "evidence_level": _enum_value(reference.evidence_level),
        "fulltext_status": _enum_value(reference.fulltext_status),
        "citation_key": reference.citation_key,
        "bibtex_entry_type": reference.bibtex_entry_type,
        "bibtex_fields": dict(reference.bibtex_fields or {}),
        "read_status": _enum_value(reference.read_status),
        "tags": list(reference.tags or []),
        "notes": reference.notes,
        "is_deleted": bool(reference.is_deleted),
        "created_at": _serialize_datetime(reference.created_at),
        "updated_at": _serialize_datetime(reference.updated_at),
    }


def serialize_asset(asset: ReferenceAsset) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "workspace_id": str(asset.workspace_id),
        "reference_id": str(asset.reference_id),
        "source_asset_id": str(asset.source_asset_id) if asset.source_asset_id else None,
        "asset_type": _enum_value(asset.asset_type),
        "file_path": asset.file_path,
        "virtual_path": asset.virtual_path,
        "public_url": asset.public_url,
        "content_type": asset.content_type,
        "file_size": asset.file_size,
        "file_hash": asset.file_hash,
        "page_count": asset.page_count,
        "language": asset.language,
        "preprocess_status": _enum_value(asset.preprocess_status),
        "preprocess_task_id": asset.preprocess_task_id,
        "preprocess_error": asset.preprocess_error,
        "manifest_path": asset.manifest_path,
        "markdown_paths": list(asset.markdown_paths or []),
        "created_at": _serialize_datetime(asset.created_at),
        "updated_at": _serialize_datetime(asset.updated_at),
    }


def serialize_external_id(external_id: ReferenceExternalId) -> dict[str, Any]:
    return {
        "id": str(external_id.id),
        "workspace_id": str(external_id.workspace_id),
        "reference_id": str(external_id.reference_id),
        "source": external_id.source,
        "external_id": external_id.external_id,
        "url": external_id.url,
        "created_at": _serialize_datetime(external_id.created_at),
        "updated_at": _serialize_datetime(external_id.updated_at),
    }


def serialize_usage_event(event: ReferenceUsageEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "workspace_id": str(event.workspace_id),
        "reference_id": str(event.reference_id),
        "outline_node_id": event.outline_node_id,
        "text_unit_id": event.text_unit_id,
        "execution_id": event.execution_id,
        "task_id": event.task_id,
        "artifact_id": event.artifact_id,
        "latex_project_id": event.latex_project_id,
        "target_section": event.target_section,
        "claim_text": event.claim_text,
        "generated_text": event.generated_text,
        "citation_key": event.citation_key,
        "usage_type": _enum_value(event.usage_type),
        "accepted_status": _enum_value(event.accepted_status),
        "created_at": _serialize_datetime(event.created_at),
        "updated_at": _serialize_datetime(event.updated_at),
    }


def summarize_preprocess_assets(assets: Sequence[ReferenceAsset]) -> dict[str, Any]:
    statuses = [_enum_value(asset.preprocess_status) for asset in assets]
    status_counts = {status: statuses.count(status) for status in sorted(set(statuses))}
    if any(status == ReferencePreprocessStatus.FAILED.value for status in statuses):
        overall_status = ReferencePreprocessStatus.FAILED.value
    elif any(status == ReferencePreprocessStatus.RUNNING.value for status in statuses):
        overall_status = ReferencePreprocessStatus.RUNNING.value
    elif any(status == ReferencePreprocessStatus.PENDING.value for status in statuses):
        overall_status = ReferencePreprocessStatus.PENDING.value
    elif any(status == ReferencePreprocessStatus.SUCCEEDED.value for status in statuses):
        overall_status = ReferencePreprocessStatus.SUCCEEDED.value
    elif statuses:
        overall_status = ReferencePreprocessStatus.SKIPPED.value
    else:
        overall_status = "none"

    markdown_paths: list[str] = []
    manifest_paths: list[str] = []
    task_ids: list[str] = []
    errors: list[str] = []
    for asset in assets:
        markdown_paths.extend(str(path) for path in asset.markdown_paths or [] if path)
        if asset.manifest_path:
            manifest_paths.append(asset.manifest_path)
        if asset.preprocess_task_id:
            task_ids.append(asset.preprocess_task_id)
        if asset.preprocess_error:
            errors.append(asset.preprocess_error)

    return {
        "status": overall_status,
        "status_counts": status_counts,
        "asset_count": len(assets),
        "markdown_paths": list(dict.fromkeys(markdown_paths)),
        "manifest_paths": list(dict.fromkeys(manifest_paths)),
        "task_ids": list(dict.fromkeys(task_ids)),
        "errors": list(dict.fromkeys(errors)),
    }


def serialize_outline_node(node: ReferenceOutlineNode) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "workspace_id": str(node.workspace_id),
        "reference_id": str(node.reference_id),
        "parent_id": node.parent_id,
        "section_path": node.section_path,
        "title": node.title,
        "level": node.level,
        "sort_order": node.sort_order,
        "page_start": node.page_start,
        "page_end": node.page_end,
        "summary": node.summary,
        "keywords": list(node.keywords or []),
    }


def serialize_text_unit(unit: ReferenceTextUnit) -> dict[str, Any]:
    return {
        "id": str(unit.id),
        "workspace_id": str(unit.workspace_id),
        "reference_id": str(unit.reference_id),
        "outline_node_id": unit.outline_node_id,
        "asset_id": unit.asset_id,
        "unit_type": _enum_value(unit.unit_type),
        "unit_index": unit.unit_index,
        "page_start": unit.page_start,
        "page_end": unit.page_end,
        "content": unit.content,
        "token_count": unit.token_count,
        "metadata": dict(unit.unit_metadata or {}),
        "created_at": _serialize_datetime(unit.created_at),
        "updated_at": _serialize_datetime(unit.updated_at),
    }


def _metadata_from_reference(reference: WorkspaceReference) -> dict[str, Any]:
    return {
        "title": reference.title,
        "authors": list(reference.authors or []),
        "year": reference.year,
        "venue": reference.venue,
        "doi": reference.doi,
        "url": reference.url,
        "abstract": reference.abstract,
        "citation_count": reference.citation_count,
        "citation_key": reference.citation_key,
    }


def _paper_candidate_from_bibtex(entry: dict[str, str]) -> dict[str, Any]:
    parser = BibTeXParser()
    payload = parser.to_paper_dict(entry)
    result = dict(payload)
    result["citation_key"] = entry.get("key")
    result["bibtex_entry_type"] = entry.get("entry_type") or "article"
    result["bibtex_fields"] = {
        key: value
        for key, value in entry.items()
        if key not in {"key", "entry_type"}
    }
    return result


async def _sync_reference_assets_to_dataservice(
    db: AsyncSession,
    reference: WorkspaceReference,
) -> list[dict[str, object]]:
    result = await db.execute(
        select(ReferenceAsset).where(
            ReferenceAsset.workspace_id == reference.workspace_id,
            ReferenceAsset.reference_id == reference.id,
        )
    )
    synced: list[dict[str, object]] = []
    asset_service = AssetDataService(db, autocommit=False)
    source_service = SourceDataService(db, autocommit=False)
    existing_assets = {
        str(item["id"]): item
        for item in await source_service.list_source_assets(
            workspace_id=str(reference.workspace_id),
            source_id=str(reference.id),
        )
    }
    for asset in result.scalars().all():
        metadata = {
            "legacy_table": "reference_assets",
            "legacy_id": str(asset.id),
            "source_asset_id": str(asset.source_asset_id) if asset.source_asset_id else None,
            "reference_id": str(asset.reference_id),
            "virtual_path": asset.virtual_path,
            "public_url": asset.public_url,
            "page_count": asset.page_count,
            "language": asset.language,
            "manifest_path": asset.manifest_path,
            "markdown_paths": list(asset.markdown_paths or []),
            "preprocess_task_id": asset.preprocess_task_id,
            "preprocess_error": asset.preprocess_error,
        }
        existing_asset = existing_assets.get(str(asset.id))
        workspace_asset_id = str(existing_asset.get("workspace_asset_id")) if existing_asset else None
        if not workspace_asset_id:
            workspace_asset = await asset_service.register_asset_record(
                workspace_id=str(asset.workspace_id),
                asset_kind="source_file",
                name=asset.virtual_path or Path(asset.file_path or str(asset.id)).name,
                title=asset.virtual_path,
                mime_type=asset.content_type,
                storage_path=asset.file_path or asset.public_url or asset.virtual_path or str(asset.id),
                size_bytes=asset.file_size,
                content_hash=asset.file_hash,
                created_by="reference_import",
                source_kind="source",
                source_id=str(reference.id),
                metadata_json=metadata,
            )
            workspace_asset_id = workspace_asset.id
        synced.append(
            await source_service.link_source_asset(
                workspace_id=str(asset.workspace_id),
                source_id=str(reference.id),
                workspace_asset_id=workspace_asset_id,
                source_asset_id=str(asset.id),
                asset_type=_enum_value(asset.asset_type),
                preprocess_status=_enum_value(asset.preprocess_status),
                metadata_json=metadata,
            )
        )
    return synced


class WorkspaceReferenceService:
    """CRUD, dedupe, and citation-key ownership for workspace references."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(
        self,
        workspace_id: str,
        reference_id: str,
        *,
        include_deleted: bool = False,
    ) -> WorkspaceReference | None:
        stmt = select(WorkspaceReference).where(
            WorkspaceReference.workspace_id == workspace_id,
            WorkspaceReference.id == reference_id,
        )
        if not include_deleted:
            stmt = stmt.where(WorkspaceReference.is_deleted.is_(False))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_reference_detail(
        self,
        workspace_id: str,
        reference_id: str,
        *,
        usage_limit: int = 10,
    ) -> dict[str, Any] | None:
        reference = await self.get(workspace_id, reference_id)
        if reference is None:
            return None

        assets_result = await self.db.execute(
            select(ReferenceAsset)
            .where(
                ReferenceAsset.workspace_id == workspace_id,
                ReferenceAsset.reference_id == reference_id,
            )
            .order_by(ReferenceAsset.created_at.desc())
        )
        assets = list(assets_result.scalars().all())

        external_ids_result = await self.db.execute(
            select(ReferenceExternalId)
            .where(
                ReferenceExternalId.workspace_id == workspace_id,
                ReferenceExternalId.reference_id == reference_id,
            )
            .order_by(ReferenceExternalId.created_at.desc())
        )
        external_ids = list(external_ids_result.scalars().all())

        usage_events_result = await self.db.execute(
            select(ReferenceUsageEvent)
            .where(
                ReferenceUsageEvent.workspace_id == workspace_id,
                ReferenceUsageEvent.reference_id == reference_id,
            )
            .order_by(ReferenceUsageEvent.created_at.desc())
            .limit(max(1, min(int(usage_limit), 50)))
        )
        usage_events = list(usage_events_result.scalars().all())
        serialized_usage_events = [serialize_usage_event(event) for event in usage_events]
        usage_status_counts: dict[str, int] = {}
        for event in serialized_usage_events:
            status = str(event.get("accepted_status") or "unknown")
            usage_status_counts[status] = usage_status_counts.get(status, 0) + 1

        serialized_external_ids = [serialize_external_id(item) for item in external_ids]
        source_history: list[dict[str, Any]] = []
        if reference.source_type or reference.source_label or reference.source_artifact_id:
            source_history.append(
                {
                    "source_type": _enum_value(reference.source_type),
                    "source_label": reference.source_label,
                    "source_run_id": reference.source_run_id,
                    "source_artifact_id": reference.source_artifact_id,
                    "verified_at": _serialize_datetime(reference.verified_at),
                }
            )
        for item in serialized_external_ids:
            source_history.append(
                {
                    "source_type": item["source"],
                    "external_id": item["external_id"],
                    "url": item["url"],
                    "created_at": item["created_at"],
                }
            )

        serialized_assets = [serialize_asset(asset) for asset in assets]
        return {
            "reference": {
                **serialize_reference(reference),
                "assets": serialized_assets,
            },
            "assets": serialized_assets,
            "external_ids": serialized_external_ids,
            "source_history": source_history,
            "preprocess": summarize_preprocess_assets(assets),
            "usage_events": serialized_usage_events,
            "usage_summary": {
                "recent_count": len(serialized_usage_events),
                "status_counts": usage_status_counts,
                "last_used_at": serialized_usage_events[0]["created_at"]
                if serialized_usage_events
                else None,
            },
        }

    async def list_references(
        self,
        workspace_id: str,
        *,
        library_status: str | None = None,
        source_type: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        base = select(WorkspaceReference).where(
            WorkspaceReference.workspace_id == workspace_id,
            WorkspaceReference.is_deleted.is_(False),
        )
        if library_status:
            base = base.where(
                WorkspaceReference.library_status == _coerce_enum_value(
                    ReferenceLibraryStatus,
                    library_status,
                    "library_status",
                )
            )
        if source_type:
            base = base.where(
                WorkspaceReference.source_type == _coerce_enum_value(
                    ReferenceSourceType,
                    source_type,
                    "source_type",
                )
            )
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            base = base.where(
                or_(
                    WorkspaceReference.title.ilike(pattern),
                    WorkspaceReference.venue.ilike(pattern),
                    WorkspaceReference.doi.ilike(pattern),
                    WorkspaceReference.abstract.ilike(pattern),
                )
            )

        total_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = int(total_result.scalar() or 0)
        core_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status == ReferenceLibraryStatus.CORE,
            )
        )
        core = int(core_result.scalar() or 0)
        items_result = await self.db.execute(
            base.order_by(WorkspaceReference.updated_at.desc())
            .offset(max(0, int(offset)))
            .limit(max(1, min(int(limit), 200)))
        )
        items = list(items_result.scalars().all())
        assets_by_reference: dict[str, list[dict[str, Any]]] = {}
        if items:
            reference_ids = [str(item.id) for item in items]
            assets_result = await self.db.execute(
                select(ReferenceAsset)
                .where(
                    ReferenceAsset.workspace_id == workspace_id,
                    ReferenceAsset.reference_id.in_(reference_ids),
                )
                .order_by(ReferenceAsset.created_at.desc())
            )
            for asset in assets_result.scalars().all():
                assets_by_reference.setdefault(str(asset.reference_id), []).append(
                    serialize_asset(asset)
                )
        return {
            "items": [
                {
                    **serialize_reference(item),
                    "assets": assets_by_reference.get(str(item.id), []),
                }
                for item in items
            ],
            "total": total,
            "core_count": core,
        }

    async def count_references(self, workspace_id: str) -> dict[str, int]:
        total_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status != ReferenceLibraryStatus.EXCLUDED,
            )
        )
        core_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status == ReferenceLibraryStatus.CORE,
            )
        )
        indexed_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.fulltext_status == ReferenceFulltextStatus.INDEXED,
            )
        )
        return {
            "total": int(total_result.scalar() or 0),
            "core": int(core_result.scalar() or 0),
            "indexed": int(indexed_result.scalar() or 0),
        }

    async def update_reference(
        self,
        workspace_id: str,
        reference_id: str,
        **updates: Any,
    ) -> WorkspaceReference | None:
        reference = await self.get(workspace_id, reference_id)
        if reference is None:
            return None

        allowed = {
            "title",
            "authors",
            "year",
            "venue",
            "publication_type",
            "doi",
            "url",
            "abstract",
            "citation_count",
            "library_status",
            "read_status",
            "tags",
            "notes",
            "citation_key",
            "bibtex_entry_type",
            "bibtex_fields",
        }
        if "doi" in updates:
            updates["doi"] = normalize_doi(updates["doi"])
        if "authors" in updates:
            updates["authors"] = parse_authors(updates["authors"])
        if "year" in updates:
            updates["year"] = safe_int(updates["year"])
        if "title" in updates and updates["title"]:
            updates["normalized_title"] = normalize_title(str(updates["title"]))
            allowed.add("normalized_title")
        if "citation_key" in updates and updates["citation_key"]:
            updates["citation_key"] = await self._ensure_unique_citation_key(
                workspace_id,
                str(updates["citation_key"]),
                exclude_reference_id=reference_id,
            )
        if "library_status" in updates and updates["library_status"] is not None:
            updates["library_status"] = _coerce_enum_value(
                ReferenceLibraryStatus,
                updates["library_status"],
                "library_status",
            )
        if "read_status" in updates and updates["read_status"] is not None:
            updates["read_status"] = _coerce_enum_value(
                ReferenceReadStatus,
                updates["read_status"],
                "read_status",
            )

        for key, value in updates.items():
            if key in allowed and hasattr(reference, key):
                setattr(reference, key, value)
        await self.db.commit()
        await self.db.refresh(reference)
        return reference

    async def mark_status(
        self,
        workspace_id: str,
        reference_id: str,
        *,
        library_status: ReferenceLibraryStatus | str | None = None,
        read_status: ReferenceReadStatus | str | None = None,
    ) -> WorkspaceReference | None:
        updates: dict[str, Any] = {}
        if library_status is not None:
            updates["library_status"] = _enum_value(library_status)
        if read_status is not None:
            updates["read_status"] = _enum_value(read_status)
        return await self.update_reference(workspace_id, reference_id, **updates)

    async def record_reference_usage(
        self,
        *,
        workspace_id: str,
        reference_ids: Sequence[str],
        outline_node_id: str | None = None,
        text_unit_id: str | None = None,
        execution_id: str | None = None,
        task_id: str | None = None,
        artifact_id: str | None = None,
        latex_project_id: str | None = None,
        target_section: str | None = None,
        claim_text: str | None = None,
        generated_text: str | None = None,
        usage_type: ReferenceUsageType | str = ReferenceUsageType.CITATION_ONLY,
        accepted_status: ReferenceAcceptedStatus | str = ReferenceAcceptedStatus.PENDING,
        mark_used_in_draft: bool = True,
    ) -> dict[str, Any]:
        return await ReferenceUsageService(self.db).record_usage(
            workspace_id=workspace_id,
            reference_ids=reference_ids,
            outline_node_id=outline_node_id,
            text_unit_id=text_unit_id,
            execution_id=execution_id,
            task_id=task_id,
            artifact_id=artifact_id,
            latex_project_id=latex_project_id,
            target_section=target_section,
            claim_text=claim_text,
            generated_text=generated_text,
            usage_type=usage_type,
            accepted_status=accepted_status,
            mark_used_in_draft=mark_used_in_draft,
        )

    async def soft_delete(self, workspace_id: str, reference_id: str) -> bool:
        reference = await self.get(workspace_id, reference_id)
        if reference is None:
            return False
        reference.is_deleted = True
        await self.db.commit()
        return True

    async def search_in_workspace(
        self,
        *,
        workspace_id: str,
        query: str,
        limit: int = 8,
    ) -> list[WorkspaceReference]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []
        pattern = f"%{normalized_query}%"
        stmt = (
            select(WorkspaceReference)
            .where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status != ReferenceLibraryStatus.EXCLUDED,
            )
            .where(
                or_(
                    WorkspaceReference.title.ilike(pattern),
                    WorkspaceReference.doi.ilike(pattern),
                    WorkspaceReference.citation_key.ilike(pattern),
                    WorkspaceReference.abstract.ilike(pattern),
                )
            )
            .order_by(WorkspaceReference.library_status, WorkspaceReference.updated_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _find_existing_reference(
        self,
        *,
        workspace_id: str,
        doi: str | None,
        title: str,
        year: int | None,
        external_source: str | None = None,
        external_id: str | None = None,
        dedupe_by_title: bool = True,
    ) -> WorkspaceReference | None:
        if external_source and external_id:
            ext_result = await self.db.execute(
                select(ReferenceExternalId)
                .where(
                    ReferenceExternalId.workspace_id == workspace_id,
                    ReferenceExternalId.source == external_source,
                    ReferenceExternalId.external_id == external_id,
                )
            )
            ext = ext_result.scalar_one_or_none()
            if ext is not None:
                return await self.get(workspace_id, ext.reference_id)

        if doi:
            doi_result = await self.db.execute(
                select(WorkspaceReference).where(
                    WorkspaceReference.workspace_id == workspace_id,
                    WorkspaceReference.doi == doi,
                    WorkspaceReference.is_deleted.is_(False),
                )
            )
            match = doi_result.scalar_one_or_none()
            if match is not None:
                return match

        if not dedupe_by_title:
            return None

        normalized_title = normalize_title(title)
        if normalized_title:
            title_stmt = select(WorkspaceReference).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.normalized_title == normalized_title,
                WorkspaceReference.is_deleted.is_(False),
            )
            if year is not None:
                title_stmt = title_stmt.where(WorkspaceReference.year == year)
            title_result = await self.db.execute(title_stmt)
            return title_result.scalars().first()
        return None

    async def upsert_reference(
        self,
        *,
        workspace_id: str,
        title: str,
        authors: Any = None,
        year: Any = None,
        venue: str | None = None,
        publication_type: str | None = None,
        doi: Any = None,
        url: str | None = None,
        abstract: str | None = None,
        citation_count: Any = None,
        source_type: ReferenceSourceType | str,
        source_label: str | None = None,
        source_run_id: str | None = None,
        source_artifact_id: str | None = None,
        verified_at: Any = None,
        library_status: ReferenceLibraryStatus | str = ReferenceLibraryStatus.CANDIDATE,
        evidence_level: ReferenceEvidenceLevel | str = ReferenceEvidenceLevel.METADATA_ONLY,
        fulltext_status: ReferenceFulltextStatus | str = ReferenceFulltextStatus.NONE,
        external_ids: Sequence[dict[str, Any]] | None = None,
        citation_key: str | None = None,
        bibtex_entry_type: str | None = None,
        bibtex_fields: dict[str, Any] | None = None,
        dedupe_by_title: bool = True,
        commit: bool = True,
    ) -> tuple[WorkspaceReference, bool]:
        resolved_title = str(title or "").strip()
        if not resolved_title:
            raise ValueError("Reference title is required")
        resolved_authors = parse_authors(authors)
        resolved_year = safe_int(year)
        resolved_doi = normalize_doi(doi)
        resolved_source_type = _coerce_enum_value(
            ReferenceSourceType,
            source_type,
            "source_type",
        )
        resolved_library_status = _coerce_enum_value(
            ReferenceLibraryStatus,
            library_status,
            "library_status",
        )
        resolved_evidence_level = _coerce_enum_value(
            ReferenceEvidenceLevel,
            evidence_level,
            "evidence_level",
        )
        resolved_fulltext_status = _coerce_enum_value(
            ReferenceFulltextStatus,
            fulltext_status,
            "fulltext_status",
        )
        ext_source = None
        ext_id = None
        for item in external_ids or []:
            if isinstance(item, dict) and item.get("source") and item.get("external_id"):
                ext_source = str(item["source"])
                ext_id = str(item["external_id"])
                break

        existing = await self._find_existing_reference(
            workspace_id=workspace_id,
            doi=resolved_doi,
            title=resolved_title,
            year=resolved_year,
            external_source=ext_source,
            external_id=ext_id,
            dedupe_by_title=dedupe_by_title,
        )
        created = existing is None
        if existing is None:
            base_key = citation_key or build_citation_key_base(
                title=resolved_title,
                authors=resolved_authors,
                year=resolved_year,
            )
            existing = WorkspaceReference(
                workspace_id=workspace_id,
                title=resolved_title,
                normalized_title=normalize_title(resolved_title),
                authors=resolved_authors,
                year=resolved_year,
                venue=(venue or None),
                publication_type=publication_type,
                doi=resolved_doi,
                url=url,
                abstract=abstract,
                citation_count=safe_int(citation_count),
                source_type=resolved_source_type,
                source_label=source_label,
                source_run_id=source_run_id,
                source_artifact_id=source_artifact_id,
                verified_at=verified_at if hasattr(verified_at, "isoformat") else utc_now() if verified_at else None,
                library_status=resolved_library_status,
                evidence_level=resolved_evidence_level,
                fulltext_status=resolved_fulltext_status,
                citation_key=await self._ensure_unique_citation_key(workspace_id, base_key),
                bibtex_entry_type=bibtex_entry_type
                or guess_bibtex_entry_type(venue=venue, publication_type=publication_type),
                bibtex_fields=bibtex_fields or {},
                read_status=ReferenceReadStatus.UNREAD,
                tags=[],
            )
            self.db.add(existing)
            await self.db.flush()
        else:
            existing.title = existing.title or resolved_title
            existing.normalized_title = normalize_title(existing.title)
            existing.authors = existing.authors or resolved_authors
            existing.year = existing.year or resolved_year
            existing.venue = existing.venue or venue
            existing.publication_type = existing.publication_type or publication_type
            existing.doi = existing.doi or resolved_doi
            existing.url = existing.url or url
            existing.abstract = existing.abstract or abstract
            existing.citation_count = existing.citation_count or safe_int(citation_count)
            existing.source_label = existing.source_label or source_label
            existing.source_run_id = existing.source_run_id or source_run_id
            existing.source_artifact_id = existing.source_artifact_id or source_artifact_id
            if verified_at and existing.verified_at is None:
                existing.verified_at = verified_at if hasattr(verified_at, "isoformat") else utc_now()
            existing.evidence_level = self._max_evidence_level(existing.evidence_level, resolved_evidence_level)  # type: ignore[assignment]
            existing.fulltext_status = self._max_fulltext_status(existing.fulltext_status, resolved_fulltext_status)  # type: ignore[assignment]
            if resolved_library_status != ReferenceLibraryStatus.CANDIDATE.value:
                existing.library_status = resolved_library_status  # type: ignore[assignment]
            if bibtex_fields:
                existing.bibtex_fields = {**dict(existing.bibtex_fields or {}), **bibtex_fields}

        await self._upsert_external_ids(
            workspace_id=workspace_id,
            reference_id=str(existing.id),
            external_ids=external_ids or [],
        )
        await self._sync_source_record(existing)
        await self._ensure_abstract_text_unit(existing)
        if commit:
            await self.db.commit()
            await self.db.refresh(existing)
        return existing, created

    async def _sync_source_record(self, reference: WorkspaceReference) -> None:
        await SourceDataService(self.db, autocommit=False).upsert_source(
            SourceCreateCommand(
                source_id=str(reference.id),
                workspace_id=str(reference.workspace_id),
                source_kind="paper",
                title=reference.title,
                normalized_title=reference.normalized_title,
                authors_json=list(reference.authors or []),
                year=reference.year,
                venue=reference.venue,
                publication_type=reference.publication_type,
                doi=reference.doi,
                url=reference.url,
                abstract=reference.abstract,
                citation_count=reference.citation_count,
                ingest_kind=_enum_value(reference.source_type),
                ingest_label=reference.source_label,
                ingest_execution_id=reference.source_run_id,
                verified_at=reference.verified_at,
                library_status=_enum_value(reference.library_status),
                evidence_level=_enum_value(reference.evidence_level),
                fulltext_status=_enum_value(reference.fulltext_status),
                citation_key=reference.citation_key,
                bibtex_entry_type=reference.bibtex_entry_type,
                bibtex_fields_json=dict(reference.bibtex_fields or {}),
                read_status=_enum_value(reference.read_status),
                tags_json=list(reference.tags or []),
                notes=reference.notes,
                is_deleted=bool(reference.is_deleted),
            )
        )

    async def _ensure_unique_citation_key(
        self,
        workspace_id: str,
        base_key: str,
        *,
        exclude_reference_id: str | None = None,
    ) -> str:
        base = re.sub(r"[^A-Za-z0-9_:-]+", "", str(base_key or "").strip()) or "ref"
        candidate = base
        suffix = 2
        while True:
            stmt = select(WorkspaceReference.id).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.citation_key == candidate,
                WorkspaceReference.is_deleted.is_(False),
            )
            if exclude_reference_id:
                stmt = stmt.where(WorkspaceReference.id != exclude_reference_id)
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none() is None:
                return candidate
            candidate = f"{base}{suffix}"
            suffix += 1

    async def _upsert_external_ids(
        self,
        *,
        workspace_id: str,
        reference_id: str,
        external_ids: Sequence[dict[str, Any]],
    ) -> None:
        for item in external_ids:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            external_id = str(item.get("external_id") or "").strip()
            if not source or not external_id:
                continue
            existing_result = await self.db.execute(
                select(ReferenceExternalId).where(
                    ReferenceExternalId.workspace_id == workspace_id,
                    ReferenceExternalId.source == source,
                    ReferenceExternalId.external_id == external_id,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing is None:
                self.db.add(
                    ReferenceExternalId(
                        workspace_id=workspace_id,
                        reference_id=reference_id,
                        source=source,
                        external_id=external_id,
                        url=str(item.get("url") or "").strip() or None,
                    )
                )
            else:
                existing.reference_id = reference_id
                existing.url = existing.url or str(item.get("url") or "").strip() or None

    async def _ensure_abstract_text_unit(self, reference: WorkspaceReference) -> None:
        if not reference.abstract:
            return
        existing_result = await self.db.execute(
            select(ReferenceTextUnit.id).where(
                ReferenceTextUnit.workspace_id == reference.workspace_id,
                ReferenceTextUnit.reference_id == reference.id,
                ReferenceTextUnit.unit_type == ReferenceTextUnitType.ABSTRACT,
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            return
        content = str(reference.abstract).strip()
        if not content:
            return
        self.db.add(
            ReferenceTextUnit(
                workspace_id=reference.workspace_id,
                reference_id=reference.id,
                unit_type=ReferenceTextUnitType.ABSTRACT,
                unit_index=0,
                content=content,
                token_count=len(content.split()),
                search_text=f"{reference.title}\nAbstract\n{content}",
                unit_metadata={"source": "reference_abstract"},
            )
        )

    @staticmethod
    def _max_evidence_level(current: Any, incoming: Any) -> str:
        order = {
            ReferenceEvidenceLevel.METADATA_ONLY.value: 0,
            ReferenceEvidenceLevel.EXTERNAL_VERIFIED.value: 1,
            ReferenceEvidenceLevel.UPLOADED_FULLTEXT.value: 2,
            ReferenceEvidenceLevel.INDEXED_FULLTEXT.value: 3,
        }
        current_value = _enum_value(current)
        incoming_value = _enum_value(incoming)
        return incoming_value if order.get(incoming_value, 0) > order.get(current_value, 0) else current_value

    @staticmethod
    def _max_fulltext_status(current: Any, incoming: Any) -> str:
        order = {
            ReferenceFulltextStatus.NONE.value: 0,
            ReferenceFulltextStatus.FAILED.value: 1,
            ReferenceFulltextStatus.UPLOADED.value: 2,
            ReferenceFulltextStatus.PREPROCESSING.value: 3,
            ReferenceFulltextStatus.INDEXED.value: 4,
        }
        current_value = _enum_value(current)
        incoming_value = _enum_value(incoming)
        return incoming_value if order.get(incoming_value, 0) > order.get(current_value, 0) else current_value


class ReferenceImportService:
    """Import references from uploads, Semantic Scholar, artifacts, BibTeX, or manual input."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.references = WorkspaceReferenceService(db)

    async def import_manual(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        library_status = data.pop("library_status", None) or ReferenceLibraryStatus.INCLUDED
        reference, created = await self.references.upsert_reference(
            workspace_id=workspace_id,
            source_type=ReferenceSourceType.MANUAL,
            library_status=library_status,
            **data,
        )
        return {"reference": serialize_reference(reference), "created": created}

    async def import_semantic_scholar_query(
        self,
        *,
        workspace_id: str,
        query: str,
        discipline: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        search_result = await LiteratureSearchService().search(
            query=query,
            discipline=discipline,
            limit=limit,
        )
        import_result = await self.import_semantic_scholar_papers(
            workspace_id=workspace_id,
            papers=search_result.get("verified_papers") or [],
            source_label=f"Semantic Scholar: {search_result.get('query') or query}",
        )
        return {
            **import_result,
            "query": search_result.get("query"),
            "retrieval": search_result.get("retrieval"),
        }

    async def import_semantic_scholar_papers(
        self,
        *,
        workspace_id: str,
        papers: Iterable[dict[str, Any]],
        source_label: str | None = None,
        source_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        imported: list[dict[str, Any]] = []
        created_count = 0
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            title = str(paper.get("title") or "").strip()
            if not title:
                continue
            external_id = str(paper.get("external_id") or paper.get("paperId") or "").strip()
            reference, created = await self.references.upsert_reference(
                workspace_id=workspace_id,
                title=title,
                authors=paper.get("authors"),
                year=paper.get("year"),
                venue=paper.get("venue"),
                doi=paper.get("doi"),
                url=paper.get("url"),
                abstract=paper.get("abstract"),
                citation_count=paper.get("citations_count") or paper.get("citation_count"),
                source_type=ReferenceSourceType.SEMANTIC_SCHOLAR,
                source_label=source_label or "Semantic Scholar",
                source_artifact_id=source_artifact_id,
                verified_at=utc_now(),
                library_status=ReferenceLibraryStatus.CANDIDATE,
                evidence_level=ReferenceEvidenceLevel.EXTERNAL_VERIFIED,
                external_ids=[
                    {
                        "source": "semantic_scholar",
                        "external_id": external_id,
                        "url": paper.get("url"),
                    }
                ]
                if external_id
                else [],
                commit=False,
            )
            created_count += 1 if created else 0
            imported.append(serialize_reference(reference))

        await self.db.commit()
        return {"imported": len(imported), "created": created_count, "items": imported}

    async def import_deep_search_artifact(
        self,
        *,
        workspace_id: str,
        artifact_ids: Sequence[str],
    ) -> dict[str, Any]:
        if not artifact_ids:
            return {"imported": 0, "created": 0, "items": []}
        result = await self.db.execute(
            select(Artifact).where(
                Artifact.workspace_id == workspace_id,
                Artifact.id.in_([str(item) for item in artifact_ids]),
            )
        )
        artifacts = list(result.scalars().all())
        candidates: list[dict[str, Any]] = []
        for artifact in artifacts:
            content = artifact.content if isinstance(artifact.content, dict) else {}
            for paper in self._iter_artifact_reference_candidates(content):
                paper = dict(paper)
                paper.setdefault("source_artifact_id", str(artifact.id))
                candidates.append(paper)

        imported: list[dict[str, Any]] = []
        created_count = 0
        for candidate in candidates:
            title = str(candidate.get("title") or "").strip()
            if not title:
                continue
            reference, created = await self.references.upsert_reference(
                workspace_id=workspace_id,
                title=title,
                authors=candidate.get("authors"),
                year=candidate.get("year"),
                venue=candidate.get("venue"),
                doi=candidate.get("doi"),
                url=candidate.get("url"),
                abstract=candidate.get("abstract") or candidate.get("summary"),
                citation_count=candidate.get("citations_count") or candidate.get("citation_count"),
                source_type=ReferenceSourceType.DEEP_SEARCH,
                source_label="Deep search",
                source_artifact_id=str(candidate.get("source_artifact_id") or ""),
                library_status=ReferenceLibraryStatus.CANDIDATE,
                evidence_level=ReferenceEvidenceLevel.EXTERNAL_VERIFIED
                if candidate.get("external_id") or candidate.get("doi")
                else ReferenceEvidenceLevel.METADATA_ONLY,
                external_ids=[
                    {
                        "source": str(candidate.get("source") or "deep_search"),
                        "external_id": str(candidate.get("external_id") or ""),
                        "url": candidate.get("url"),
                    }
                ]
                if candidate.get("external_id")
                else [],
                commit=False,
            )
            created_count += 1 if created else 0
            imported.append(serialize_reference(reference))
        await self.db.commit()
        return {"imported": len(imported), "created": created_count, "items": imported}

    async def import_bibtex(self, *, workspace_id: str, content: str) -> dict[str, Any]:
        entries = BibTeXParser().parse(content)
        imported: list[dict[str, Any]] = []
        created_count = 0
        for entry in entries:
            payload = _paper_candidate_from_bibtex(entry)
            reference, created = await self.references.upsert_reference(
                workspace_id=workspace_id,
                title=payload.get("title") or "Untitled Reference",
                authors=payload.get("authors"),
                year=payload.get("year"),
                venue=payload.get("venue"),
                doi=payload.get("doi"),
                source_type=ReferenceSourceType.BIBTEX,
                source_label="BibTeX import",
                library_status=ReferenceLibraryStatus.INCLUDED,
                evidence_level=ReferenceEvidenceLevel.METADATA_ONLY,
                citation_key=payload.get("citation_key"),
                bibtex_entry_type=payload.get("bibtex_entry_type"),
                bibtex_fields=payload.get("bibtex_fields"),
                commit=False,
            )
            created_count += 1 if created else 0
            imported.append(serialize_reference(reference))
        await self.db.commit()
        return {"imported": len(imported), "created": created_count, "items": imported}

    async def import_uploaded_pdf(
        self,
        *,
        workspace_id: str,
        filename: str,
        content_type: str | None,
        content: bytes,
        task_service: Any | None = None,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        if not is_pdf_upload(filename, content_type):
            raise ValueError("Reference uploads must be PDF files")
        safe_name = sanitize_upload_filename(filename)
        output_dir = workspace_upload_dir(workspace_id, REFERENCE_UPLOAD_BUCKET)
        target = next_available_path(output_dir, safe_name)
        target.write_bytes(content)

        preview = extract_document_preview(
            safe_name,
            content_type,
            content=content,
        )
        title = str(preview.get("title") or "").strip() or target.stem
        file_hash = sha256_bytes(content)
        reference, _created = await self.references.upsert_reference(
            workspace_id=workspace_id,
            title=title,
            authors=preview.get("authors"),
            source_type=ReferenceSourceType.UPLOAD,
            source_label="PDF upload",
            library_status=ReferenceLibraryStatus.INCLUDED,
            evidence_level=ReferenceEvidenceLevel.UPLOADED_FULLTEXT,
            fulltext_status=ReferenceFulltextStatus.UPLOADED,
            external_ids=[
                {
                    "source": "upload_sha256",
                    "external_id": file_hash,
                    "url": None,
                }
            ],
            dedupe_by_title=False,
            commit=False,
        )
        public_url = workspace_upload_public_url(workspace_id, target, root=DEFAULT_WORKSPACE_UPLOAD_ROOT)
        asset = ReferenceAsset(
            workspace_id=workspace_id,
            reference_id=str(reference.id),
            asset_type=ReferenceAssetType.PDF,
            file_path=str(target),
            virtual_path=f"{REFERENCE_UPLOAD_BUCKET}/{target.name}",
            public_url=public_url,
            content_type=content_type,
            file_size=len(content),
            file_hash=file_hash,
            page_count=safe_int(preview.get("page_count")),
            preprocess_status=ReferencePreprocessStatus.PENDING,
        )
        self.db.add(asset)
        await self.db.flush()

        if len(content) > REFERENCE_PREPROCESS_THRESHOLD_BYTES and task_service and user_id:
            reference.fulltext_status = ReferenceFulltextStatus.PREPROCESSING
            asset.preprocess_status = ReferencePreprocessStatus.PENDING
            await self.db.commit()
            await self.db.refresh(reference)
            await self.db.refresh(asset)
            try:
                task_id = await task_service.submit_task(
                    user_id=user_id,
                    task_type="reference_preprocess",
                    payload={
                        "workspace_id": workspace_id,
                        "reference_id": str(reference.id),
                        "asset_id": str(asset.id),
                        "thread_id": thread_id,
                        "filename": target.name,
                        "content_type": content_type,
                        "source_path": str(target),
                        "output_dir": str(target.parent / "_preprocessed" / target.stem),
                        "output_virtual_root": f"{REFERENCE_UPLOAD_BUCKET}/_preprocessed/{target.stem}",
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to schedule reference preprocess for workspace=%s reference=%s asset=%s",
                    workspace_id,
                    reference.id,
                    asset.id,
                    exc_info=True,
                )
                reference.fulltext_status = ReferenceFulltextStatus.UPLOADED
                asset.preprocess_status = ReferencePreprocessStatus.FAILED
                asset.preprocess_error = str(exc)
                await self.db.commit()
                await self.db.refresh(reference)
                await self.db.refresh(asset)
                preprocess = {
                    "status": "failed",
                    "error": str(exc),
                    "message": "Reference Library 后台解析任务提交失败，PDF 已保存，可稍后重新解析。",
                }
            else:
                asset.preprocess_task_id = str(task_id)
                await self.db.commit()
                await self.db.refresh(reference)
                await self.db.refresh(asset)
                preprocess = {
                    "status": "pending",
                    "task_id": str(task_id),
                    "message": "文件较大，已进入 Reference Library 后台解析队列；解析完成前不要引用全文内容。",
                }
        else:
            preprocess = await ReferencePreprocessService(self.db).process_asset(
                workspace_id=workspace_id,
                reference_id=str(reference.id),
                asset_id=str(asset.id),
                filename=target.name,
                content_type=content_type,
                source_path=target,
                output_dir=target.parent / "_preprocessed" / target.stem,
                output_virtual_root=f"{REFERENCE_UPLOAD_BUCKET}/_preprocessed/{target.stem}",
                commit=True,
            )
            await self.db.refresh(reference)
            await self.db.refresh(asset)

        await _sync_reference_assets_to_dataservice(self.db, reference)
        await self.db.commit()

        return {
            "success": True,
            "reference": serialize_reference(reference),
            "asset": serialize_asset(asset),
            "filename": target.name,
            "size_bytes": len(content),
            "workspace_id": workspace_id,
            "preprocess": preprocess,
        }

    @staticmethod
    def _iter_artifact_reference_candidates(content: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for key in ("verified_papers", "semantic_scholar_results"):
            values = content.get(key)
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))
        return candidates


class ReferencePreprocessService:
    """Preprocess uploaded full text and build outline/text-unit indexes."""

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process_asset(
        self,
        *,
        workspace_id: str,
        reference_id: str,
        asset_id: str,
        filename: str,
        content_type: str | None,
        source_path: Path,
        output_dir: Path,
        output_virtual_root: str,
        task_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        reference = await WorkspaceReferenceService(self.db).get(workspace_id, reference_id)
        if reference is None:
            raise ValueError(f"Reference not found: {reference_id}")
        asset = await self._get_asset(workspace_id, asset_id)
        if asset is None:
            raise ValueError(f"Reference asset not found: {asset_id}")

        asset.preprocess_status = ReferencePreprocessStatus.RUNNING
        if task_id:
            asset.preprocess_task_id = task_id
        reference.fulltext_status = ReferenceFulltextStatus.PREPROCESSING
        await self.db.flush()

        result = await get_upload_preprocessor_service().preprocess_file(
            filename=filename,
            content_type=content_type,
            source_path=source_path,
            output_dir=output_dir,
            output_virtual_root=output_virtual_root,
        )
        metadata = await self.apply_preprocess_result(
            workspace_id=workspace_id,
            reference_id=reference_id,
            asset_id=asset_id,
            result=result,
            task_id=task_id,
        )
        if commit:
            await self.db.commit()
        return metadata

    async def apply_preprocess_result(
        self,
        *,
        workspace_id: str,
        reference_id: str,
        asset_id: str,
        result: UploadPreprocessResult,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        reference = await WorkspaceReferenceService(self.db).get(workspace_id, reference_id)
        asset = await self._get_asset(workspace_id, asset_id)
        if reference is None or asset is None:
            raise ValueError("Reference or asset not found")

        metadata = result.to_metadata()
        if task_id:
            metadata["task_id"] = task_id
            asset.preprocess_task_id = task_id
        asset.manifest_path = result.manifest_path
        asset.markdown_paths = list(result.markdown_paths)
        asset.preprocess_error = result.error

        if result.status == "succeeded":
            asset.preprocess_status = ReferencePreprocessStatus.SUCCEEDED
            reference.fulltext_status = ReferenceFulltextStatus.INDEXED
            reference.evidence_level = ReferenceEvidenceLevel.INDEXED_FULLTEXT
            page_map = await self._load_preprocess_page_map(reference, result.manifest_path)
            await self._delete_preprocessed_assets(reference, asset)
            await self._register_preprocessed_assets(reference, asset, result)
            await self._rebuild_outline_and_text_units(
                reference,
                asset,
                result.markdown_paths,
                page_map=page_map,
            )
            await self._sync_source_index(reference)
        elif result.status in {"disabled", "skipped"}:
            asset.preprocess_status = ReferencePreprocessStatus.SKIPPED
            reference.fulltext_status = ReferenceFulltextStatus.UPLOADED
            reference.evidence_level = WorkspaceReferenceService._max_evidence_level(
                reference.evidence_level,
                ReferenceEvidenceLevel.UPLOADED_FULLTEXT,
            )  # type: ignore[assignment]
        else:
            asset.preprocess_status = ReferencePreprocessStatus.FAILED
            reference.fulltext_status = ReferenceFulltextStatus.FAILED
        await WorkspaceReferenceService(self.db)._sync_source_record(reference)
        await _sync_reference_assets_to_dataservice(self.db, reference)
        return metadata

    async def _get_asset(self, workspace_id: str, asset_id: str) -> ReferenceAsset | None:
        result = await self.db.execute(
            select(ReferenceAsset).where(
                ReferenceAsset.workspace_id == workspace_id,
                ReferenceAsset.id == asset_id,
            )
        )
        return result.scalar_one_or_none()

    async def _load_preprocess_page_map(
        self,
        reference: WorkspaceReference,
        manifest_path: str | None,
    ) -> dict[str, dict[str, Any]]:
        if not manifest_path:
            return {}
        try:
            disk_path = resolve_workspace_upload_stored_path(
                reference.workspace_id,
                manifest_path,
                root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                allow_root_prefixed_relative=True,
            )
            manifest = json.loads(disk_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "Failed to read reference preprocess manifest path=%s reference=%s",
                manifest_path,
                reference.id,
                exc_info=True,
            )
            return {}
        pages = manifest.get("pages") if isinstance(manifest, dict) else None
        if not isinstance(pages, list):
            return {}
        page_map: dict[str, dict[str, Any]] = {}
        for item in pages:
            if not isinstance(item, dict):
                continue
            markdown_path = str(item.get("markdown_path") or "").strip()
            if not markdown_path:
                continue
            page_start = safe_int(item.get("page_start") or item.get("page_number"))
            page_end = safe_int(item.get("page_end") or item.get("page_number"))
            if page_start is None:
                continue
            page_map[markdown_path] = {
                "page_start": page_start,
                "page_end": page_end or page_start,
                "page_source": str(item.get("page_source") or "manifest").strip() or "manifest",
            }
        return page_map

    async def _delete_preprocessed_assets(
        self,
        reference: WorkspaceReference,
        source_asset: ReferenceAsset,
    ) -> None:
        await self.db.execute(
            delete(ReferenceAsset).where(
                ReferenceAsset.workspace_id == reference.workspace_id,
                ReferenceAsset.reference_id == reference.id,
                ReferenceAsset.source_asset_id == source_asset.id,
                ReferenceAsset.asset_type.in_(
                    [
                        ReferenceAssetType.MARKDOWN,
                        ReferenceAssetType.MANIFEST,
                    ]
                ),
            )
        )

    async def _register_preprocessed_assets(
        self,
        reference: WorkspaceReference,
        source_asset: ReferenceAsset,
        result: UploadPreprocessResult,
    ) -> None:
        for markdown_path in result.markdown_paths:
            self.db.add(
                ReferenceAsset(
                    workspace_id=reference.workspace_id,
                    reference_id=reference.id,
                    source_asset_id=str(source_asset.id),
                    asset_type=ReferenceAssetType.MARKDOWN,
                    file_path=markdown_path,
                    virtual_path=markdown_path,
                    public_url=workspace_upload_public_url(
                        reference.workspace_id,
                        markdown_path,
                        root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                    ),
                    content_type="text/markdown",
                    preprocess_status=ReferencePreprocessStatus.SUCCEEDED,
                    preprocess_task_id=source_asset.preprocess_task_id,
                )
            )
        if result.manifest_path:
            self.db.add(
                ReferenceAsset(
                    workspace_id=reference.workspace_id,
                    reference_id=reference.id,
                    source_asset_id=str(source_asset.id),
                    asset_type=ReferenceAssetType.MANIFEST,
                    file_path=result.manifest_path,
                    virtual_path=result.manifest_path,
                    public_url=workspace_upload_public_url(
                        reference.workspace_id,
                        result.manifest_path,
                        root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                    ),
                    content_type="application/json",
                    preprocess_status=ReferencePreprocessStatus.SUCCEEDED,
                    preprocess_task_id=source_asset.preprocess_task_id,
                )
            )

    async def _rebuild_outline_and_text_units(
        self,
        reference: WorkspaceReference,
        asset: ReferenceAsset,
        markdown_paths: Sequence[str],
        *,
        page_map: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.db.execute(
            delete(ReferenceTextUnit).where(
                ReferenceTextUnit.workspace_id == reference.workspace_id,
                ReferenceTextUnit.reference_id == reference.id,
                ReferenceTextUnit.unit_type != ReferenceTextUnitType.ABSTRACT,
            )
        )
        await self.db.execute(
            delete(ReferenceOutlineNode).where(
                ReferenceOutlineNode.workspace_id == reference.workspace_id,
                ReferenceOutlineNode.reference_id == reference.id,
            )
        )
        sort_order = 0
        for doc_index, markdown_path in enumerate(markdown_paths):
            try:
                disk_path = resolve_workspace_upload_stored_path(
                    reference.workspace_id,
                    markdown_path,
                    root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                    allow_root_prefixed_relative=True,
                )
                text = disk_path.read_text(encoding="utf-8")
            except Exception:
                logger.warning(
                    "Failed to read reference markdown path=%s reference=%s",
                    markdown_path,
                    reference.id,
                    exc_info=True,
                )
                continue
            page_info = (page_map or {}).get(str(markdown_path), {})
            page_start = safe_int(page_info.get("page_start")) or doc_index + 1
            page_end = safe_int(page_info.get("page_end")) or page_start
            page_source = str(page_info.get("page_source") or "layout_result_index")
            sort_order = await self._index_markdown_document(
                reference=reference,
                asset=asset,
                markdown=text,
                doc_index=doc_index,
                page_start=page_start,
                page_end=page_end,
                page_source=page_source,
                initial_sort_order=sort_order,
            )

    async def _sync_source_index(self, reference: WorkspaceReference) -> None:
        outline_result = await self.db.execute(
            select(ReferenceOutlineNode)
            .where(
                ReferenceOutlineNode.workspace_id == reference.workspace_id,
                ReferenceOutlineNode.reference_id == reference.id,
            )
            .order_by(ReferenceOutlineNode.sort_order)
        )
        text_unit_result = await self.db.execute(
            select(ReferenceTextUnit)
            .where(
                ReferenceTextUnit.workspace_id == reference.workspace_id,
                ReferenceTextUnit.reference_id == reference.id,
            )
            .order_by(ReferenceTextUnit.unit_index)
        )
        outline_nodes = [
            {
                "id": str(node.id),
                "workspace_id": str(node.workspace_id),
                "source_id": str(node.reference_id),
                "parent_id": node.parent_id,
                "section_path": node.section_path,
                "title": node.title,
                "level": node.level,
                "sort_order": node.sort_order,
                "page_start": node.page_start,
                "page_end": node.page_end,
                "char_start": node.char_start,
                "char_end": node.char_end,
                "summary": node.summary,
                "keywords_json": list(node.keywords or []),
            }
            for node in outline_result.scalars().all()
        ]
        text_units = [
            {
                "id": str(unit.id),
                "workspace_id": str(unit.workspace_id),
                "source_id": str(unit.reference_id),
                "outline_node_id": unit.outline_node_id,
                "source_asset_id": unit.asset_id,
                "unit_type": _enum_value(unit.unit_type),
                "unit_index": unit.unit_index,
                "content": unit.content,
                "search_text": unit.search_text,
                "token_count": unit.token_count,
                "page_start": unit.page_start,
                "page_end": unit.page_end,
                "char_start": unit.char_start,
                "char_end": unit.char_end,
                "metadata_json": dict(unit.unit_metadata or {}),
            }
            for unit in text_unit_result.scalars().all()
        ]
        await SourceDataService(self.db, autocommit=False).replace_source_index(
            workspace_id=str(reference.workspace_id),
            source_id=str(reference.id),
            outline_nodes=outline_nodes,
            text_units=text_units,
        )

    async def _index_markdown_document(
        self,
        *,
        reference: WorkspaceReference,
        asset: ReferenceAsset,
        markdown: str,
        doc_index: int,
        page_start: int,
        page_end: int,
        page_source: str,
        initial_sort_order: int,
    ) -> int:
        sections = self._split_markdown_sections(markdown)
        if not sections:
            chunks = self._chunk_text(markdown)
            sections = [
                {
                    "level": 1,
                    "title": f"Full text {index + 1}",
                    "content": chunk,
                    "char_start": 0,
                    "char_end": len(chunk),
                }
                for index, chunk in enumerate(chunks)
            ]

        counters = [0] * 8
        stack: dict[int, ReferenceOutlineNode] = {}
        sort_order = initial_sort_order
        for index, section in enumerate(sections):
            content = str(section.get("content") or "").strip()
            if not content:
                continue
            level = max(1, min(int(section.get("level") or 1), 6))
            counters[level] += 1
            for pos in range(level + 1, len(counters)):
                counters[pos] = 0
            path_parts = [str(counters[pos]) for pos in range(1, level + 1) if counters[pos]]
            section_path = ".".join(path_parts) or str(index + 1)
            parent = stack.get(level - 1)
            node = ReferenceOutlineNode(
                workspace_id=reference.workspace_id,
                reference_id=reference.id,
                parent_id=str(parent.id) if parent is not None else None,
                section_path=section_path,
                title=str(section.get("title") or f"Section {index + 1}").strip(),
                normalized_title=normalize_title(str(section.get("title") or "")),
                level=level,
                sort_order=sort_order,
                page_start=page_start,
                page_end=page_end,
                char_start=safe_int(section.get("char_start")),
                char_end=safe_int(section.get("char_end")),
                summary=" ".join(content.split())[:360],
                keywords=[],
            )
            self.db.add(node)
            await self.db.flush()
            stack[level] = node
            for stale_level in list(stack):
                if stale_level > level:
                    stack.pop(stale_level, None)

            self.db.add(
                ReferenceTextUnit(
                    workspace_id=reference.workspace_id,
                    reference_id=reference.id,
                    outline_node_id=str(node.id),
                    asset_id=str(asset.id),
                    unit_type=ReferenceTextUnitType.SECTION,
                    unit_index=sort_order,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    content=content,
                    token_count=len(content.split()),
                    char_start=node.char_start,
                    char_end=node.char_end,
                    search_text=f"{reference.title}\n{node.title}\n{content}",
                    unit_metadata={
                        "section_path": section_path,
                        "doc_index": doc_index,
                        "page_source": page_source,
                    },
                )
            )
            sort_order += 1
        return sort_order

    def _split_markdown_sections(self, markdown: str) -> list[dict[str, Any]]:
        lines = markdown.splitlines()
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        char_offset = 0
        for line in lines:
            match = self.HEADING_RE.match(line)
            if match:
                if current is not None:
                    current["content"] = "\n".join(current.pop("lines")).strip()
                    current["char_end"] = char_offset
                    sections.append(current)
                current = {
                    "level": len(match.group(1)),
                    "title": match.group(2).strip(),
                    "lines": [],
                    "char_start": char_offset,
                }
            elif current is not None:
                current["lines"].append(line)
            char_offset += len(line) + 1
        if current is not None:
            current["content"] = "\n".join(current.pop("lines")).strip()
            current["char_end"] = char_offset
            sections.append(current)
        return [section for section in sections if str(section.get("content") or "").strip()]

    @staticmethod
    def _chunk_text(text: str, *, max_chars: int = 5000) -> list[str]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        return [normalized[index : index + max_chars] for index in range(0, len(normalized), max_chars)]


class ReferenceIndexService:
    """Outline-first retrieval over workspace references."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.references = WorkspaceReferenceService(db)

    async def get_library_outline(self, workspace_id: str) -> list[dict[str, Any]]:
        ref_result = await self.db.execute(
            select(WorkspaceReference)
            .where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status != ReferenceLibraryStatus.EXCLUDED,
            )
            .order_by(WorkspaceReference.library_status, WorkspaceReference.updated_at.desc())
        )
        references = list(ref_result.scalars().all())
        output: list[dict[str, Any]] = []
        for reference in references:
            nodes = await self.get_reference_outline(workspace_id, str(reference.id), limit=24)
            output.append(
                {
                    "reference": serialize_reference(reference),
                    "outline": nodes,
                }
            )
        return output

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        outline = await self.get_library_outline(workspace_id)
        if not outline:
            return ""
        lines = ["## Reference Library Outline"]
        for index, item in enumerate(outline[:30], start=1):
            reference = item["reference"]
            lines.append(
                f"### [{index}] {reference['title']} "
                f"({reference.get('year') or 'n.d.'}, key={reference['citation_key']})"
            )
            nodes = item.get("outline") or []
            if nodes:
                toc = "; ".join(
                    f"{node['section_path']} {node['title']}"
                    for node in nodes[:12]
                )
                lines.append(f"- Outline: {toc}")
            else:
                status = reference.get("fulltext_status")
                abstract = str(reference.get("abstract") or "").strip()
                if abstract:
                    lines.append(f"- Metadata/abstract only: {' '.join(abstract.split())[:240]}")
                else:
                    lines.append(f"- Full-text status: {status}; no outline is available yet.")
        return "\n".join(lines)

    async def get_reference_outline(
        self,
        workspace_id: str,
        reference_id: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(ReferenceOutlineNode)
            .where(
                ReferenceOutlineNode.workspace_id == workspace_id,
                ReferenceOutlineNode.reference_id == reference_id,
            )
            .order_by(ReferenceOutlineNode.sort_order)
            .limit(max(1, min(limit, 500)))
        )
        return [serialize_outline_node(node) for node in result.scalars().all()]

    async def read_outline_node(
        self,
        *,
        workspace_id: str,
        reference_id: str,
        node_id: str,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(ReferenceTextUnit).where(
                ReferenceTextUnit.workspace_id == workspace_id,
                ReferenceTextUnit.reference_id == reference_id,
                ReferenceTextUnit.outline_node_id == node_id,
            )
        )
        units = [serialize_text_unit(unit) for unit in result.scalars().all()]
        if not units:
            return None
        return {"units": units, "content": "\n\n".join(unit["content"] for unit in units)}

    async def read_pages(
        self,
        *,
        workspace_id: str,
        reference_id: str,
        page_start: int,
        page_end: int,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(ReferenceTextUnit)
            .where(
                ReferenceTextUnit.workspace_id == workspace_id,
                ReferenceTextUnit.reference_id == reference_id,
                ReferenceTextUnit.page_start.is_not(None),
                ReferenceTextUnit.page_start <= page_end,
                func.coalesce(
                    ReferenceTextUnit.page_end,
                    ReferenceTextUnit.page_start,
                )
                >= page_start,
            )
            .order_by(ReferenceTextUnit.unit_index)
        )
        return [serialize_text_unit(unit) for unit in result.scalars().all()]

    async def search_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        reference_ids: Sequence[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []
        stmt = select(ReferenceTextUnit).where(
            ReferenceTextUnit.workspace_id == workspace_id,
            ReferenceTextUnit.search_text.ilike(f"%{normalized_query}%"),
        )
        if reference_ids:
            stmt = stmt.where(ReferenceTextUnit.reference_id.in_([str(item) for item in reference_ids]))
        result = await self.db.execute(
            stmt.order_by(ReferenceTextUnit.updated_at.desc()).limit(max(1, min(limit, 50)))
        )
        return [serialize_text_unit(unit) for unit in result.scalars().all()]

    async def search_workspace_sections(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        return await self.search_text_units(workspace_id=workspace_id, query=query, limit=limit)

    async def get_reference_section(
        self,
        *,
        reference_id: str,
        section_path: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._get_reference_section(
            reference_id=reference_id,
            section_path=section_path,
            workspace_id=workspace_id,
        )

    async def get_reference_section_by_title(
        self,
        *,
        reference_id: str,
        section_title: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any] | None:
        stmt = select(ReferenceOutlineNode).where(ReferenceOutlineNode.reference_id == reference_id)
        if workspace_id:
            stmt = stmt.where(ReferenceOutlineNode.workspace_id == workspace_id)
        stmt = stmt.where(ReferenceOutlineNode.title.ilike(f"%{section_title}%"))
        result = await self.db.execute(stmt.order_by(ReferenceOutlineNode.sort_order).limit(1))
        node = result.scalar_one_or_none()
        if node is None:
            return None
        content = await self.read_outline_node(
            workspace_id=str(node.workspace_id),
            reference_id=str(node.reference_id),
            node_id=str(node.id),
        )
        return {
            "reference_id": str(node.reference_id),
            "node_id": str(node.id),
            "title": node.title,
            "section_path": node.section_path,
            "content": content["content"] if content else "",
            "units": content["units"] if content else [],
        }

    async def _get_reference_section(
        self,
        *,
        reference_id: str,
        section_path: str,
        workspace_id: str | None,
    ) -> dict[str, Any] | None:
        stmt = select(ReferenceOutlineNode).where(
            ReferenceOutlineNode.reference_id == reference_id,
            ReferenceOutlineNode.section_path == section_path,
        )
        if workspace_id:
            stmt = stmt.where(ReferenceOutlineNode.workspace_id == workspace_id)
        result = await self.db.execute(stmt.limit(1))
        node = result.scalar_one_or_none()
        if node is None:
            return None
        content = await self.read_outline_node(
            workspace_id=str(node.workspace_id),
            reference_id=str(node.reference_id),
            node_id=str(node.id),
        )
        return {
            "reference_id": str(node.reference_id),
            "node_id": str(node.id),
            "title": node.title,
            "section_path": node.section_path,
            "content": content["content"] if content else "",
            "units": content["units"] if content else [],
        }


class ReferenceUsageService:
    """Persist writing-time reference usage and keep citation state queryable."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_usage(
        self,
        *,
        workspace_id: str,
        reference_ids: Sequence[str],
        outline_node_id: str | None = None,
        text_unit_id: str | None = None,
        execution_id: str | None = None,
        task_id: str | None = None,
        artifact_id: str | None = None,
        latex_project_id: str | None = None,
        target_section: str | None = None,
        claim_text: str | None = None,
        generated_text: str | None = None,
        usage_type: ReferenceUsageType | str = ReferenceUsageType.CITATION_ONLY,
        accepted_status: ReferenceAcceptedStatus | str = ReferenceAcceptedStatus.PENDING,
        mark_used_in_draft: bool = True,
        commit: bool = True,
    ) -> dict[str, Any]:
        unique_ids = [
            item
            for item in dict.fromkeys(str(reference_id).strip() for reference_id in reference_ids)
            if item
        ]
        if not workspace_id or not unique_ids:
            return {"recorded": 0, "reference_ids": []}

        result = await self.db.execute(
            select(WorkspaceReference).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.id.in_(unique_ids),
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status != ReferenceLibraryStatus.EXCLUDED,
            )
        )
        references = list(result.scalars().all())
        recorded_ids: list[str] = []
        resolved_usage_type = _coerce_enum_value(
            ReferenceUsageType,
            usage_type,
            "usage_type",
        )
        resolved_accepted_status = _coerce_enum_value(
            ReferenceAcceptedStatus,
            accepted_status,
            "accepted_status",
        )
        for reference in references:
            reference_id = str(reference.id)
            self.db.add(
                ReferenceUsageEvent(
                    workspace_id=workspace_id,
                    reference_id=reference_id,
                    outline_node_id=outline_node_id,
                    text_unit_id=text_unit_id,
                    execution_id=execution_id,
                    task_id=task_id,
                    artifact_id=artifact_id,
                    latex_project_id=latex_project_id,
                    target_section=target_section,
                    claim_text=claim_text,
                    generated_text=generated_text,
                    citation_key=reference.citation_key,
                    usage_type=resolved_usage_type,
                    accepted_status=resolved_accepted_status,
                )
            )
            if mark_used_in_draft and _enum_value(reference.library_status) in {
                ReferenceLibraryStatus.CANDIDATE.value,
                ReferenceLibraryStatus.INCLUDED.value,
            }:
                reference.library_status = ReferenceLibraryStatus.USED_IN_DRAFT
            recorded_ids.append(reference_id)

        if commit:
            await self.db.commit()
        return {"recorded": len(recorded_ids), "reference_ids": recorded_ids}

    async def record_usage_by_citation_keys(
        self,
        *,
        workspace_id: str,
        citation_keys: Sequence[str],
        execution_id: str | None = None,
        task_id: str | None = None,
        artifact_id: str | None = None,
        latex_project_id: str | None = None,
        target_section: str | None = None,
        claim_text: str | None = None,
        generated_text: str | None = None,
        usage_type: ReferenceUsageType | str = ReferenceUsageType.CITATION_ONLY,
        accepted_status: ReferenceAcceptedStatus | str = ReferenceAcceptedStatus.PENDING,
        mark_used_in_draft: bool = True,
        commit: bool = True,
    ) -> dict[str, Any]:
        unique_keys = [
            key
            for key in dict.fromkeys(str(item).strip() for item in citation_keys)
            if key
        ]
        if not workspace_id or not unique_keys:
            return {"recorded": 0, "reference_ids": [], "citation_keys": []}
        result = await self.db.execute(
            select(WorkspaceReference).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.citation_key.in_(unique_keys),
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status != ReferenceLibraryStatus.EXCLUDED,
            )
        )
        references = list(result.scalars().all())
        usage_result = await self.record_usage(
            workspace_id=workspace_id,
            reference_ids=[str(reference.id) for reference in references],
            execution_id=execution_id,
            task_id=task_id,
            artifact_id=artifact_id,
            latex_project_id=latex_project_id,
            target_section=target_section,
            claim_text=claim_text,
            generated_text=generated_text,
            usage_type=usage_type,
            accepted_status=accepted_status,
            mark_used_in_draft=mark_used_in_draft,
            commit=commit,
        )
        usage_result["citation_keys"] = [
            str(reference.citation_key) for reference in references
        ]
        return usage_result


_LATEX_CITATION_RE = re.compile(r"\\cite[a-zA-Z]*(?:\[[^\]]*\])*\{([^{}]*)\}")


def _extract_citation_keys(latex_content: str) -> set[str]:
    """Extract all citation keys from LaTeX content."""
    keys: set[str] = set()
    for match in _LATEX_CITATION_RE.finditer(latex_content):
        raw = match.group(1)
        for key in raw.split(","):
            key = key.strip()
            if key:
                keys.add(key)
    return keys


class ReferenceBibTeXService:
    """Generate and synchronize BibTeX from workspace references."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build_bibtex(
        self,
        *,
        workspace_id: str,
        scope: ReferenceBibtexScope | str = ReferenceBibtexScope.INCLUDED_AND_CORE,
    ) -> dict[str, Any]:
        scope_value = _coerce_enum_value(ReferenceBibtexScope, scope, "scope")
        references = await self._load_scope(workspace_id, scope_value)
        bibliography = await SourceDataService(self.db, autocommit=False).build_bibliography(
            SourceBibliographyCreateCommand(
                workspace_id=workspace_id,
                source_ids=[str(reference.id) for reference in references],
                include_excluded=True,
            )
        )
        content = bibliography.content or ""
        return {
            "workspace_id": workspace_id,
            "scope": scope_value,
            "content": content,
            "reference_count": bibliography.count,
            "checksum": sha256_bytes(content.encode("utf-8")),
        }

    async def validate_bibtex(self, *, workspace_id: str) -> dict[str, Any]:
        references = await self._load_scope(workspace_id, ReferenceBibtexScope.ALL_NON_EXCLUDED)
        keys: dict[str, int] = {}
        missing: list[str] = []
        for reference in references:
            if not reference.citation_key:
                missing.append(str(reference.id))
            keys[reference.citation_key] = keys.get(reference.citation_key, 0) + 1
        duplicates = [key for key, count in keys.items() if key and count > 1]
        return {
            "ok": not missing and not duplicates,
            "missing_citation_key_reference_ids": missing,
            "duplicate_citation_keys": duplicates,
        }

    async def validate_citations(
        self,
        *,
        workspace_id: str,
        latex_content: str,
    ) -> dict[str, Any]:
        """Validate cite keys in LaTeX content against workspace references.

        Returns:
            dict with valid, missing_keys, unused_bib_keys, unverified_keys.
        """
        cited_keys = _extract_citation_keys(latex_content)
        references = await SourceDataService(self.db, autocommit=False).list_sources(
            workspace_id=workspace_id,
            include_excluded=True,
            limit=5000,
        )
        workspace_keys = {ref.citation_key for ref in references if ref.citation_key}
        verified_keys = {
            ref.citation_key
            for ref in references
            if ref.citation_key
            and str(ref.evidence_level) not in {
                ReferenceEvidenceLevel.METADATA_ONLY.value,
            }
        }

        missing_keys = sorted(cited_keys - workspace_keys)
        unused_bib_keys = sorted(workspace_keys - cited_keys)
        unverified_keys = sorted(cited_keys & (workspace_keys - verified_keys))

        return {
            "valid": not missing_keys and not unverified_keys,
            "missing_keys": missing_keys,
            "unused_bib_keys": unused_bib_keys,
            "unverified_keys": unverified_keys,
        }

    async def sync_prism(
        self,
        *,
        workspace_id: str,
        scope: ReferenceBibtexScope | str = ReferenceBibtexScope.INCLUDED_AND_CORE,
    ) -> dict[str, Any]:
        bibtex = await self.build_bibtex(workspace_id=workspace_id, scope=scope)
        workspace_result = await self.db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = workspace_result.scalar_one_or_none()
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        project = await WorkspaceLatexProjectService(self.db).ensure_workspace_project(
            workspace_id=workspace_id,
            project_name=workspace.name,
        )
        project_service = LatexProjectService(self.db)
        await project_service.write_text_file(project, "refs.bib", bibtex["content"])
        await self._ensure_main_tex_bibliography(project_service, project)

        snapshot = ReferenceBibtexSnapshot(
            workspace_id=workspace_id,
            latex_project_id=str(project.id),
            scope=bibtex["scope"],
            content=bibtex["content"],
            reference_count=bibtex["reference_count"],
            checksum=bibtex["checksum"],
        )
        self.db.add(snapshot)
        await self.db.commit()
        return {
            **bibtex,
            "latex_project_id": str(project.id),
            "synced_file": "refs.bib",
        }

    async def _load_scope(
        self,
        workspace_id: str,
        scope: ReferenceBibtexScope | str,
    ) -> list[Any]:
        scope_value = _coerce_enum_value(ReferenceBibtexScope, scope, "scope")
        source_service = SourceDataService(self.db, autocommit=False)
        if scope_value == ReferenceBibtexScope.CORE.value:
            return await source_service.list_sources(
                workspace_id=workspace_id,
                library_status=ReferenceLibraryStatus.CORE.value,
                include_excluded=True,
                limit=5000,
            )
        elif scope_value == ReferenceBibtexScope.INCLUDED_AND_CORE.value:
            sources = []
            for library_status in (
                ReferenceLibraryStatus.CORE.value,
                ReferenceLibraryStatus.INCLUDED.value,
                ReferenceLibraryStatus.USED_IN_DRAFT.value,
            ):
                sources.extend(
                    await source_service.list_sources(
                        workspace_id=workspace_id,
                        library_status=library_status,
                        include_excluded=True,
                        limit=5000,
                    )
                )
            return sorted(sources, key=lambda source: source.citation_key)
        elif scope_value == ReferenceBibtexScope.USED_ONLY.value:
            return await source_service.list_sources(
                workspace_id=workspace_id,
                library_status=ReferenceLibraryStatus.USED_IN_DRAFT.value,
                include_excluded=True,
                limit=5000,
            )
        sources = await source_service.list_sources(
            workspace_id=workspace_id,
            include_excluded=False,
            limit=5000,
        )
        return sorted(sources, key=lambda source: source.citation_key)

    def _format_entry(self, reference: WorkspaceReference) -> str:
        fields = dict(reference.bibtex_fields or {})
        fields.setdefault("title", reference.title)
        if reference.authors:
            fields.setdefault("author", " and ".join(str(author) for author in reference.authors if author))
        if reference.year:
            fields.setdefault("year", str(reference.year))
        if reference.venue:
            field_name = "booktitle" if reference.bibtex_entry_type == "inproceedings" else "journal"
            fields.setdefault(field_name, reference.venue)
        if reference.doi:
            fields.setdefault("doi", reference.doi)
        if reference.url:
            fields.setdefault("url", reference.url)

        rendered_fields = []
        for key in sorted(fields):
            value = clean_bibtex_value(fields[key])
            if value:
                rendered_fields.append(f"  {key} = {{{value}}}")
        joined = ",\n".join(rendered_fields)
        entry_type = reference.bibtex_entry_type or "article"
        return f"@{entry_type}{{{reference.citation_key},\n{joined}\n}}"

    @staticmethod
    async def _ensure_main_tex_bibliography(project_service: LatexProjectService, project: Any) -> None:
        try:
            main_content = project_service.read_text_file(project, project.main_file)
        except FileNotFoundError:
            return
        if "\\bibliography{" in main_content or "\\printbibliography" in main_content:
            return
        insertion = "\n\\bibliographystyle{plain}\n\\bibliography{refs}\n"
        if "\\end{document}" in main_content:
            updated = main_content.replace("\\end{document}", f"{insertion}\\end{{document}}", 1)
        else:
            updated = f"{main_content.rstrip()}\n{insertion}\n"
        await project_service.write_text_file(project, project.main_file, updated)

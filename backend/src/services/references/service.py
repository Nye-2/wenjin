"""Services for the workspace-scoped reference library."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.citation.bibtex.parser import BibTeXParser
from src.academic.literature.search_service import LiteratureSearchService
from src.database import (
    ReferenceBibtexScope,
    ReferenceEvidenceLevel,
    ReferenceFulltextStatus,
    ReferenceLibraryStatus,
    ReferencePreprocessStatus,
    ReferenceSourceType,
)
from src.database.base import generate_uuid
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import WorkspaceAssetCreatePayload
from src.dataservice_client.contracts.source import (
    SourceAssetLinkPayload,
    SourceAssetUpdatePayload,
    SourceBibliographyCreatePayload,
    SourceBibliographySnapshotCreatePayload,
    SourceEvidencePackCreatePayload,
    SourceExternalIdCreatePayload,
    SourceImportPayload,
    SourceIndexReplacePayload,
    SourceUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client
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


@asynccontextmanager
async def _managed_dataservice_client(
    dataservice: AsyncDataServiceClient | None,
):
    if dataservice is not None:
        yield dataservice
        return
    async with dataservice_client() as client:
        yield client


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


def _source_external_id_commands(external_ids: Sequence[dict[str, Any]] | None) -> list[SourceExternalIdCreatePayload]:
    commands: list[SourceExternalIdCreatePayload] = []
    for item in external_ids or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("source") or item.get("provider") or "").strip()
        external_id = str(item.get("external_id") or "").strip()
        if not provider or not external_id:
            continue
        commands.append(
            SourceExternalIdCreatePayload(
                provider=provider,
                external_id=external_id,
                url=item.get("url"),
                metadata_json=dict(item.get("metadata") or item.get("metadata_json") or {}),
            )
        )
    return commands


def _source_import_command(
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
) -> SourceImportPayload:
    resolved_title = str(title or "").strip()
    resolved_authors = parse_authors(authors)
    resolved_year = safe_int(year)
    return SourceImportPayload(
        workspace_id=workspace_id,
        source_kind="paper",
        title=resolved_title,
        normalized_title=normalize_title(resolved_title),
        authors_json=resolved_authors,
        year=resolved_year,
        venue=venue,
        publication_type=publication_type,
        doi=normalize_doi(doi),
        url=url,
        abstract=abstract,
        citation_count=safe_int(citation_count),
        ingest_kind=_enum_value(source_type),
        ingest_label=source_label,
        ingest_execution_id=source_run_id or source_artifact_id,
        verified_at=verified_at if hasattr(verified_at, "isoformat") else utc_now() if verified_at else None,
        library_status=_enum_value(library_status),
        evidence_level=_enum_value(evidence_level),
        fulltext_status=_enum_value(fulltext_status),
        citation_key=citation_key
        or build_citation_key_base(title=resolved_title, authors=resolved_authors, year=resolved_year),
        bibtex_entry_type=bibtex_entry_type
        or guess_bibtex_entry_type(venue=venue, publication_type=publication_type),
        bibtex_fields_json=dict(bibtex_fields or {}),
        external_ids=_source_external_id_commands(external_ids),
        dedupe_by_title=dedupe_by_title,
    )


def _serialize_source_reference(source: Any) -> dict[str, Any]:
    created_at = getattr(source, "created_at", None)
    updated_at = getattr(source, "updated_at", None)
    verified_at = getattr(source, "verified_at", None)
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
        "source_run_id": source.ingest_execution_id,
        "source_artifact_id": source.ingest_execution_id,
        "verified_at": verified_at.isoformat() if verified_at else None,
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
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


class SourceLibraryImportService:
    """Import source-library entries from uploads, Semantic Scholar, artifacts, BibTeX, or manual input."""

    def __init__(self, dataservice: AsyncDataServiceClient | None = None) -> None:
        self._dataservice = dataservice

    async def import_manual(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        library_status = data.pop("library_status", None) or ReferenceLibraryStatus.INCLUDED
        async with _managed_dataservice_client(self._dataservice) as client:
            result = await client.import_source(
                _source_import_command(
                    workspace_id=workspace_id,
                    source_type=ReferenceSourceType.MANUAL,
                    library_status=library_status,
                    **data,
                )
            )
        return {"reference": _serialize_source_reference(result.source), "created": result.created}

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
        async with _managed_dataservice_client(self._dataservice) as client:
            for paper in papers:
                if not isinstance(paper, dict):
                    continue
                title = str(paper.get("title") or "").strip()
                if not title:
                    continue
                external_id = str(paper.get("external_id") or paper.get("paperId") or "").strip()
                result = await client.import_source(
                    _source_import_command(
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
                    )
                )
                created_count += 1 if result.created else 0
                imported.append(_serialize_source_reference(result.source))

        return {"imported": len(imported), "created": created_count, "items": imported}

    async def import_deep_search_artifact(
        self,
        *,
        workspace_id: str,
        artifact_ids: Sequence[str],
    ) -> dict[str, Any]:
        if not artifact_ids:
            return {"imported": 0, "created": 0, "items": []}
        async with _managed_dataservice_client(self._dataservice) as client:
            artifacts = [
                artifact
                for artifact_id in artifact_ids
                if (
                    artifact := await client.get_workspace_artifact(str(artifact_id))
                )
                is not None
                and str(artifact.workspace_id) == workspace_id
            ]
        candidates: list[dict[str, Any]] = []
        for artifact in artifacts:
            content = artifact.content if isinstance(artifact.content, dict) else {}
            for paper in self._iter_artifact_reference_candidates(content):
                paper = dict(paper)
                paper.setdefault("source_artifact_id", str(artifact.id))
                candidates.append(paper)

        imported: list[dict[str, Any]] = []
        created_count = 0
        async with _managed_dataservice_client(self._dataservice) as client:
            for candidate in candidates:
                title = str(candidate.get("title") or "").strip()
                if not title:
                    continue
                result = await client.import_source(
                    _source_import_command(
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
                    )
                )
                created_count += 1 if result.created else 0
                imported.append(_serialize_source_reference(result.source))
        return {"imported": len(imported), "created": created_count, "items": imported}

    async def import_bibtex(self, *, workspace_id: str, content: str) -> dict[str, Any]:
        entries = BibTeXParser().parse(content)
        imported: list[dict[str, Any]] = []
        created_count = 0
        async with _managed_dataservice_client(self._dataservice) as client:
            for entry in entries:
                payload = _paper_candidate_from_bibtex(entry)
                result = await client.import_source(
                    _source_import_command(
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
                    )
                )
                created_count += 1 if result.created else 0
                imported.append(_serialize_source_reference(result.source))
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
        async with _managed_dataservice_client(self._dataservice) as client:
            source_import = await client.import_source(
                _source_import_command(
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
                )
            )
            source = source_import.source
            public_url = workspace_upload_public_url(workspace_id, target, root=DEFAULT_WORKSPACE_UPLOAD_ROOT)
            workspace_asset = await client.register_asset(
                WorkspaceAssetCreatePayload(
                    workspace_id=workspace_id,
                    asset_kind="source_file",
                    name=target.name,
                    title=title,
                    mime_type=content_type,
                    storage_path=str(target),
                    size_bytes=len(content),
                    content_hash=file_hash,
                    created_by="reference_import",
                    source_kind="source",
                    source_id=source.id,
                    metadata_json={
                        "virtual_path": f"{REFERENCE_UPLOAD_BUCKET}/{target.name}",
                        "public_url": public_url,
                        "page_count": safe_int(preview.get("page_count")),
                        "upload_bucket": REFERENCE_UPLOAD_BUCKET,
                    },
                )
            )
            source_asset = await client.link_source_asset(
                SourceAssetLinkPayload(
                    workspace_id=workspace_id,
                    source_id=source.id,
                    workspace_asset_id=workspace_asset.id,
                    asset_type="pdf",
                    preprocess_status=ReferencePreprocessStatus.PENDING.value,
                    metadata_json={
                        "virtual_path": f"{REFERENCE_UPLOAD_BUCKET}/{target.name}",
                        "public_url": public_url,
                        "page_count": safe_int(preview.get("page_count")),
                        "content_type": content_type,
                        "file_size": len(content),
                        "file_hash": file_hash,
                    },
                )
            )

            if len(content) > REFERENCE_PREPROCESS_THRESHOLD_BYTES and task_service and user_id:
                await client.update_source(
                    workspace_id=workspace_id,
                    source_id=source.id,
                    command=SourceUpdatePayload(fulltext_status=ReferenceFulltextStatus.PREPROCESSING.value),
                )
                try:
                    task_id = await task_service.submit_task(
                        user_id=user_id,
                        task_type="reference_preprocess",
                        payload={
                            "workspace_id": workspace_id,
                            "source_id": source.id,
                            "source_asset_id": str(source_asset["id"]),
                            "workspace_asset_id": workspace_asset.id,
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
                        source.id,
                        source_asset["id"],
                        exc_info=True,
                    )
                    await client.update_source(
                        workspace_id=workspace_id,
                        source_id=source.id,
                        command=SourceUpdatePayload(fulltext_status=ReferenceFulltextStatus.UPLOADED.value),
                    )
                    source_asset = await client.update_source_asset(
                        workspace_id=workspace_id,
                        source_asset_id=str(source_asset["id"]),
                        command=SourceAssetUpdatePayload(
                            preprocess_status=ReferencePreprocessStatus.FAILED.value,
                            metadata_json={"preprocess_error": str(exc)},
                        ),
                    ) or source_asset
                    preprocess = {
                        "status": "failed",
                        "error": str(exc),
                        "message": "Reference Library 后台解析任务提交失败，PDF 已保存，可稍后重新解析。",
                    }
                else:
                    source_asset = await client.update_source_asset(
                        workspace_id=workspace_id,
                        source_asset_id=str(source_asset["id"]),
                        command=SourceAssetUpdatePayload(
                            preprocess_status=ReferencePreprocessStatus.PENDING.value,
                            metadata_json={"preprocess_task_id": str(task_id)},
                        ),
                    ) or source_asset
                    preprocess = {
                        "status": "pending",
                        "task_id": str(task_id),
                        "message": "文件较大，已进入 Reference Library 后台解析队列；解析完成前不要引用全文内容。",
                    }
            else:
                preprocess = await SourcePreprocessService(client).process_asset(
                    workspace_id=workspace_id,
                    source_asset_id=str(source_asset["id"]),
                    source_id=source.id,
                    workspace_asset_id=workspace_asset.id,
                    filename=target.name,
                    content_type=content_type,
                    source_path=target,
                    output_dir=target.parent / "_preprocessed" / target.stem,
                    output_virtual_root=f"{REFERENCE_UPLOAD_BUCKET}/_preprocessed/{target.stem}",
                    commit=True,
                )
                source_asset = await client.get_source_asset(
                    workspace_id=workspace_id,
                    source_asset_id=str(source_asset["id"]),
                ) or source_asset

            source = await client.get_source_for_workspace(workspace_id=workspace_id, source_id=source.id) or source

        return {
            "success": True,
            "reference": _serialize_source_reference(source),
            "asset": source_asset,
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


class SourcePreprocessService:
    """Preprocess uploaded full text into Source DataService assets and indexes."""

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def __init__(self, dataservice: AsyncDataServiceClient | None = None) -> None:
        self._dataservice = dataservice

    async def process_asset(
        self,
        *,
        workspace_id: str,
        source_id: str,
        source_asset_id: str,
        workspace_asset_id: str,
        filename: str,
        content_type: str | None,
        source_path: Path,
        output_dir: Path,
        output_virtual_root: str,
        task_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        async with _managed_dataservice_client(self._dataservice) as client:
            source = await client.get_source_for_workspace(workspace_id=workspace_id, source_id=source_id)
            source_asset = await client.get_source_asset(
                workspace_id=workspace_id,
                source_asset_id=source_asset_id,
            )
            if source is None or source_asset is None:
                raise ValueError("Source or source asset not found")
            await client.update_source(
                workspace_id=workspace_id,
                source_id=source_id,
                command=SourceUpdatePayload(fulltext_status=ReferenceFulltextStatus.PREPROCESSING.value),
            )
            await client.update_source_asset(
                workspace_id=workspace_id,
                source_asset_id=source_asset_id,
                command=SourceAssetUpdatePayload(
                    preprocess_status=ReferencePreprocessStatus.RUNNING.value,
                    metadata_json={"preprocess_task_id": task_id} if task_id else {},
                ),
            )
            result = await get_upload_preprocessor_service().preprocess_file(
                filename=filename,
                content_type=content_type,
                source_path=source_path,
                output_dir=output_dir,
                output_virtual_root=output_virtual_root,
            )
            return await self.apply_preprocess_result(
                workspace_id=workspace_id,
                source_id=source_id,
                source_asset_id=source_asset_id,
                workspace_asset_id=workspace_asset_id,
                result=result,
                task_id=task_id,
                dataservice=client,
            )

    async def apply_preprocess_result(
        self,
        *,
        workspace_id: str,
        source_id: str,
        source_asset_id: str,
        workspace_asset_id: str,
        result: UploadPreprocessResult,
        task_id: str | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> dict[str, Any]:
        metadata = result.to_metadata()
        if task_id:
            metadata["task_id"] = task_id
        status_metadata = {
            "manifest_path": result.manifest_path,
            "markdown_paths": list(result.markdown_paths),
            "preprocess_error": result.error,
            **({"preprocess_task_id": task_id} if task_id else {}),
        }
        async with _managed_dataservice_client(dataservice or self._dataservice) as client:
            if result.status == "succeeded":
                derivative_assets = await self._register_preprocessed_assets(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    parent_asset_id=workspace_asset_id,
                    source_asset_id=source_asset_id,
                    result=result,
                    dataservice=client,
                )
                manifest_asset_id = next(
                    (item["id"] for item in derivative_assets if item.get("asset_type") == "manifest"),
                    None,
                )
                await self._rebuild_source_index(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    source_asset_id=source_asset_id,
                    markdown_paths=result.markdown_paths,
                    dataservice=client,
                )
                await client.update_source(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    command=SourceUpdatePayload(
                        fulltext_status=ReferenceFulltextStatus.INDEXED.value,
                        evidence_level=ReferenceEvidenceLevel.INDEXED_FULLTEXT.value,
                    ),
                )
                await client.update_source_asset(
                    workspace_id=workspace_id,
                    source_asset_id=source_asset_id,
                    command=SourceAssetUpdatePayload(
                        preprocess_status=ReferencePreprocessStatus.SUCCEEDED.value,
                        manifest_asset_id=str(manifest_asset_id) if manifest_asset_id else None,
                        metadata_json=status_metadata,
                    ),
                )
            elif result.status in {"disabled", "skipped"}:
                await client.update_source(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    command=SourceUpdatePayload(
                        fulltext_status=ReferenceFulltextStatus.UPLOADED.value,
                        evidence_level=ReferenceEvidenceLevel.UPLOADED_FULLTEXT.value,
                    ),
                )
                await client.update_source_asset(
                    workspace_id=workspace_id,
                    source_asset_id=source_asset_id,
                    command=SourceAssetUpdatePayload(
                        preprocess_status=ReferencePreprocessStatus.SKIPPED.value,
                        metadata_json=status_metadata,
                    ),
                )
            else:
                await client.update_source(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    command=SourceUpdatePayload(fulltext_status=ReferenceFulltextStatus.FAILED.value),
                )
                await client.update_source_asset(
                    workspace_id=workspace_id,
                    source_asset_id=source_asset_id,
                    command=SourceAssetUpdatePayload(
                        preprocess_status=ReferencePreprocessStatus.FAILED.value,
                        metadata_json=status_metadata,
                    ),
                )
        return metadata

    async def _register_preprocessed_assets(
        self,
        *,
        workspace_id: str,
        source_id: str,
        parent_asset_id: str,
        source_asset_id: str,
        result: UploadPreprocessResult,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> list[dict[str, object]]:
        linked_assets: list[dict[str, object]] = []
        async with _managed_dataservice_client(dataservice or self._dataservice) as client:
            for markdown_path in result.markdown_paths:
                workspace_asset = await client.register_asset(
                    WorkspaceAssetCreatePayload(
                        workspace_id=workspace_id,
                        asset_kind="source_derivative",
                        name=Path(markdown_path).name,
                        title=Path(markdown_path).name,
                        mime_type="text/markdown",
                        storage_path=markdown_path,
                        parent_asset_id=parent_asset_id,
                        created_by="source_preprocess",
                        source_kind="source",
                        source_id=source_id,
                        metadata_json={
                            "virtual_path": markdown_path,
                            "public_url": workspace_upload_public_url(
                                workspace_id,
                                markdown_path,
                                root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                            ),
                            "source_asset_id": source_asset_id,
                        },
                    )
                )
                linked_assets.append(
                    await client.link_source_asset(
                        SourceAssetLinkPayload(
                            workspace_id=workspace_id,
                            source_id=source_id,
                            workspace_asset_id=workspace_asset.id,
                            asset_type="markdown",
                            preprocess_status=ReferencePreprocessStatus.SUCCEEDED.value,
                            metadata_json={
                                "virtual_path": markdown_path,
                                "public_url": workspace_upload_public_url(
                                    workspace_id,
                                    markdown_path,
                                    root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                                ),
                                "source_asset_id": source_asset_id,
                            },
                        )
                    )
                )
            if result.manifest_path:
                workspace_asset = await client.register_asset(
                    WorkspaceAssetCreatePayload(
                        workspace_id=workspace_id,
                        asset_kind="source_derivative",
                        name=Path(result.manifest_path).name,
                        title=Path(result.manifest_path).name,
                        mime_type="application/json",
                        storage_path=result.manifest_path,
                        parent_asset_id=parent_asset_id,
                        created_by="source_preprocess",
                        source_kind="source",
                        source_id=source_id,
                        metadata_json={
                            "virtual_path": result.manifest_path,
                            "public_url": workspace_upload_public_url(
                                workspace_id,
                                result.manifest_path,
                                root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                            ),
                            "source_asset_id": source_asset_id,
                        },
                    )
                )
                linked_assets.append(
                    await client.link_source_asset(
                        SourceAssetLinkPayload(
                            workspace_id=workspace_id,
                            source_id=source_id,
                            workspace_asset_id=workspace_asset.id,
                            asset_type="manifest",
                            preprocess_status=ReferencePreprocessStatus.SUCCEEDED.value,
                            metadata_json={
                                "virtual_path": result.manifest_path,
                                "public_url": workspace_upload_public_url(
                                    workspace_id,
                                    result.manifest_path,
                                    root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                                ),
                                "source_asset_id": source_asset_id,
                            },
                        )
                    )
                )
        return linked_assets

    async def _rebuild_source_index(
        self,
        *,
        workspace_id: str,
        source_id: str,
        source_asset_id: str,
        markdown_paths: Sequence[str],
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        outline_nodes: list[dict[str, object]] = []
        text_units: list[dict[str, object]] = []
        sort_order = 0
        async with _managed_dataservice_client(dataservice or self._dataservice) as client:
            source = await client.get_source_for_workspace(workspace_id=workspace_id, source_id=source_id)
        source_title = source.title if source is not None else ""
        for doc_index, markdown_path in enumerate(markdown_paths):
            try:
                disk_path = resolve_workspace_upload_stored_path(
                    workspace_id,
                    markdown_path,
                    root=DEFAULT_WORKSPACE_UPLOAD_ROOT,
                    allow_root_prefixed_relative=True,
                )
                text = disk_path.read_text(encoding="utf-8")
            except Exception:
                logger.warning(
                    "Failed to read source markdown path=%s source=%s",
                    markdown_path,
                    source_id,
                    exc_info=True,
                )
                continue
            for section in self._split_markdown_sections(text) or self._chunked_sections(text):
                content = str(section.get("content") or "").strip()
                if not content:
                    continue
                node_id = generate_uuid()
                title = str(section.get("title") or f"Section {sort_order + 1}").strip()
                section_path = str(sort_order + 1)
                outline_nodes.append(
                    {
                        "id": node_id,
                        "workspace_id": workspace_id,
                        "source_id": source_id,
                        "parent_id": None,
                        "section_path": section_path,
                        "title": title,
                        "level": int(section.get("level") or 1),
                        "sort_order": sort_order,
                        "page_start": doc_index + 1,
                        "page_end": doc_index + 1,
                        "char_start": safe_int(section.get("char_start")),
                        "char_end": safe_int(section.get("char_end")),
                        "summary": " ".join(content.split())[:360],
                        "keywords_json": [],
                    }
                )
                text_units.append(
                    {
                        "id": generate_uuid(),
                        "workspace_id": workspace_id,
                        "source_id": source_id,
                        "outline_node_id": node_id,
                        "source_asset_id": source_asset_id,
                        "unit_type": "section",
                        "unit_index": sort_order,
                        "content": content,
                        "search_text": f"{source_title}\n{title}\n{content}",
                        "token_count": len(content.split()),
                        "page_start": doc_index + 1,
                        "page_end": doc_index + 1,
                        "char_start": safe_int(section.get("char_start")),
                        "char_end": safe_int(section.get("char_end")),
                        "metadata_json": {
                            "section_path": section_path,
                            "doc_index": doc_index,
                            "markdown_path": markdown_path,
                        },
                    }
                )
                sort_order += 1
        async with _managed_dataservice_client(dataservice or self._dataservice) as client:
            await client.replace_source_index(
                SourceIndexReplacePayload(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    outline_nodes=outline_nodes,
                    text_units=text_units,
                )
            )

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
    def _chunked_sections(text: str, *, max_chars: int = 5000) -> list[dict[str, Any]]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        return [
            {
                "level": 1,
                "title": f"Full text {index + 1}",
                "content": normalized[start : start + max_chars],
                "char_start": start,
                "char_end": min(start + max_chars, len(normalized)),
            }
            for index, start in enumerate(range(0, len(normalized), max_chars))
        ]


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


class SourceBibliographyService:
    """Generate and synchronize BibTeX from workspace Source metadata."""

    def __init__(
        self,
        dataservice: AsyncDataServiceClient | None = None,
        *,
        db: AsyncSession | None = None,
    ) -> None:
        self._dataservice = dataservice
        self.db = db

    async def build_bibtex(
        self,
        *,
        workspace_id: str,
        scope: ReferenceBibtexScope | str = ReferenceBibtexScope.INCLUDED_AND_CORE,
    ) -> dict[str, Any]:
        scope_value = _coerce_enum_value(ReferenceBibtexScope, scope, "scope")
        references = await self._load_scope(workspace_id, scope_value)
        async with _managed_dataservice_client(self._dataservice) as client:
            bibliography = await client.build_source_bibliography(
                SourceBibliographyCreatePayload(
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
        async with _managed_dataservice_client(self._dataservice) as client:
            references = await client.list_sources(
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
        async with _managed_dataservice_client(self._dataservice) as client:
            workspace = await client.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        if self.db is None:
            raise ValueError("LaTeX bibliography sync requires a request database session until LaTeX is migrated.")

        project = await WorkspaceLatexProjectService(self.db).ensure_workspace_project(
            workspace_id=workspace_id,
            project_name=workspace.name,
        )
        project_service = LatexProjectService(self.db)
        await project_service.write_text_file(project, "refs.bib", bibtex["content"])
        await self._ensure_main_tex_bibliography(project_service, project)

        async with _managed_dataservice_client(self._dataservice) as client:
            await client.create_source_bibliography_snapshot(
                SourceBibliographySnapshotCreatePayload(
                    workspace_id=workspace_id,
                    prism_project_id=str(project.id),
                    scope=bibtex["scope"],
                    content=bibtex["content"],
                    reference_count=bibtex["reference_count"],
                    checksum=bibtex["checksum"],
                )
            )
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
        async with _managed_dataservice_client(self._dataservice) as client:
            if scope_value == ReferenceBibtexScope.CORE.value:
                return await client.list_sources(
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
                        await client.list_sources(
                            workspace_id=workspace_id,
                            library_status=library_status,
                            include_excluded=True,
                            limit=5000,
                        )
                    )
                return sorted(sources, key=lambda source: source.citation_key)
            elif scope_value == ReferenceBibtexScope.USED_ONLY.value:
                return await client.list_sources(
                    workspace_id=workspace_id,
                    library_status=ReferenceLibraryStatus.USED_IN_DRAFT.value,
                    include_excluded=True,
                    limit=5000,
                )
            sources = await client.list_sources(
                workspace_id=workspace_id,
                include_excluded=False,
                limit=5000,
            )
        return sorted(sources, key=lambda source: source.citation_key)

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

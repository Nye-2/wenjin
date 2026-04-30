"""Workspace Reference Library API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    ReferenceAsset,
    ReferenceBibtexScope,
    ReferenceLibraryStatus,
    ReferenceReadStatus,
    ReferenceSourceType,
    User,
)
from src.gateway.access_control import require_workspace_owner
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_task_service, get_workspace_service
from src.gateway.deps.core import get_db
from src.services.references import (
    ReferenceBibTeXService,
    ReferenceEvidenceService,
    ReferenceImportService,
    ReferenceIndexService,
    WorkspaceReferenceService,
    serialize_asset,
    serialize_reference,
)
from src.task.service import TaskService
from src.workspace_events import publish_workspace_event

router = APIRouter(prefix="/workspaces/{workspace_id}/references", tags=["references"])

_MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 64 * 1024


class ReferenceUpdateRequest(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    publication_type: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    citation_count: int | None = None
    library_status: ReferenceLibraryStatus | None = None
    read_status: ReferenceReadStatus | None = None
    tags: list[str] | None = None
    notes: str | None = None
    citation_key: str | None = None
    bibtex_entry_type: str | None = None
    bibtex_fields: dict[str, Any] | None = None


class ManualReferenceRequest(ReferenceUpdateRequest):
    title: str = Field(min_length=1)


class SemanticScholarImportRequest(BaseModel):
    query: str = Field(min_length=1)
    discipline: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class DeepSearchArtifactImportRequest(BaseModel):
    artifact_ids: list[str] = Field(default_factory=list)


class BibtexImportRequest(BaseModel):
    content: str = Field(min_length=1)


class SearchTextUnitsRequest(BaseModel):
    query: str = Field(min_length=1)
    reference_ids: list[str] | None = None
    limit: int = Field(default=12, ge=1, le=50)


class EvidencePackRequest(BaseModel):
    query: str | None = None
    reference_ids: list[str] | None = None
    max_units: int = Field(default=8, ge=1, le=30)


class BibtexScopeRequest(BaseModel):
    scope: ReferenceBibtexScope = ReferenceBibtexScope.INCLUDED_AND_CORE


async def _read_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {_MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _require_owner(
    *,
    workspace_id: str,
    current_user: User,
    workspace_service: Any,
) -> None:
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )


async def _publish_references_refresh(workspace_id: str) -> None:
    await publish_workspace_event(
        workspace_id,
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "references"]},
    )


@router.get("")
async def list_references(
    workspace_id: str,
    library_status: ReferenceLibraryStatus | None = None,
    source_type: ReferenceSourceType | None = None,
    query: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        return await WorkspaceReferenceService(db).list_references(
            workspace_id,
            library_status=library_status,
            source_type=source_type,
            query=query,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/count")
async def count_references(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return await WorkspaceReferenceService(db).count_references(workspace_id)


@router.get("/outline")
async def get_library_outline(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    outline = await ReferenceIndexService(db).get_library_outline(workspace_id)
    return {"items": outline, "count": len(outline)}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_reference_pdf(
    workspace_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    task_service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    content = await _read_upload(file)
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    try:
        result = await ReferenceImportService(db).import_uploaded_pdf(
            workspace_id=workspace_id,
            filename=file.filename or "reference.pdf",
            content_type=file.content_type,
            content=content,
            task_service=task_service,
            user_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _publish_references_refresh(workspace_id)
    return result


@router.post("/import/semantic-scholar")
async def import_semantic_scholar(
    workspace_id: str,
    request: SemanticScholarImportRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    result = await ReferenceImportService(db).import_semantic_scholar_query(
        workspace_id=workspace_id,
        query=request.query,
        discipline=request.discipline,
        limit=request.limit,
    )
    await _publish_references_refresh(workspace_id)
    return result


@router.post("/import/deep-search-artifact")
async def import_deep_search_artifact(
    workspace_id: str,
    request: DeepSearchArtifactImportRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    result = await ReferenceImportService(db).import_deep_search_artifact(
        workspace_id=workspace_id,
        artifact_ids=request.artifact_ids,
    )
    await _publish_references_refresh(workspace_id)
    return result


@router.post("/import/bibtex")
async def import_bibtex(
    workspace_id: str,
    request: BibtexImportRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    result = await ReferenceImportService(db).import_bibtex(
        workspace_id=workspace_id,
        content=request.content,
    )
    await _publish_references_refresh(workspace_id)
    return result


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def create_manual_reference(
    workspace_id: str,
    request: ManualReferenceRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        result = await ReferenceImportService(db).import_manual(
            workspace_id,
            request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _publish_references_refresh(workspace_id)
    return result


@router.post("/search-text-units")
async def search_text_units(
    workspace_id: str,
    request: SearchTextUnitsRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    items = await ReferenceIndexService(db).search_text_units(
        workspace_id=workspace_id,
        query=request.query,
        reference_ids=request.reference_ids,
        limit=request.limit,
    )
    return {"items": items, "count": len(items)}


@router.post("/evidence-pack")
async def build_evidence_pack(
    workspace_id: str,
    request: EvidencePackRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return await ReferenceEvidenceService(db).build_evidence_pack(
        workspace_id=workspace_id,
        query=request.query,
        reference_ids=request.reference_ids,
        max_units=request.max_units,
    )


@router.get("/bibtex")
async def get_bibtex(
    workspace_id: str,
    scope: ReferenceBibtexScope = ReferenceBibtexScope.INCLUDED_AND_CORE,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        return await ReferenceBibTeXService(db).build_bibtex(
            workspace_id=workspace_id,
            scope=scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/bibtex/validate")
async def validate_bibtex(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return await ReferenceBibTeXService(db).validate_bibtex(workspace_id=workspace_id)


@router.post("/bibtex/sync-prism")
async def sync_bibtex_to_prism(
    workspace_id: str,
    request: BibtexScopeRequest | None = None,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    scope = request.scope if request is not None else "included_and_core"
    try:
        result = await ReferenceBibTeXService(db).sync_prism(
            workspace_id=workspace_id,
            scope=scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _publish_references_refresh(workspace_id)
    return result


@router.get("/{reference_id}")
async def get_reference(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    service = WorkspaceReferenceService(db)
    reference = await service.get(workspace_id, reference_id)
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    assets_result = await db.execute(
        select_assets_for_reference(workspace_id=workspace_id, reference_id=reference_id)
    )
    return {
        "reference": serialize_reference(reference),
        "assets": [serialize_asset(asset) for asset in assets_result.scalars().all()],
    }


def select_assets_for_reference(*, workspace_id: str, reference_id: str):
    return select(ReferenceAsset).where(
        ReferenceAsset.workspace_id == workspace_id,
        ReferenceAsset.reference_id == reference_id,
    )


@router.patch("/{reference_id}")
async def update_reference(
    workspace_id: str,
    reference_id: str,
    request: ReferenceUpdateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        reference = await WorkspaceReferenceService(db).update_reference(
            workspace_id,
            reference_id,
            **request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    await _publish_references_refresh(workspace_id)
    return serialize_reference(reference)


@router.delete("/{reference_id}")
async def delete_reference(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    deleted = await WorkspaceReferenceService(db).soft_delete(workspace_id, reference_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    await _publish_references_refresh(workspace_id)
    return {"success": True}


@router.post("/{reference_id}/mark-included")
async def mark_included(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _mark_reference_status(
        workspace_id,
        reference_id,
        "included",
        current_user,
        workspace_service,
        db,
    )


@router.post("/{reference_id}/mark-core")
async def mark_core(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _mark_reference_status(
        workspace_id,
        reference_id,
        "core",
        current_user,
        workspace_service,
        db,
    )


@router.post("/{reference_id}/exclude")
async def exclude_reference(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _mark_reference_status(
        workspace_id,
        reference_id,
        "excluded",
        current_user,
        workspace_service,
        db,
    )


@router.post("/{reference_id}/mark-read")
async def mark_read(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    reference = await WorkspaceReferenceService(db).mark_status(
        workspace_id,
        reference_id,
        read_status="read",
    )
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    await _publish_references_refresh(workspace_id)
    return serialize_reference(reference)


async def _mark_reference_status(
    workspace_id: str,
    reference_id: str,
    library_status: str,
    current_user: User,
    workspace_service: Any,
    db: AsyncSession,
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    reference = await WorkspaceReferenceService(db).mark_status(
        workspace_id,
        reference_id,
        library_status=library_status,
    )
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    await _publish_references_refresh(workspace_id)
    return serialize_reference(reference)


@router.get("/{reference_id}/outline")
async def get_reference_outline(
    workspace_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    items = await ReferenceIndexService(db).get_reference_outline(workspace_id, reference_id)
    return {"items": items, "count": len(items)}


@router.get("/{reference_id}/outline/{node_id}/content")
async def read_outline_node(
    workspace_id: str,
    reference_id: str,
    node_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    result = await ReferenceIndexService(db).read_outline_node(
        workspace_id=workspace_id,
        reference_id=reference_id,
        node_id=node_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference outline node not found")
    return result


@router.get("/{reference_id}/pages")
async def read_reference_pages(
    workspace_id: str,
    reference_id: str,
    page_start: int = Query(ge=1),
    page_end: int = Query(ge=1),
    current_user: User = Depends(get_current_user),
    workspace_service: Any = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    if page_end < page_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_end must be >= page_start")
    items = await ReferenceIndexService(db).read_pages(
        workspace_id=workspace_id,
        reference_id=reference_id,
        page_start=page_start,
        page_end=page_end,
    )
    return {"items": items, "count": len(items)}

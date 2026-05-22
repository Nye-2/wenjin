"""Workspace Rooms Router — HTTP handlers for all 8 room types.

All endpoints live under /workspaces/{ws_id}/<room> and enforce workspace
ownership via ``_assert_workspace_owner``.

Rooms covered (spec §5.3):
  library | documents | decisions | memory | runs | tasks | settings | sandbox
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import (
    WorkspaceAssetCreatePayload,
    WorkspaceAssetPayload,
    WorkspaceAssetUpdatePayload,
)
from src.dataservice_client.contracts.rooms import (
    DecisionSetPayload,
    MemoryFactCreatePayload,
    WorkspaceTaskCreatePayload,
    WorkspaceTaskUpdatePayload,
)
from src.dataservice_client.contracts.sandbox import SandboxEnvironmentCreatePayload
from src.dataservice_client.contracts.source import SourceCreatePayload
from src.dataservice_client.contracts.workspace import WorkspaceSettingsUpdatePayload
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_dataservice_client, get_workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspace_rooms"])

_DOCUMENT_SOURCE_KIND = "documents_room"
_MIGRATED_DOCUMENT_SOURCE_KIND = "documents_v2"
_DOCUMENT_SOURCE_KINDS = {_DOCUMENT_SOURCE_KIND, _MIGRATED_DOCUMENT_SOURCE_KIND}


# ---------------------------------------------------------------------------
# Ownership helper
# ---------------------------------------------------------------------------


async def _assert_workspace_owner(
    ws_id: str,
    current_user: User,
    workspace_service: WorkspaceService,
) -> None:
    """Raise 404 if workspace doesn't belong to user."""
    workspace = await workspace_service.get(ws_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    if not await workspace_service.has_active_membership(
        workspace_id=ws_id,
        user_id=str(current_user.id),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

# ── Library ──────────────────────────────────────────────────────────────────


class LibraryItemCreateRequest(BaseModel):
    item_type: str
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    full_text_path: str | None = None
    metadata_json: dict[str, Any] = {}
    tags: list[str] = []
    cited_in_documents: list[str] = []
    added_by: str = "user"


# ── Documents ────────────────────────────────────────────────────────────────


class DocumentCreateRequest(BaseModel):
    name: str
    kind: str
    mime_type: str | None = None
    storage_path: str | None = None
    size_bytes: int | None = None
    metadata_json: dict[str, Any] = {}
    added_by: str = "user"


class DocumentUpdateRequest(BaseModel):
    """Update a document.  If parent_id is set a new version is committed."""

    parent_id: str | None = None
    name: str | None = None
    kind: str | None = None
    mime_type: str | None = None
    storage_path: str | None = None
    size_bytes: int | None = None
    metadata_json: dict[str, Any] | None = None
    added_by: str | None = None


# ── Decisions ────────────────────────────────────────────────────────────────


class DecisionCreateRequest(BaseModel):
    key: str
    value: str
    extracted_by: str = "user"
    confidence: float = 1.0


# ── Memory ───────────────────────────────────────────────────────────────────


class MemoryFactItem(BaseModel):
    category: str
    content: str
    confidence: float = 1.0


class MemoryBulkAddRequest(BaseModel):
    facts: list[MemoryFactItem]


# ── Tasks ────────────────────────────────────────────────────────────────────


class WorkspaceTaskCreateRequest(BaseModel):
    title: str
    description: str | None = None
    status: str = "pending"
    priority: int = 0
    related_execution_ids: list[str] = []
    created_by: str = "user"


class WorkspaceTaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    related_execution_ids: list[str] | None = None


# ── Settings ─────────────────────────────────────────────────────────────────


class WorkspaceSettingsUpdateRequest(BaseModel):
    default_model: str | None = None
    thinking_enabled: bool | None = None
    sandbox_provider: str | None = None
    auto_compact_threshold: float | None = None
    capability_overrides: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


# ── Sandbox ──────────────────────────────────────────────────────────────────


class SandboxExecRequest(BaseModel):
    command: str
    timeout_seconds: int = 30


# ---------------------------------------------------------------------------
# Helper: convert ORM row → dict
# ---------------------------------------------------------------------------


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Best-effort ORM row → plain dict serialisation."""
    if hasattr(row, "__dict__"):
        return {
            k: v
            for k, v in row.__dict__.items()
            if not k.startswith("_")
        }
    return dict(row)


def _execution_to_run_dict(row: Any) -> dict[str, Any]:
    """Project an execution record into the workspace Runs room contract."""
    result = getattr(row, "result", None) or {}
    task_report = result.get("task_report") if isinstance(result, dict) else None
    if not isinstance(task_report, dict):
        task_report = {}

    raw_usage = task_report.get("token_usage")
    token_usage = None
    if isinstance(raw_usage, dict):
        token_usage = {
            "input": int(raw_usage.get("input") or raw_usage.get("input_tokens") or 0),
            "output": int(raw_usage.get("output") or raw_usage.get("output_tokens") or 0),
        }

    raw_review_items = task_report.get("review_items")
    review_items = raw_review_items if isinstance(raw_review_items, list) else []
    review_items_count = sum(
        1
        for item in review_items
        if isinstance(item, dict)
        and (
            item.get("kind") == "prism_file_change"
            or item.get("target_domain") == "prism"
            or (
                isinstance(item.get("target"), dict)
                and item["target"].get("kind") == "prism_file_change"
            )
        )
    )
    raw_errors = task_report.get("errors")
    errors = raw_errors if isinstance(raw_errors, list) else []
    first_error = next((item for item in errors if isinstance(item, dict)), None)
    failure_message = (
        getattr(row, "last_error", None)
        or getattr(row, "error", None)
        or (first_error.get("error") if first_error else None)
    )
    status_value = getattr(row, "status", "running")
    failure_category = None
    if status_value in {"failed", "failed_partial"}:
        lower_error = str(failure_message or "").lower()
        if "queue" in lower_error or "celery" in lower_error or "dispatch" in lower_error:
            failure_category = "queue_failed"
        elif "writeback" in lower_error or "write back" in lower_error:
            failure_category = "writeback_failed"
        elif status_value == "failed_partial":
            failure_category = "node_failed"
        else:
            failure_category = "unknown"

    started_at = getattr(row, "started_at", None) or getattr(row, "created_at", None)
    completed_at = getattr(row, "completed_at", None)
    feature_id = getattr(row, "feature_id", None)

    return {
        "id": str(getattr(row, "id", "")),
        "workspace_id": getattr(row, "workspace_id", None),
        "thread_id": getattr(row, "thread_id", None),
        "capability_id": feature_id,
        "capability_name": (
            getattr(row, "display_name", None)
            or feature_id
            or getattr(row, "execution_type", None)
            or "Execution"
        ),
        "status": status_value,
        "started_at": started_at.isoformat() if hasattr(started_at, "isoformat") else str(started_at or ""),
        "completed_at": (
            completed_at.isoformat()
            if hasattr(completed_at, "isoformat")
            else (str(completed_at) if completed_at else None)
        ),
        "summary": (
            getattr(row, "result_summary", None)
            or task_report.get("narrative")
            or getattr(row, "message", None)
            or getattr(row, "error", None)
            or ""
        ),
        "token_usage": token_usage,
        "progress": getattr(row, "progress", None),
        "primary_surface": "prism" if review_items_count > 0 else "rooms",
        "review_items_count": review_items_count,
        "has_prism_changes": review_items_count > 0,
        "failure_category": failure_category,
        "failure_message": failure_message,
    }


def _library_source_command(workspace_id: str, data: dict[str, Any]) -> SourceCreatePayload:
    return SourceCreatePayload(
        workspace_id=workspace_id,
        source_kind=str(data.get("item_type") or data.get("source_kind") or "paper"),
        title=str(data["title"]),
        authors_json=list(data.get("authors") or data.get("authors_json") or []),
        year=data.get("year"),
        venue=data.get("venue"),
        publication_type=data.get("publication_type"),
        doi=data.get("doi"),
        url=data.get("url"),
        abstract=data.get("abstract"),
        ingest_kind="manual",
        ingest_label=data.get("added_by"),
        library_status=str(data.get("library_status") or "included"),
        citation_key=str(data.get("citation_key") or _source_citation_key(data)),
        bibtex_fields_json=dict(data.get("bibtex_fields_json") or data.get("metadata_json") or {}),
        tags_json=list(data.get("tags") or []),
        notes=data.get("notes"),
    )


def _source_citation_key(data: dict[str, Any]) -> str:
    raw = str(data.get("doi") or data.get("title") or "source").lower()
    key = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    year = data.get("year")
    if year:
        key = f"{key}_{year}"
    return (key or "source")[:240]


def _asset_to_document(asset: WorkspaceAssetPayload) -> dict[str, Any]:
    metadata = dict(asset.metadata_json or {})
    return {
        "id": asset.id,
        "workspace_id": asset.workspace_id,
        "name": asset.name,
        "kind": str(metadata.get("kind") or metadata.get("legacy_kind") or asset.asset_kind or "document"),
        "mime_type": asset.mime_type,
        "storage_path": asset.storage_path,
        "size_bytes": asset.size_bytes,
        "parent_id": asset.parent_asset_id or metadata.get("parent_id") or metadata.get("legacy_parent_id"),
        "version": int(metadata.get("version") or metadata.get("legacy_version") or 1),
        "metadata_json": metadata,
        "added_by": asset.created_by,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
        "deleted_at": asset.deleted_at,
    }


def _asset_sort_value(asset: WorkspaceAssetProjection) -> float:
    stamp = asset.created_at or asset.updated_at
    return stamp.timestamp() if hasattr(stamp, "timestamp") else 0.0


def _inline_storage_path(data: dict[str, Any]) -> str:
    name = str(data.get("name") or "document").lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-") or "document"
    return f"inline://documents/{slug}"


def _inline_size(metadata: dict[str, Any]) -> int | None:
    content = metadata.get("content")
    return len(content.encode("utf-8")) if isinstance(content, str) else None


async def _list_document_assets(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    room_assets = await dataservice.list_assets(
        workspace_id=workspace_id,
        source_kind=_DOCUMENT_SOURCE_KIND,
        include_deleted=False,
        limit=limit,
    )
    migrated_assets = await dataservice.list_assets(
        workspace_id=workspace_id,
        source_kind=_MIGRATED_DOCUMENT_SOURCE_KIND,
        include_deleted=False,
        limit=max(0, limit - len(room_assets)),
    )
    combined = sorted([*room_assets, *migrated_assets], key=_asset_sort_value, reverse=True)
    return [_asset_to_document(asset) for asset in combined[:limit]]


async def _get_document_asset(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    doc_id: str,
) -> dict[str, Any] | None:
    asset = await dataservice.get_asset(doc_id)
    if asset is None or asset.workspace_id != workspace_id or asset.deleted_at is not None:
        return None
    if asset.source_kind not in _DOCUMENT_SOURCE_KINDS:
        return None
    return _asset_to_document(asset)


async def _create_document_asset(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    if parent_id := data.get("parent_id"):
        version_data = dict(data)
        version_data.pop("parent_id", None)
        return await _commit_document_asset_version(
            dataservice,
            workspace_id=workspace_id,
            parent_id=str(parent_id),
            data=version_data,
        )

    metadata = dict(data.get("metadata_json") or {})
    kind = str(data.get("kind") or "document")
    metadata.setdefault("kind", kind)
    metadata.setdefault("version", 1)
    asset = await dataservice.register_asset(
        WorkspaceAssetCreatePayload(
            workspace_id=workspace_id,
            asset_kind=kind,
            name=str(data["name"]),
            title=str(data.get("name") or ""),
            mime_type=data.get("mime_type") or "text/markdown",
            storage_backend="local",
            storage_path=data.get("storage_path") or _inline_storage_path(data),
            size_bytes=data.get("size_bytes") or _inline_size(metadata),
            created_by=str(data.get("added_by") or "user"),
            source_kind=_DOCUMENT_SOURCE_KIND,
            source_id=None,
            metadata_json=metadata,
        )
    )
    return _asset_to_document(asset)


async def _commit_document_asset_version(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    parent_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    parent = await _get_document_asset(dataservice, workspace_id=workspace_id, doc_id=parent_id)
    if parent is None:
        raise ValueError(f"Parent document {parent_id} not found")
    metadata = dict(data.get("metadata_json") or {})
    version = int(parent.get("version") or 1) + 1
    metadata.setdefault("kind", data.get("kind") or parent.get("kind"))
    metadata["version"] = version
    metadata["parent_id"] = parent_id
    asset = await dataservice.register_asset(
        WorkspaceAssetCreatePayload(
            workspace_id=workspace_id,
            asset_kind=str(metadata["kind"]),
            name=str(data.get("name") or parent["name"]),
            title=str(data.get("name") or parent["name"]),
            mime_type=data.get("mime_type") or parent.get("mime_type"),
            storage_backend="local",
            storage_path=data.get("storage_path") or _inline_storage_path(data),
            size_bytes=data.get("size_bytes") or _inline_size(metadata),
            parent_asset_id=parent_id,
            created_by=str(data.get("added_by") or parent.get("added_by") or "user"),
            source_kind=_DOCUMENT_SOURCE_KIND,
            source_id=parent_id,
            metadata_json=metadata,
        )
    )
    return _asset_to_document(asset)


async def _update_document_asset(
    dataservice: AsyncDataServiceClient,
    *,
    workspace_id: str,
    doc_id: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    current = await _get_document_asset(dataservice, workspace_id=workspace_id, doc_id=doc_id)
    if current is None:
        return None
    metadata = dict(current.get("metadata_json") or {})
    if data.get("kind") is not None:
        metadata["kind"] = data["kind"]
    if data.get("metadata_json") is not None:
        metadata.update(dict(data["metadata_json"] or {}))
    asset = await dataservice.update_asset(
        doc_id,
        WorkspaceAssetUpdatePayload(
            name=data.get("name"),
            title=data.get("name"),
            mime_type=data.get("mime_type"),
            metadata_json=metadata,
        ),
    )
    return _asset_to_document(asset) if asset is not None else None


# ===========================================================================
# LIBRARY endpoints
# ===========================================================================


@router.get("/{ws_id}/library")
async def list_library_items(
    ws_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    items = await dataservice.list_sources(
        workspace_id=ws_id,
        library_status="included",
        include_deleted=False,
        limit=limit,
    )
    return {"items": [_row_to_dict(i) for i in items], "count": len(items)}


@router.post("/{ws_id}/library", status_code=status.HTTP_201_CREATED)
async def create_library_item(
    ws_id: str,
    body: LibraryItemCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    item = await dataservice.create_source(_library_source_command(ws_id, body.model_dump()))
    return _row_to_dict(item)


@router.get("/{ws_id}/library/{item_id}")
async def get_library_item(
    ws_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    item = await dataservice.get_source(item_id)
    if item is None or item.workspace_id != ws_id or item.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Library item not found",
        )
    return _row_to_dict(item)


@router.delete("/{ws_id}/library/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_item(
    ws_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await dataservice.delete_source(
        workspace_id=ws_id,
        source_id=item_id,
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")


# ===========================================================================
# DOCUMENTS endpoints
# ===========================================================================


@router.get("/{ws_id}/documents")
async def list_documents(
    ws_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    docs = await _list_document_assets(dataservice, workspace_id=ws_id, limit=limit)
    return {"items": [_row_to_dict(d) for d in docs], "count": len(docs)}


@router.post("/{ws_id}/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    ws_id: str,
    body: DocumentCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    doc = await _create_document_asset(
        dataservice,
        workspace_id=ws_id,
        data=body.model_dump(),
    )
    return _row_to_dict(doc)


@router.get("/{ws_id}/documents/{doc_id}")
async def get_document(
    ws_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    doc = await _get_document_asset(dataservice, workspace_id=ws_id, doc_id=doc_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return _row_to_dict(doc)


@router.put("/{ws_id}/documents/{doc_id}")
async def update_document(
    ws_id: str,
    doc_id: str,
    body: DocumentUpdateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    """Update a document.  When ``parent_id`` is provided a new version is
    committed (commit_version) instead of an in-place update."""
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    data = body.model_dump(exclude_none=True)

    if "parent_id" in data:
        parent_id = data.pop("parent_id")
        try:
            doc = await _commit_document_asset_version(
                dataservice,
                workspace_id=ws_id,
                parent_id=parent_id,
                data=data,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    else:
        doc = await _update_document_asset(
            dataservice,
            workspace_id=ws_id,
            doc_id=doc_id,
            data=data,
        )
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return _row_to_dict(doc)


@router.delete("/{ws_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    ws_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    current = await _get_document_asset(dataservice, workspace_id=ws_id, doc_id=doc_id)
    found = current is not None and await dataservice.delete_asset(doc_id) is not None
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")


# ===========================================================================
# DECISIONS endpoints
# ===========================================================================


@router.get("/{ws_id}/decisions")
async def list_decisions(
    ws_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    active = await dataservice.list_room_decisions(ws_id)
    return {"active": active}


@router.post("/{ws_id}/decisions", status_code=status.HTTP_201_CREATED)
async def set_decision(
    ws_id: str,
    body: DecisionCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    decision = await dataservice.set_room_decision(
        DecisionSetPayload(
            workspace_id=ws_id,
            key=body.key,
            value=body.value,
            extracted_by=body.extracted_by,
            confidence=body.confidence,
        )
    )
    return _row_to_dict(decision)


@router.delete("/{ws_id}/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_decision(
    ws_id: str,
    decision_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await dataservice.delete_room_decision(decision_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")


# ===========================================================================
# MEMORY endpoints
# ===========================================================================


@router.get("/{ws_id}/memory")
async def list_memory(
    ws_id: str,
    k: int = Query(15, ge=1, le=200),
    category: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    facts = await dataservice.list_room_memory_facts(
        workspace_id=ws_id,
        limit=k,
        category=category,
    )
    return {"items": [_row_to_dict(f) for f in facts], "count": len(facts)}


@router.post("/{ws_id}/memory", status_code=status.HTTP_201_CREATED)
async def add_memory_facts(
    ws_id: str,
    body: MemoryBulkAddRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    commands = [
        MemoryFactCreatePayload(
            workspace_id=ws_id,
            category=f.category,
            content=f.content,
            confidence=f.confidence,
        )
        for f in body.facts
    ]
    rows = await dataservice.add_room_memory_facts(commands)
    return {"items": [_row_to_dict(r) for r in rows], "count": len(rows)}


@router.delete("/{ws_id}/memory/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_fact(
    ws_id: str,
    fact_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await dataservice.delete_room_memory_fact(workspace_id=ws_id, fact_id=fact_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")


# ===========================================================================
# RUNS (read-only history) endpoints
# ===========================================================================


@router.get("/{ws_id}/runs")
async def list_runs(
    ws_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    runs = await dataservice.list_executions(workspace_id=ws_id, limit=limit)
    return {"items": [_execution_to_run_dict(r) for r in runs], "count": len(runs)}


@router.get("/{ws_id}/runs/{run_id}")
async def get_run(
    ws_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    run = await dataservice.get_execution(run_id)
    if run is None or run.workspace_id != ws_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _execution_to_run_dict(run)


# ===========================================================================
# TASKS endpoints
# ===========================================================================


@router.get("/{ws_id}/tasks")
async def list_workspace_tasks(
    ws_id: str,
    task_status: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    tasks = await dataservice.list_room_tasks(workspace_id=ws_id, status=task_status)
    return {"items": [_row_to_dict(t) for t in tasks], "count": len(tasks)}


@router.post("/{ws_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_workspace_task(
    ws_id: str,
    body: WorkspaceTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    task = await dataservice.create_room_task(
        WorkspaceTaskCreatePayload(workspace_id=ws_id, **body.model_dump())
    )
    return _row_to_dict(task)


@router.put("/{ws_id}/tasks/{task_id}")
async def update_workspace_task(
    ws_id: str,
    task_id: str,
    body: WorkspaceTaskUpdateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    data = body.model_dump(exclude_none=True)
    task = await dataservice.update_room_task(
        workspace_id=ws_id,
        task_id=task_id,
        command=WorkspaceTaskUpdatePayload(**data),
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _row_to_dict(task)


@router.delete("/{ws_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_task(
    ws_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await dataservice.delete_room_task(workspace_id=ws_id, task_id=task_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


# ===========================================================================
# SETTINGS endpoints
# ===========================================================================


@router.get("/{ws_id}/settings")
async def get_workspace_settings(
    ws_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    settings = await dataservice.get_workspace_settings(ws_id)
    return _row_to_dict(settings)


@router.put("/{ws_id}/settings")
async def update_workspace_settings(
    ws_id: str,
    body: WorkspaceSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    data = body.model_dump(exclude_none=True)
    updated = await dataservice.update_workspace_settings(
        ws_id,
        WorkspaceSettingsUpdatePayload(**data),
    )
    return _row_to_dict(updated)


# ===========================================================================
# SANDBOX exec endpoint
# ===========================================================================


@router.post("/{ws_id}/sandbox/exec", status_code=status.HTTP_200_OK)
async def sandbox_exec(
    ws_id: str,
    body: SandboxExecRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    """Execute a command in the workspace sandbox.

    V1: sandbox_dev_mode is always allowed (logs a warning per spec).
    """
    await _assert_workspace_owner(ws_id, current_user, workspace_service)

    sandbox = await dataservice.get_or_create_sandbox_environment(
        ws_id,
        SandboxEnvironmentCreatePayload(workspace_id=ws_id, provider="local"),
    )
    return {
        "sandbox_id": sandbox.sandbox_id,
        "provider": sandbox.provider,
        "command": body.command,
        "status": "queued",
        "note": "V1 stub — real execution wired in Phase 2",
    }

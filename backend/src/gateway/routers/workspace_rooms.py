"""Workspace Rooms Router — HTTP handlers for user-facing room types.

All endpoints live under /workspaces/{ws_id}/<room> and enforce workspace
ownership via ``_assert_workspace_owner``.

Rooms covered:
  library | decisions | tasks | settings
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, field_validator

from src.academic.services.workspace_service import WorkspaceService
from src.contracts.reasoning import ReasoningEffort
from src.contracts.review_policy import ReviewMode, normalize_review_mode
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.rooms import (
    DecisionSetPayload,
    WorkspaceTaskCreatePayload,
    WorkspaceTaskUpdatePayload,
)
from src.dataservice_client.contracts.source import SourceCreatePayload
from src.dataservice_client.contracts.workspace import WorkspaceSettingsUpdatePayload
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps import get_dataservice_client, get_workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspace_rooms"])


# ---------------------------------------------------------------------------
# Ownership helper
# ---------------------------------------------------------------------------


async def _assert_workspace_owner(
    ws_id: str,
    current_user: AccountAuthSubject,
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


# ── Decisions ────────────────────────────────────────────────────────────────


class DecisionCreateRequest(BaseModel):
    key: str
    value: str
    extracted_by: str = "user"
    confidence: float = 1.0


# ── Tasks ────────────────────────────────────────────────────────────────────


class WorkspaceTaskCreateRequest(BaseModel):
    title: str
    description: str | None = None
    status: str = "pending"
    priority: int = 0
    related_mission_ids: list[str] = []
    created_by: str = "user"


class WorkspaceTaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    related_mission_ids: list[str] | None = None


# ── Settings ─────────────────────────────────────────────────────────────────


class WorkspaceSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    auto_compact_threshold: float | None = None
    review_mode: ReviewMode | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("review_mode", mode="before")
    @classmethod
    def _normalize_review_mode(cls, value: Any) -> ReviewMode | None:
        if value is None:
            return None
        return normalize_review_mode(value)


# ---------------------------------------------------------------------------
# Helper: convert ORM row → dict
# ---------------------------------------------------------------------------


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Best-effort ORM row → plain dict serialisation."""
    if hasattr(row, "__dict__"):
        return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
    return dict(row)


def _library_item_to_dict(row: Any) -> dict[str, Any]:
    """Project a DataService SourcePayload into the workspace Library contract."""
    data = _row_to_dict(row)
    authors = data.get("authors")
    if not isinstance(authors, list):
        authors = data.get("authors_json") if isinstance(data.get("authors_json"), list) else []
    added_by = data.get("added_by") or data.get("source_label") or data.get("ingest_label") or data.get("source_type") or data.get("ingest_kind") or "library"
    return {
        **data,
        "authors": authors,
        "added_by": added_by,
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


# ===========================================================================
# LIBRARY endpoints
# ===========================================================================


@router.get("/{ws_id}/library")
async def list_library_items(
    ws_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    return {"items": [_library_item_to_dict(i) for i in items], "count": len(items)}


@router.post("/{ws_id}/library", status_code=status.HTTP_201_CREATED)
async def create_library_item(
    ws_id: str,
    body: LibraryItemCreateRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    item = await dataservice.create_source(_library_source_command(ws_id, body.model_dump()))
    return _library_item_to_dict(item)


@router.get("/{ws_id}/library/{item_id}")
async def get_library_item(
    ws_id: str,
    item_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    return _library_item_to_dict(item)


@router.delete("/{ws_id}/library/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_item(
    ws_id: str,
    item_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
# DECISIONS endpoints
# ===========================================================================


@router.get("/{ws_id}/decisions")
async def list_decisions(
    ws_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    decisions = await dataservice.list_room_decisions(ws_id)
    return {"items": [_row_to_dict(item) for item in decisions], "count": len(decisions)}


@router.post("/{ws_id}/decisions", status_code=status.HTTP_201_CREATED)
async def set_decision(
    ws_id: str,
    body: DecisionCreateRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await dataservice.delete_room_decision(decision_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")


# ===========================================================================
# TASKS endpoints
# ===========================================================================


@router.get("/{ws_id}/tasks")
async def list_workspace_tasks(
    ws_id: str,
    task_status: str | None = Query(None, alias="status"),
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    task = await dataservice.create_room_task(WorkspaceTaskCreatePayload(workspace_id=ws_id, **body.model_dump()))
    return _row_to_dict(task)


@router.put("/{ws_id}/tasks/{task_id}")
async def update_workspace_task(
    ws_id: str,
    task_id: str,
    body: WorkspaceTaskUpdateRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
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

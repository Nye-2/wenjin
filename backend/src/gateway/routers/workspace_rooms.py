"""Workspace Rooms Router — HTTP handlers for all 8 room types.

All endpoints live under /workspaces/{ws_id}/<room> and enforce workspace
ownership via ``_assert_workspace_owner``.

Rooms covered (spec §5.3):
  library | documents | decisions | memory | runs | tasks | settings | sandbox
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_db, get_workspace_service

if TYPE_CHECKING:
    from src.services.rooms.decisions_service import DecisionsService
    from src.services.rooms.documents_service import DocumentsService
    from src.services.rooms.library_service import LibraryService
    from src.services.rooms.memory_service import MemoryService
    from src.services.rooms.run_history_service import RunHistoryService
    from src.services.rooms.settings_service import WorkspaceSettingsService
    from src.services.rooms.workspace_tasks_service import WorkspaceTasksService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspace_rooms"])


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
# Service factories (thin wrappers to keep endpoint signatures clean)
# ---------------------------------------------------------------------------


def _library_service(db: AsyncSession) -> LibraryService:
    from src.services.rooms.library_service import LibraryService

    return LibraryService(db)


def _documents_service(db: AsyncSession) -> DocumentsService:
    from src.services.rooms.documents_service import DocumentsService

    return DocumentsService(db)


def _decisions_service(db: AsyncSession) -> DecisionsService:
    from src.services.rooms.decisions_service import DecisionsService

    return DecisionsService(db)


def _memory_service(db: AsyncSession) -> MemoryService:
    from src.services.rooms.memory_service import MemoryService

    return MemoryService(db)


def _run_history_service(db: AsyncSession) -> RunHistoryService:
    from src.services.rooms.run_history_service import RunHistoryService

    return RunHistoryService(db)


def _workspace_tasks_service(db: AsyncSession) -> WorkspaceTasksService:
    from src.services.rooms.workspace_tasks_service import WorkspaceTasksService

    return WorkspaceTasksService(db)


def _settings_service(db: AsyncSession) -> WorkspaceSettingsService:
    from src.services.rooms.settings_service import WorkspaceSettingsService

    return WorkspaceSettingsService(db)


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


# ===========================================================================
# LIBRARY endpoints
# ===========================================================================


@router.get("/{ws_id}/library")
async def list_library_items(
    ws_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    items = await _library_service(db).list(ws_id, limit=limit)
    return {"items": [_row_to_dict(i) for i in items], "count": len(items)}


@router.post("/{ws_id}/library", status_code=status.HTTP_201_CREATED)
async def create_library_item(
    ws_id: str,
    body: LibraryItemCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    item = await _library_service(db).add(ws_id, body.model_dump())
    return _row_to_dict(item)


@router.get("/{ws_id}/library/{item_id}")
async def get_library_item(
    ws_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    item = await _library_service(db).get(ws_id, item_id)
    if item is None:
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
    db: AsyncSession = Depends(get_db),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await _library_service(db).delete(ws_id, item_id)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    docs = await _documents_service(db).list(ws_id, limit=limit)
    return {"items": [_row_to_dict(d) for d in docs], "count": len(docs)}


@router.post("/{ws_id}/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    ws_id: str,
    body: DocumentCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    doc = await _documents_service(db).add(ws_id, body.model_dump())
    return _row_to_dict(doc)


@router.get("/{ws_id}/documents/{doc_id}")
async def get_document(
    ws_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    doc = await _documents_service(db).get(ws_id, doc_id)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a document.  When ``parent_id`` is provided a new version is
    committed (commit_version) instead of an in-place update."""
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    svc = _documents_service(db)
    data = body.model_dump(exclude_none=True)

    if "parent_id" in data:
        parent_id = data.pop("parent_id")
        try:
            doc = await svc.commit_version(ws_id, parent_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    else:
        doc = await svc.update(ws_id, doc_id, data)
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return _row_to_dict(doc)


@router.delete("/{ws_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    ws_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await _documents_service(db).delete(ws_id, doc_id)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    active = await _decisions_service(db).get_active(ws_id)
    return {"active": active}


@router.post("/{ws_id}/decisions", status_code=status.HTTP_201_CREATED)
async def set_decision(
    ws_id: str,
    body: DecisionCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    decision = await _decisions_service(db).set(
        workspace_id=ws_id,
        key=body.key,
        value=body.value,
        extracted_by=body.extracted_by,
        confidence=body.confidence,
    )
    return _row_to_dict(decision)


@router.delete("/{ws_id}/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_decision(
    ws_id: str,
    decision_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await _decisions_service(db).delete(decision_id)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    facts = await _memory_service(db).top(ws_id, k=k, category=category)
    return {"items": [_row_to_dict(f) for f in facts], "count": len(facts)}


@router.post("/{ws_id}/memory", status_code=status.HTTP_201_CREATED)
async def add_memory_facts(
    ws_id: str,
    body: MemoryBulkAddRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from src.services.rooms.memory_service import FactCreate

    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    fact_creates = [
        FactCreate(category=f.category, content=f.content, confidence=f.confidence)
        for f in body.facts
    ]
    rows = await _memory_service(db).add_facts(ws_id, fact_creates)
    return {"items": [_row_to_dict(r) for r in rows], "count": len(rows)}


@router.delete("/{ws_id}/memory/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_fact(
    ws_id: str,
    fact_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await _memory_service(db).delete(ws_id, fact_id)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    runs = await _run_history_service(db).list(ws_id, limit=limit)
    return {"items": [_row_to_dict(r) for r in runs], "count": len(runs)}


@router.get("/{ws_id}/runs/{run_id}")
async def get_run(
    ws_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    run = await _run_history_service(db).get(ws_id, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _row_to_dict(run)


# ===========================================================================
# TASKS endpoints
# ===========================================================================


@router.get("/{ws_id}/tasks")
async def list_workspace_tasks(
    ws_id: str,
    task_status: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    tasks = await _workspace_tasks_service(db).list(ws_id, status=task_status)
    return {"items": [_row_to_dict(t) for t in tasks], "count": len(tasks)}


@router.post("/{ws_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_workspace_task(
    ws_id: str,
    body: WorkspaceTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    task = await _workspace_tasks_service(db).add(ws_id, body.model_dump())
    return _row_to_dict(task)


@router.put("/{ws_id}/tasks/{task_id}")
async def update_workspace_task(
    ws_id: str,
    task_id: str,
    body: WorkspaceTaskUpdateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    data = body.model_dump(exclude_none=True)
    task = await _workspace_tasks_service(db).update(ws_id, task_id, **data)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _row_to_dict(task)


@router.delete("/{ws_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_task(
    ws_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    found = await _workspace_tasks_service(db).delete(ws_id, task_id)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    settings = await _settings_service(db).get_or_create(ws_id)
    return _row_to_dict(settings)


@router.put("/{ws_id}/settings")
async def update_workspace_settings(
    ws_id: str,
    body: WorkspaceSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    data = body.model_dump(exclude_none=True)
    updated = await _settings_service(db).update(ws_id, **data)
    if updated is None:
        # Settings row didn't exist yet — create with defaults then apply
        await _settings_service(db).get_or_create(ws_id)
        updated = await _settings_service(db).update(ws_id, **data)
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute a command in the workspace sandbox.

    V1: sandbox_dev_mode is always allowed (logs a warning per spec).
    """
    logger.warning(
        "sandbox/exec invoked for workspace=%s user=%s — "
        "dev-mode sandbox is enabled; gate on Settings.sandbox_dev_mode in Phase 2",
        ws_id,
        str(current_user.id),
    )
    await _assert_workspace_owner(ws_id, current_user, workspace_service)

    from src.services.rooms.sandbox_service import SandboxService

    sandbox_svc = SandboxService(db)
    sandbox = await sandbox_svc.get_or_create(ws_id)

    # V1 stub: record the sandbox touch and return an ack.
    await sandbox_svc.touch(ws_id)
    return {
        "sandbox_id": sandbox.sandbox_id,
        "provider": sandbox.provider,
        "command": body.command,
        "status": "queued",
        "note": "V1 stub — real execution wired in Phase 2",
    }

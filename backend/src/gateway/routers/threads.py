"""Thread management and platform-style thread state/history endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.database import User
from src.gateway.access_control import (
    owner_check_session_from_service,
    require_workspace_owner_by_session,
)
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_thread_service
from src.gateway.deps.runtime import get_run_manager
from src.gateway.routers.thread_contracts import (
    ThreadCreate,
    ThreadListResponse,
    WorkspaceThreadEnsureRequest,
)
from src.gateway.routers.thread_contracts import (
    ThreadResponse as ThreadDetailResponse,
)
from src.gateway.routers.thread_serializers import thread_to_response, thread_to_summary
from src.models.router import InvalidRequestedModelError
from src.runtime.runs import RunManager, RunStatus
from src.runtime.serialization import serialize_channel_values
from src.services.thread_events import publish_thread_deleted, publish_thread_updated
from src.services.thread_service import ThreadService
from src.services.workspace_skill_labels import resolve_thread_skill_name

router = APIRouter(tags=["threads"])


class PlatformThreadResponse(BaseModel):
    thread_id: str = Field(description="Unique thread identifier")
    status: str = Field(default="idle", description="Thread status")
    created_at: str = Field(default="", description="ISO timestamp")
    updated_at: str = Field(default="", description="ISO timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    values: dict[str, Any] = Field(default_factory=dict, description="Current state channel values")
    interrupts: dict[str, Any] = Field(default_factory=dict, description="Pending interrupts")


class ThreadSearchRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata filter (exact match)")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    status: str | None = Field(default=None, description="Filter by thread status")


class ThreadStateResponse(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict, description="Current channel values")
    next: list[str] = Field(default_factory=list, description="Next tasks to execute")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    checkpoint: dict[str, Any] = Field(default_factory=dict, description="Synthetic checkpoint info")
    checkpoint_id: str | None = Field(default=None, description="Synthetic checkpoint id")
    parent_checkpoint_id: str | None = Field(default=None, description="Parent checkpoint id")
    created_at: str | None = Field(default=None, description="Checkpoint timestamp")
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="Active task details")


class HistoryEntry(BaseModel):
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    next: list[str] = Field(default_factory=list)


class ThreadHistoryRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100, description="Maximum entries")
    before: str | None = Field(default=None, description="Cursor for pagination")


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return ""
    return str(value)


async def _require_owned_workspace_if_provided(
    workspace_id: str | None,
    *,
    user_id: str,
    thread_service: ThreadService,
) -> None:
    if not workspace_id:
        return
    owner_session = owner_check_session_from_service(thread_service)
    if owner_session is None:
        return
    await require_workspace_owner_by_session(
        owner_session,
        workspace_id=workspace_id,
        user_id=user_id,
    )


async def _get_owned_thread_or_404(
    *,
    thread_id: str,
    user_id: str,
    thread_service: ThreadService,
    detail: str = "Thread not found",
) -> Any:
    thread = await thread_service.get_thread(thread_id, user_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=detail)
    return thread


def _thread_metadata(thread: Any) -> dict[str, Any]:
    return {
        "workspace_id": thread.workspace_id,
        "skill": thread.skill,
        "skill_name": resolve_thread_skill_name(thread),
        "model": thread.model,
    }


def _thread_status_from_runs(runs: list[Any]) -> str:
    for run in runs:
        if run.status in (RunStatus.pending, RunStatus.running):
            return "busy"
    if runs:
        latest = runs[0]
        if latest.status == RunStatus.interrupted:
            return "interrupted"
        if latest.status == RunStatus.error:
            return "error"
    return "idle"


def _active_run_tasks_from_runs(runs: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": run.run_id,
            "name": "run",
            "status": run.status.value,
        }
        for run in runs
        if run.status in (RunStatus.pending, RunStatus.running)
    ]


def _group_runs_by_thread(runs: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for run in runs:
        grouped.setdefault(run.thread_id, []).append(run)
    return grouped


def _state_values(thread: Any) -> dict[str, Any]:
    return serialize_channel_values(
        {
            "thread_id": thread.id,
            "workspace_id": thread.workspace_id,
            "title": thread.title,
            "model": thread.model,
            "skill": thread.skill,
            "skill_name": resolve_thread_skill_name(thread),
            "messages": thread.messages or [],
        }
    )


@router.post("/threads", response_model=ThreadDetailResponse)
async def create_thread(
    request: ThreadCreate,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadDetailResponse:
    actor_id = str(current_user.id)
    await _require_owned_workspace_if_provided(
        request.workspace_id,
        user_id=actor_id,
        thread_service=thread_service,
    )
    try:
        thread = await thread_service.create_thread(
            user_id=actor_id,
            workspace_id=request.workspace_id,
            title=request.title,
            model=request.model,
            skill=request.skill,
        )
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await publish_thread_updated(thread)
    return thread_to_response(thread, include_messages=False)


@router.post("/workspaces/{workspace_id}/thread", response_model=ThreadDetailResponse)
async def ensure_workspace_thread(
    workspace_id: str,
    request: WorkspaceThreadEnsureRequest = Body(
        default_factory=WorkspaceThreadEnsureRequest
    ),
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadDetailResponse:
    actor_id = str(current_user.id)
    await _require_owned_workspace_if_provided(
        workspace_id,
        user_id=actor_id,
        thread_service=thread_service,
    )
    try:
        thread = await thread_service.get_or_create_thread(
            user_id=actor_id,
            workspace_id=workspace_id,
            model=request.model,
            skill=request.skill,
            skill_explicit="skill" in request.model_fields_set,
        )
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return thread_to_response(thread)


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread_details(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadDetailResponse:
    thread = await _get_owned_thread_or_404(
        thread_id=thread_id,
        user_id=str(current_user.id),
        thread_service=thread_service,
    )
    return thread_to_response(thread)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> dict[str, Any]:
    thread = await _get_owned_thread_or_404(
        thread_id=thread_id,
        user_id=str(current_user.id),
        thread_service=thread_service,
    )
    deleted = await thread_service.delete_thread(thread_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    await publish_thread_deleted(thread.workspace_id, thread_id)
    return {"success": True}


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    workspace_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadListResponse:
    actor_id = str(current_user.id)
    await _require_owned_workspace_if_provided(
        workspace_id,
        user_id=actor_id,
        thread_service=thread_service,
    )
    threads = await thread_service.list_threads(
        user_id=actor_id,
        workspace_id=workspace_id,
        limit=limit,
    )
    return ThreadListResponse(
        threads=[thread_to_summary(thread) for thread in threads],
        count=len(threads),
    )


@router.post("/threads/search", response_model=list[PlatformThreadResponse])
async def search_threads(
    body: ThreadSearchRequest,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: RunManager = Depends(get_run_manager),
) -> list[PlatformThreadResponse]:
    user_id = str(current_user.id)
    workspace_id = body.metadata.get("workspace_id")
    candidate_limit = min(1000, max(body.limit + body.offset, body.limit))
    threads = await thread_service.list_threads(
        user_id=user_id,
        workspace_id=workspace_id if isinstance(workspace_id, str) else None,
        limit=candidate_limit,
    )

    runs = await run_manager.list_all()
    runs_by_thread = _group_runs_by_thread(runs)

    rows: list[PlatformThreadResponse] = []
    for thread in threads:
        metadata = _thread_metadata(thread)
        if body.metadata and not all(metadata.get(key) == value for key, value in body.metadata.items()):
            continue
        status = _thread_status_from_runs(runs_by_thread.get(str(thread.id), []))
        if body.status and status != body.status:
            continue
        rows.append(
            PlatformThreadResponse(
                thread_id=str(thread.id),
                status=status,
                created_at=_iso(thread.created_at),
                updated_at=_iso(thread.updated_at),
                metadata=metadata,
                values=serialize_channel_values({"title": thread.title}),
            )
        )

    return rows[body.offset : body.offset + body.limit]


@router.get("/threads/{thread_id}/state", response_model=ThreadStateResponse)
async def get_thread_state(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: RunManager = Depends(get_run_manager),
) -> ThreadStateResponse:
    thread = await _get_owned_thread_or_404(
        thread_id=thread_id,
        user_id=str(current_user.id),
        thread_service=thread_service,
        detail=f"Thread {thread_id} not found",
    )

    runs = await run_manager.list_by_thread(thread_id)
    status = _thread_status_from_runs(runs)
    tasks = _active_run_tasks_from_runs(runs)
    created_at = _iso(thread.updated_at)
    checkpoint_id = f"thread:{thread_id}:{int(thread.updated_at.timestamp() * 1000)}"
    return ThreadStateResponse(
        values=_state_values(thread),
        next=(["run"] if tasks else []),
        metadata={**_thread_metadata(thread), "status": status},
        checkpoint={"id": checkpoint_id, "ts": created_at},
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=None,
        created_at=created_at,
        tasks=tasks,
    )


@router.post("/threads/{thread_id}/history", response_model=list[HistoryEntry])
async def get_thread_history(
    thread_id: str,
    body: ThreadHistoryRequest,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: RunManager = Depends(get_run_manager),
) -> list[HistoryEntry]:
    thread = await _get_owned_thread_or_404(
        thread_id=thread_id,
        user_id=str(current_user.id),
        thread_service=thread_service,
        detail=f"Thread {thread_id} not found",
    )

    checkpoint_id = f"thread:{thread_id}:{int(thread.updated_at.timestamp() * 1000)}"
    if body.before and body.before != checkpoint_id:
        return []

    runs = await run_manager.list_by_thread(thread_id)
    status = _thread_status_from_runs(runs)
    tasks = _active_run_tasks_from_runs(runs)
    entry = HistoryEntry(
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=None,
        metadata={**_thread_metadata(thread), "status": status},
        values=_state_values(thread),
        created_at=_iso(thread.updated_at),
        next=(["run"] if tasks else []),
    )
    return [entry][: body.limit]

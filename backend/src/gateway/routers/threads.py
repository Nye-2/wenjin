"""Canonical conversation-thread management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.access_control import require_workspace_owner_by_dataservice
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps import get_dataservice_client, get_thread_service
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
from src.services.thread_events import publish_thread_deleted, publish_thread_updated
from src.services.thread_service import ThreadService

router = APIRouter(tags=["threads"])


async def _require_owned_workspace_if_provided(
    workspace_id: str | None,
    *,
    user_id: str,
) -> None:
    if not workspace_id:
        return
    await require_workspace_owner_by_dataservice(
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


async def _thread_messages(thread_service: ThreadService, thread: Any) -> list[dict[str, Any]]:
    return await thread_service.list_thread_messages(thread)


@router.post("/threads", response_model=ThreadDetailResponse)
async def create_thread(
    request: ThreadCreate,
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadDetailResponse:
    actor_id = str(current_user.id)
    await _require_owned_workspace_if_provided(
        request.workspace_id,
        user_id=actor_id,
    )
    try:
        thread = await thread_service.create_thread(
            user_id=actor_id,
            workspace_id=request.workspace_id,
            title=request.title,
            model=request.model,
        )
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await publish_thread_updated(thread)
    return thread_to_response(thread, include_messages=False)


@router.post("/workspaces/{workspace_id}/thread", response_model=ThreadDetailResponse)
async def ensure_workspace_thread(
    workspace_id: str,
    request: WorkspaceThreadEnsureRequest = Body(default_factory=WorkspaceThreadEnsureRequest),
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ThreadDetailResponse:
    actor_id = str(current_user.id)
    await _require_owned_workspace_if_provided(
        workspace_id,
        user_id=actor_id,
    )
    requested_model = request.model
    if requested_model is None or not requested_model.strip():
        settings = await dataservice.get_workspace_settings(workspace_id)
        default_model = getattr(settings, "default_model", None)
        if isinstance(default_model, str) and default_model.strip():
            requested_model = default_model.strip()
    try:
        thread = await thread_service.get_or_create_thread(
            user_id=actor_id,
            workspace_id=workspace_id,
            model=requested_model,
        )
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    messages = await _thread_messages(thread_service, thread)
    return thread_to_response(thread, messages=messages)


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread_details(
    thread_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadDetailResponse:
    thread = await _get_owned_thread_or_404(
        thread_id=thread_id,
        user_id=str(current_user.id),
        thread_service=thread_service,
    )
    messages = await _thread_messages(thread_service, thread)
    return thread_to_response(thread, messages=messages)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
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
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> ThreadListResponse:
    actor_id = str(current_user.id)
    await _require_owned_workspace_if_provided(
        workspace_id,
        user_id=actor_id,
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

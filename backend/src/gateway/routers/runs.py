"""Stateless run endpoints for direct run architecture usage."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import Response, StreamingResponse

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_thread_service, get_thread_turn_handler
from src.gateway.deps.runtime import get_run_manager, get_stream_bridge
from src.gateway.routers.run_contracts import (
    RunCreateRequest,
    RunResponse,
    RunWaitResponse,
    record_to_response,
)
from src.gateway.services.run_http import (
    await_run_task,
    cancel_run_with_http_response,
    get_run_or_404,
    maybe_cancel_then_wait,
    stream_run_response,
)
from src.gateway.services.run_launch import (
    launch_run_from_create_request,
    resolve_run_thread_id,
)
from src.gateway.services.run_views import build_wait_payload
from src.runtime.runs import RunManager, RunRecord
from src.runtime.stream_bridge import StreamBridge
from src.services.thread_service import ThreadService

router = APIRouter(prefix="/runs", tags=["runs"])


async def _require_owned_run(
    *,
    record: RunRecord,
    actor_id: str,
    thread_service: ThreadService,
) -> None:
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    owner_id = str(metadata.get("_owner_id") or "").strip()
    if owner_id:
        if owner_id != actor_id:
            raise HTTPException(
                status_code=404,
                detail=f"Run {record.run_id} not found",
            )
        return

    thread = await thread_service.get_thread(record.thread_id, actor_id)
    if thread is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run {record.run_id} not found",
        )


@router.post("/stream")
async def stream_run(
    body: RunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    handler: Any = Depends(get_thread_turn_handler),
    run_manager: RunManager = Depends(get_run_manager),
    bridge: StreamBridge = Depends(get_stream_bridge),
) -> StreamingResponse:
    record = await launch_run_from_create_request(
        body=body,
        actor_id=str(current_user.id),
        run_thread_id=resolve_run_thread_id(body.thread_id),
        request_thread_id=body.thread_id,
        handler=handler,
        run_manager=run_manager,
        bridge=bridge,
    )
    return stream_run_response(
        bridge=bridge,
        record=record,
        request=request,
        run_manager=run_manager,
    )


@router.post("/wait", response_model=RunWaitResponse)
async def wait_run(
    body: RunCreateRequest,
    current_user: User = Depends(get_current_user),
    handler: Any = Depends(get_thread_turn_handler),
    run_manager: RunManager = Depends(get_run_manager),
    bridge: StreamBridge = Depends(get_stream_bridge),
) -> RunWaitResponse:
    record = await launch_run_from_create_request(
        body=body,
        actor_id=str(current_user.id),
        run_thread_id=resolve_run_thread_id(body.thread_id),
        request_thread_id=body.thread_id,
        handler=handler,
        run_manager=run_manager,
        bridge=bridge,
    )

    await await_run_task(record, run_manager=run_manager, bridge=bridge)

    return RunWaitResponse(**(await build_wait_payload(
        record=record,
        actor_id=str(current_user.id),
        handler=handler,
        run_manager=run_manager,
    )))


@router.api_route("/{run_id}/stream", methods=["GET", "POST"], response_model=None)
async def stream_existing_run(
    run_id: str,
    request: Request,
    action: Literal["interrupt", "rollback"] | None = Query(default=None),
    wait: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: RunManager = Depends(get_run_manager),
    bridge: StreamBridge = Depends(get_stream_bridge),
) -> Response:
    """Join or cancel-then-join an existing run by run_id."""
    record = await get_run_or_404(run_manager, run_id)
    await _require_owned_run(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )

    cancel_response = await maybe_cancel_then_wait(
        run_manager=run_manager,
        record=record,
        action=action,
        wait=wait,
    )
    if cancel_response is not None:
        return cancel_response

    return stream_run_response(
        bridge=bridge,
        record=record,
        request=request,
        run_manager=run_manager,
    )


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: RunManager = Depends(get_run_manager),
) -> RunResponse:
    record = await get_run_or_404(run_manager, run_id)
    await _require_owned_run(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )
    return record_to_response(record)


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    wait: bool = Query(default=False),
    action: Literal["interrupt", "rollback"] = Query(default="interrupt"),
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: RunManager = Depends(get_run_manager),
) -> Response:
    record = await get_run_or_404(run_manager, run_id)
    await _require_owned_run(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )
    return await cancel_run_with_http_response(
        run_manager=run_manager,
        record=record,
        action=action,
        wait=wait,
    )


@router.delete("/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Spec §6.2 B3 — soft-delete a workspace_run row. User-initiated."""
    from src.database.session import get_db_session
    from src.services.workspace_run_service import WorkspaceRunService

    async with get_db_session() as db:
        svc = WorkspaceRunService(db)
        await svc.delete_run(run_id)
    return Response(status_code=204)


@router.post("/{run_id}/pause", status_code=204)
async def pause_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Spec §6.1 — pause the in-flight ParallelExecutor at the next phase boundary.

    Silently no-ops if no executor is registered for run_id (already finished or
    never started). Auth required so callers cannot probe arbitrary run_ids.
    """
    from src.subagents.manager import GlobalSubagentManager

    try:
        mgr = GlobalSubagentManager.get_instance()
    except RuntimeError:
        return Response(status_code=204)
    mgr.pause_run(run_id)
    return Response(status_code=204)


@router.post("/{run_id}/resume", status_code=204)
async def resume_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Spec §6.1 — resume a paused executor."""
    from src.subagents.manager import GlobalSubagentManager

    try:
        mgr = GlobalSubagentManager.get_instance()
    except RuntimeError:
        return Response(status_code=204)
    mgr.resume_run(run_id)
    return Response(status_code=204)

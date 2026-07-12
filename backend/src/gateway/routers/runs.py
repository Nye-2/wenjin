"""Stateless endpoints for short-lived ChatTurnRun transport."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps import get_thread_service, get_thread_turn_handler
from src.gateway.deps.runtime import get_chat_turn_run_manager, get_chat_turn_stream_bridge
from src.gateway.routers.chat_turn_contracts import (
    ChatTurnCreateRequest,
    ChatTurnResponse,
    ChatTurnWaitResponse,
    record_to_response,
)
from src.gateway.services.chat_turn_http import (
    await_chat_turn_task,
    cancel_chat_turn_with_http_response,
    get_chat_turn_or_404,
    maybe_cancel_chat_turn_then_wait,
    stream_chat_turn_response,
)
from src.gateway.services.chat_turn_launch import (
    launch_chat_turn_from_create_request,
    resolve_chat_turn_thread_id,
)
from src.gateway.services.chat_turn_views import build_chat_turn_wait_payload
from src.runtime.chat_turns import ChatTurnRunManager, ChatTurnRunRecord
from src.runtime.stream_bridge import StreamBridge
from src.services.thread_service import ThreadService

router = APIRouter(prefix="/runs", tags=["chat_turns"])


async def _require_owned_chat_turn(
    *,
    record: ChatTurnRunRecord,
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
async def stream_chat_turn(
    body: ChatTurnCreateRequest,
    request: Request,
    current_user: AccountAuthSubject = Depends(get_current_user),
    handler: Any = Depends(get_thread_turn_handler),
    run_manager: ChatTurnRunManager = Depends(get_chat_turn_run_manager),
    bridge: StreamBridge = Depends(get_chat_turn_stream_bridge),
) -> StreamingResponse:
    record = await launch_chat_turn_from_create_request(
        body=body,
        actor_id=str(current_user.id),
        run_thread_id=resolve_chat_turn_thread_id(body.thread_id),
        request_thread_id=body.thread_id,
        handler=handler,
        run_manager=run_manager,
        bridge=bridge,
    )
    return stream_chat_turn_response(
        bridge=bridge,
        record=record,
        request=request,
        run_manager=run_manager,
    )


@router.post("/wait", response_model=ChatTurnWaitResponse)
async def wait_chat_turn(
    body: ChatTurnCreateRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    handler: Any = Depends(get_thread_turn_handler),
    run_manager: ChatTurnRunManager = Depends(get_chat_turn_run_manager),
    bridge: StreamBridge = Depends(get_chat_turn_stream_bridge),
) -> ChatTurnWaitResponse:
    record = await launch_chat_turn_from_create_request(
        body=body,
        actor_id=str(current_user.id),
        run_thread_id=resolve_chat_turn_thread_id(body.thread_id),
        request_thread_id=body.thread_id,
        handler=handler,
        run_manager=run_manager,
        bridge=bridge,
    )

    await await_chat_turn_task(record, run_manager=run_manager, bridge=bridge)

    return ChatTurnWaitResponse(
        **(
            await build_chat_turn_wait_payload(
                record=record,
                actor_id=str(current_user.id),
                handler=handler,
                run_manager=run_manager,
            )
        )
    )


@router.api_route("/{run_id}/stream", methods=["GET", "POST"], response_model=None)
async def stream_existing_chat_turn(
    run_id: str,
    request: Request,
    action: Literal["interrupt", "rollback"] | None = Query(default=None),
    wait: bool = Query(default=False),
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: ChatTurnRunManager = Depends(get_chat_turn_run_manager),
    bridge: StreamBridge = Depends(get_chat_turn_stream_bridge),
) -> Response:
    """Join or cancel-then-join an existing run by run_id."""
    record = await get_chat_turn_or_404(run_manager, run_id)
    await _require_owned_chat_turn(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )

    cancel_response = await maybe_cancel_chat_turn_then_wait(
        run_manager=run_manager,
        record=record,
        action=action,
        wait=wait,
    )
    if cancel_response is not None:
        return cancel_response

    return stream_chat_turn_response(
        bridge=bridge,
        record=record,
        request=request,
        run_manager=run_manager,
    )


@router.get("/{run_id}", response_model=ChatTurnResponse)
async def get_chat_turn(
    run_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: ChatTurnRunManager = Depends(get_chat_turn_run_manager),
) -> ChatTurnResponse:
    record = await get_chat_turn_or_404(run_manager, run_id)
    await _require_owned_chat_turn(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )
    return record_to_response(record)


@router.post("/{run_id}/cancel")
async def cancel_chat_turn(
    run_id: str,
    wait: bool = Query(default=False),
    action: Literal["interrupt", "rollback"] = Query(default="interrupt"),
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: ChatTurnRunManager = Depends(get_chat_turn_run_manager),
) -> Response:
    record = await get_chat_turn_or_404(run_manager, run_id)
    await _require_owned_chat_turn(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )
    return await cancel_chat_turn_with_http_response(
        run_manager=run_manager,
        record=record,
        action=action,
        wait=wait,
    )


@router.delete("/{run_id}", status_code=204)
async def delete_chat_turn(
    run_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    run_manager: ChatTurnRunManager = Depends(get_chat_turn_run_manager),
) -> Response:
    """Delete a runtime run record from the canonical run manager."""
    record = await get_chat_turn_or_404(run_manager, run_id)
    await _require_owned_chat_turn(
        record=record,
        actor_id=str(current_user.id),
        thread_service=thread_service,
    )
    await run_manager.cleanup(run_id, delay=0, remove_persistent=True)
    return Response(status_code=204)

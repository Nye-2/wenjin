"""ChatTurnRun launch helpers."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from src.application.errors import ApplicationError
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.access_control import require_workspace_owner_by_dataservice
from src.gateway.error_mapping import to_http_exception
from src.gateway.routers.chat_turn_contracts import ChatTurnCreateRequest, to_turn_request
from src.gateway.services.chat_turn_lifecycle import launch_chat_turn
from src.runtime.chat_turns import ChatTurnRunManager, ChatTurnRunRecord
from src.runtime.stream_bridge import StreamBridge


def resolve_chat_turn_thread_id(thread_id: str | None) -> str:
    """Resolve thread id used for run-level concurrency control."""
    if thread_id and thread_id.strip():
        return thread_id.strip()
    return str(uuid.uuid4())


async def require_owned_workspace_if_provided(
    workspace_id: str | None,
    *,
    user_id: str,
    dataservice: AsyncDataServiceClient | None = None,
) -> None:
    """Enforce workspace ownership when a workspace-bound request is sent."""
    if not workspace_id:
        return
    await require_workspace_owner_by_dataservice(
        workspace_id=workspace_id,
        user_id=user_id,
        dataservice=dataservice,
    )


async def launch_chat_turn_from_create_request(
    *,
    body: ChatTurnCreateRequest,
    actor_id: str,
    run_thread_id: str,
    request_thread_id: str | None,
    handler: Any,
    run_manager: ChatTurnRunManager,
    bridge: StreamBridge,
) -> ChatTurnRunRecord:
    """Validate access and launch one thread run from a ChatTurnCreateRequest."""
    await require_owned_workspace_if_provided(
        body.workspace_id,
        user_id=actor_id,
    )
    turn_request = to_turn_request(body, forced_thread_id=request_thread_id)

    try:
        return await launch_chat_turn(
            handler=handler,
            run_manager=run_manager,
            bridge=bridge,
            actor_id=actor_id,
            run_thread_id=run_thread_id,
            turn_request=turn_request,
            assistant_id="thread",
            metadata=body.metadata,
            kwargs={
                "request": {
                    "workspace_id": body.workspace_id,
                    "thread_id": turn_request.thread_id,
                    "model": body.model,
                    "skill": body.skill,
                }
            },
            on_disconnect=body.on_disconnect,
            multitask_strategy=body.multitask_strategy,
        )
    except HTTPException:
        raise
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc

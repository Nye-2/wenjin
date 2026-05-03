"""Shared launch helpers for run lifecycle routers."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from src.application.errors import ApplicationError
from src.gateway.access_control import (
    owner_check_session_from_service,
    require_workspace_owner_by_session,
)
from src.gateway.error_mapping import to_http_exception
from src.gateway.routers.run_contracts import RunCreateRequest, to_turn_request
from src.gateway.services.run_lifecycle import launch_thread_run
from src.runtime.runs import RunManager, RunRecord
from src.runtime.stream_bridge import StreamBridge


def resolve_run_thread_id(thread_id: str | None) -> str:
    """Resolve thread id used for run-level concurrency control."""
    if thread_id and thread_id.strip():
        return thread_id.strip()
    return str(uuid.uuid4())


async def require_owned_workspace_if_provided(
    workspace_id: str | None,
    *,
    user_id: str,
    thread_service: Any,
) -> None:
    """Enforce workspace ownership when a workspace-bound request is sent."""
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


async def launch_run_from_create_request(
    *,
    body: RunCreateRequest,
    actor_id: str,
    run_thread_id: str,
    request_thread_id: str | None,
    handler: Any,
    run_manager: RunManager,
    bridge: StreamBridge,
) -> RunRecord:
    """Validate access and launch one thread run from a RunCreateRequest."""
    await require_owned_workspace_if_provided(
        body.workspace_id,
        user_id=actor_id,
        thread_service=getattr(handler, "thread_service", None),
    )
    turn_request = to_turn_request(body, forced_thread_id=request_thread_id)

    try:
        return await launch_thread_run(
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

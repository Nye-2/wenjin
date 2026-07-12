"""Celery task entrypoint for short-lived ChatTurnRun processing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from celery import shared_task

from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.results import ThreadTurnAttachment, ThreadTurnRequest
from src.config import redis_settings, settings
from src.runtime.chat_turns import ChatTurnRunManager, run_chat_turn
from src.runtime.stream_bridge import RedisStreamBridge


def _build_turn_request(payload: dict[str, Any]) -> ThreadTurnRequest:
    attachments_payload = payload.get("attachments")
    attachments: tuple[ThreadTurnAttachment, ...] = ()
    if isinstance(attachments_payload, list):
        built: list[ThreadTurnAttachment] = []
        for item in attachments_payload:
            if isinstance(item, dict):
                built.append(ThreadTurnAttachment(**item))
        attachments = tuple(built)

    return ThreadTurnRequest(
        message=str(payload.get("message") or ""),
        workspace_id=(
            str(payload.get("workspace_id")).strip()
            if payload.get("workspace_id") is not None
            else None
        ),
        thread_id=(
            str(payload.get("thread_id")).strip()
            if payload.get("thread_id") is not None
            else None
        ),
        model=(
            str(payload.get("model")).strip()
            if payload.get("model") is not None
            else None
        ),
        skill=(
            str(payload.get("skill")).strip()
            if payload.get("skill") is not None
            else None
        ),
        thinking_enabled=bool(payload.get("thinking_enabled", False)),
        reasoning_effort=(
            str(payload.get("reasoning_effort")).strip()
            if payload.get("reasoning_effort") is not None
            else None
        ),
        attachments=attachments,
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
        skill_explicit=bool(payload.get("skill_explicit", False)),
    )


async def _process_chat_turn_async(
    run_id: str,
    request_payload: dict[str, Any],
    actor_id: str,
) -> dict[str, Any]:
    from src.academic.cache.redis_client import redis_client
    from src.academic.services.artifact_service import ArtifactService
    from src.academic.services.workspace_service import WorkspaceService
    from src.dataservice_client.provider import dataservice_client
    from src.services import ThreadService
    from src.task.model_catalog_runtime import refresh_runtime_model_catalog

    if not redis_settings.enabled:
        raise RuntimeError("process_chat_turn requires REDIS_ENABLED=true")

    # Rebind Redis clients to the current loop before task execution.
    await redis_client.reset_client(close_current=False)
    await redis_client.reset_stream_client(close_current=False)

    # Always verify process-local Redis loop affinity for each run task.
    await redis_client.connect()
    await redis_client.connect_stream()

    run_manager = ChatTurnRunManager(
        redis_backend=redis_client.client,
        chat_turn_ttl_seconds=settings.runtime_run_ttl_seconds,
    )
    record = await run_manager.get_or_load(run_id)
    if record is None:
        return {"ok": False, "reason": "run_not_found", "run_id": run_id}

    turn_request = _build_turn_request(request_payload)
    bridge = RedisStreamBridge(
        redis_client.stream_client,
        queue_maxsize=512,
        stream_ttl_seconds=min(3600, settings.runtime_run_ttl_seconds),
        key_prefix="runtime:chat_turns:stream",
    )

    async with dataservice_client() as dataservice:
        await refresh_runtime_model_catalog(dataservice)
        handler = ThreadTurnHandler(
            thread_service=ThreadService(dataservice=dataservice),
            workspace_service=WorkspaceService(dataservice=dataservice),
            index_service=dataservice,
            artifact_service=ArtifactService(dataservice=dataservice),
            reference_service=dataservice,
        )
        await run_chat_turn(
            bridge,
            run_manager,
            record,
            handler=handler,
            request=turn_request,
            actor_id=actor_id,
        )

    latest = await run_manager.get_or_load(run_id) or record
    return {
        "ok": True,
        "run_id": run_id,
        "status": latest.status.value,
        "thread_id": latest.thread_id,
    }


def _process_chat_turn_entry(
    _self: Any,
    run_id: str,
    request_payload: dict[str, Any],
    actor_id: str,
) -> dict[str, Any]:
    from src.task.worker import run_worker_coroutine

    runner = cast(
        Callable[[Awaitable[dict[str, Any]]], dict[str, Any]],
        run_worker_coroutine,
    )
    return runner(_process_chat_turn_async(run_id, request_payload, actor_id))


process_chat_turn = shared_task(
    bind=True,
    name="src.task.tasks.process_chat_turn",
)(_process_chat_turn_entry)

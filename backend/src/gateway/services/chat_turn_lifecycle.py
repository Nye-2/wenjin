"""ChatTurnRun SSE lifecycle helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException, Request

from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.results import ThreadTurnRequest
from src.config.app_config import celery_settings, redis_settings, settings
from src.observability.prometheus import track_run_dispatch
from src.runtime.chat_turns import (
    ChatTurnConflictError,
    ChatTurnDisconnectMode,
    ChatTurnRunManager,
    ChatTurnRunRecord,
    ChatTurnRunStatus,
    ChatTurnTransportUnavailableError,
    UnsupportedChatTurnStrategyError,
)
from src.runtime.serialization import dumps_json, serialize
from src.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge

logger = logging.getLogger(__name__)


def _serialize_turn_request(request: ThreadTurnRequest) -> dict[str, Any]:
    attachments = []
    for item in request.attachments:
        attachments.append(
            {
                "name": item.name,
                "path": item.path,
                "kind": item.kind,
                "url": item.url,
                "content_type": item.content_type,
                "size_bytes": item.size_bytes,
                "reference_id": item.reference_id,
                "artifact_id": item.artifact_id,
                "metadata": item.metadata,
            }
        )
    return {
        "message": request.message,
        "workspace_id": request.workspace_id,
        "thread_id": request.thread_id,
        "model": request.model,
        "reasoning_effort": request.reasoning_effort,
        "attachments": attachments,
        "metadata": request.metadata,
        "turn_idempotency_key": request.turn_idempotency_key,
    }


def _request_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        serialize(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Encode one SSE frame with stable JSON serialization."""
    parts = [f"event: {event}", f"data: {dumps_json(data)}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


async def launch_chat_turn(
    *,
    handler: ThreadTurnHandler,
    run_manager: ChatTurnRunManager,
    bridge: StreamBridge,
    actor_id: str,
    run_thread_id: str,
    turn_request: ThreadTurnRequest,
    assistant_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    on_disconnect: str = "cancel",
    multitask_strategy: str = "reject",
) -> ChatTurnRunRecord:
    """Create a run record and launch the thread run worker."""

    await handler.preflight_stream_turn(turn_request, actor_id=actor_id)
    stable_request_key = str(turn_request.turn_idempotency_key or "").strip()
    if not stable_request_key:
        raise HTTPException(
            status_code=400,
            detail="Chat turn requires a stable request identity",
        )
    if not celery_settings.enabled:
        track_run_dispatch("backend_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Run execution backend unavailable: CELERY_ENABLED must be true",
        )
    if not redis_settings.enabled:
        track_run_dispatch("stream_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Run execution backend unavailable: REDIS_ENABLED must be true",
        )

    resolved_metadata: dict[str, Any] = dict(metadata) if isinstance(metadata, dict) else {}
    # Server-owned identity fields for run-level authorization. These keys are
    # intentionally reserved and always overwritten by gateway.
    resolved_metadata["_owner_id"] = actor_id
    if turn_request.workspace_id:
        resolved_metadata["_workspace_id"] = turn_request.workspace_id
    if turn_request.thread_id:
        resolved_metadata["_request_thread_id"] = turn_request.thread_id

    disconnect_mode = ChatTurnDisconnectMode.cancel if on_disconnect == ChatTurnDisconnectMode.cancel.value else ChatTurnDisconnectMode.continue_

    try:
        serialized_request = _serialize_turn_request(turn_request)
        admission = await run_manager.create_or_reject(
            run_thread_id,
            assistant_id=assistant_id,
            on_disconnect=disconnect_mode,
            metadata=resolved_metadata,
            kwargs=kwargs,
            multitask_strategy=multitask_strategy,
            request_idempotency_key=stable_request_key,
            request_fingerprint=_request_fingerprint(serialized_request),
            dispatch_payload=serialized_request,
        )
    except ChatTurnConflictError as exc:
        track_run_dispatch("conflict")
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedChatTurnStrategyError as exc:
        track_run_dispatch("invalid_strategy")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatTurnTransportUnavailableError as exc:
        track_run_dispatch("transport_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Chat turn transport is temporarily unavailable",
        ) from exc
    record = admission.record
    dispatch_owner = await run_manager.claim_dispatch(record.run_id)
    if dispatch_owner is None:
        track_run_dispatch("replay")
        return record

    try:
        from src.task.tasks import enqueue_chat_turn

        worker_task_id = enqueue_chat_turn(
            record.run_id,
            serialized_request,
            actor_id,
        )
        marked = await run_manager.mark_dispatched(
            record.run_id,
            owner=dispatch_owner,
            worker_task_id=worker_task_id,
        )
        if not marked:
            logger.warning(
                "Worker task %s was published but dispatch receipt for run %s "
                "could not be persisted",
                worker_task_id,
                record.run_id,
            )
        await bridge.publish(
            record.run_id,
            "run_queued",
            {
                "type": "run_queued",
                "run_id": record.run_id,
                "thread_id": run_thread_id,
                "status": "pending",
            },
        )
        track_run_dispatch("success")
        return record
    except Exception as exc:
        track_run_dispatch("queue_error")
        await run_manager.release_dispatch_claim(
            record.run_id,
            owner=dispatch_owner,
        )
        raise HTTPException(
            status_code=503,
            detail="Run worker queue unavailable",
        ) from exc


async def sse_consumer(
    *,
    bridge: StreamBridge,
    record: ChatTurnRunRecord,
    request: Request,
    run_manager: ChatTurnRunManager,
) -> AsyncIterator[str]:
    """Consume run stream events and emit SSE frames."""

    last_event_id = request.headers.get("Last-Event-ID")
    reached_stream_end = False
    subscription_failed = False

    try:
        try:
            async for item in bridge.subscribe(record.run_id, last_event_id=last_event_id):
                if await request.is_disconnected():
                    break

                if item is HEARTBEAT_SENTINEL:
                    yield ": heartbeat\n\n"
                    continue

                if item is END_SENTINEL:
                    reached_stream_end = True
                    yield format_sse("end", None, event_id=item.id or None)
                    return

                yield format_sse(item.event, item.data, event_id=item.id or None)
        except Exception:
            subscription_failed = True
            logger.warning(
                "Run %s stream subscription failed",
                record.run_id,
                exc_info=True,
            )
            if not await request.is_disconnected():
                yield format_sse(
                    "error",
                    {
                        "type": "error",
                        "error": "流式连接暂时不可用，请重试。",
                    },
                )
    finally:
        latest = await run_manager.get_or_load(record.run_id, refresh=True) or record
        if not reached_stream_end and not subscription_failed and latest.status in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running):
            if latest.on_disconnect == ChatTurnDisconnectMode.cancel:
                should_cancel = True
                grace_seconds = max(0.0, float(settings.runtime_disconnect_cancel_grace_seconds))
                if grace_seconds > 0:
                    await asyncio.sleep(grace_seconds)
                    latest = await run_manager.get_or_load(record.run_id, refresh=True) or latest
                    if latest.status not in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running):
                        should_cancel = False
                if should_cancel:
                    await run_manager.cancel(latest.run_id)

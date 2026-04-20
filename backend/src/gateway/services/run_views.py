"""Shared view/presentation helpers for run lifecycle routers."""

from __future__ import annotations

import logging
from typing import Any

from src.runtime.runs import RunManager, RunRecord
from src.runtime.serialization import serialize_channel_values
from src.services.workspace_skill_labels import resolve_thread_skill_name

logger = logging.getLogger(__name__)


async def build_wait_payload(
    *,
    record: RunRecord,
    actor_id: str,
    handler,
    run_manager: RunManager,
) -> dict[str, Any]:
    latest = await run_manager.get_or_load(record.run_id, refresh=True) or record
    payload: dict[str, Any] = {
        "run_id": latest.run_id,
        "thread_id": latest.thread_id,
        "status": latest.status.value,
        "error": latest.error,
    }

    thread_service = getattr(handler, "thread_service", None)
    if thread_service is None:
        return payload

    try:
        thread = await thread_service.get_thread(latest.thread_id, actor_id)
    except Exception:
        logger.debug(
            "Failed to resolve thread snapshot for run wait payload: run_id=%s thread_id=%s",
            latest.run_id,
            latest.thread_id,
            exc_info=True,
        )
        return payload

    if thread is None:
        return payload

    payload["values"] = serialize_channel_values(
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
    return payload

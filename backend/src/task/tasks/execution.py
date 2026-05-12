"""Celery task entrypoint for v2 capability execution via ExecutionEngineV2."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from celery import shared_task

from src.config import settings
from src.config.app_config import redis_settings

logger = logging.getLogger(__name__)


async def _execute_execution_async(execution_id: str) -> dict[str, Any]:
    from src.academic.cache.redis_client import redis_client
    from src.database import get_db_session, reset_db_engine
    from src.services.capability_resolver import CapabilityResolver
    from src.services.event_bus import EventBus
    from src.services.execution_event_publisher import (
        publish_execution_event,
        publish_execution_stream_end,
    )
    from src.services.execution_service import ExecutionService
    from src.services.rooms.run_history_service import RunHistoryService

    if not redis_settings.enabled:
        raise RuntimeError("execute_execution requires REDIS_ENABLED=true")

    await reset_db_engine(dispose_current=False)
    await redis_client.reset_client(close_current=False)
    await redis_client.reset_stream_client(close_current=False)
    await redis_client.connect()
    await redis_client.connect_stream()

    async with get_db_session() as db:
        execution_service = ExecutionService(db, redis=redis_client.client)
        record = await execution_service.get_by_id(execution_id)
        if record is None:
            return {"ok": False, "reason": "execution_not_found", "execution_id": execution_id}

        workspace_id = str(record.workspace_id) if record.workspace_id else None

        # Publish running status to execution stream + workspace events
        if workspace_id:
            await publish_execution_event(
                execution_id,
                "execution.status",
                {"status": "running", "message": "Starting execution"},
                workspace_id=workspace_id,
            )

        # Build deps
        run_history_service = RunHistoryService(db)
        event_bus = EventBus(redis_client.client)
        resolver = CapabilityResolver(
            session_factory=get_db_session,
            event_bus=event_bus,
        )

        # Wire publish_event for LeadAgentRuntime
        async def _publish_fn(
            exec_id: str,
            event_name: str,
            payload: dict,
        ) -> None:
            await publish_execution_event(
                exec_id,
                event_name,
                payload,
                workspace_id=workspace_id,
            )

        # Build runtime + engine
        from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
        from src.execution.engine import ExecutionEngineV2
        from src.services.workspace_skill_labels import get_workspace_type as _resolve_ws_type

        async def _resolve_ws_type_with_fallback(ws_id: str) -> str:
            # ``get_workspace_type`` is async; wrap so the ``or "thesis"``
            # fallback actually evaluates against the awaited result instead
            # of against a (truthy) coroutine object.
            return (await _resolve_ws_type(db, ws_id)) or "thesis"

        async def _record_node_event(**kw: Any) -> None:
            # Persist per-node lifecycle (running / completed / failed) so the
            # FE node-detail endpoint sees real input/output instead of an
            # empty row.  Best-effort: a DB hiccup must not abort the run.
            try:
                await execution_service.upsert_node_event(**kw)
            except Exception:
                logger.warning("upsert_node_event failed", exc_info=True)

        runtime = LeadAgentRuntime(
            resolver=resolver,
            publish_event=_publish_fn,
            get_workspace_type=_resolve_ws_type_with_fallback,
            redis=redis_client.client,
            record_node_event=_record_node_event,
        )
        engine = ExecutionEngineV2(
            runtime=runtime,
            execution_service=execution_service,
            run_history_service=run_history_service,
        )

        try:
            await engine.run(execution_id)
        finally:
            await publish_execution_stream_end(execution_id)

        # Reload to get final status
        final = await execution_service.get_by_id(execution_id)
        return {
            "ok": True,
            "execution_id": execution_id,
            "status": final.status if final else "unknown",
        }


def _execute_execution_entry(
    _self: Any,
    execution_id: str,
) -> dict[str, Any]:
    from src.task.worker import run_worker_coroutine

    runner = cast(
        Callable[[Awaitable[dict[str, Any]]], dict[str, Any]],
        run_worker_coroutine,
    )
    return runner(_execute_execution_async(execution_id))


execute_execution = shared_task(
    bind=True,
    name="src.task.tasks.execute_execution",
)(_execute_execution_entry)

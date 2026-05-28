"""Celery task entrypoint for v2 capability execution via ExecutionEngineV2."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from celery import shared_task

from src.config.app_config import redis_settings

logger = logging.getLogger(__name__)

_TERMINAL_EXECUTION_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "failed_partial",
        "cancelled",
    }
)


def is_terminal_execution_status(status: Any) -> bool:
    """Return whether a redelivered execution task should no-op."""
    return str(status or "").strip().lower() in _TERMINAL_EXECUTION_STATUSES


def _result_card_data_from_task_report(execution_id: str, task_report: dict[str, Any]) -> dict[str, Any]:
    """Build the async ResultCard payload consumed by the workspace frontend."""
    raw_outputs = task_report.get("outputs")
    outputs: list[dict[str, Any]] = []
    if isinstance(raw_outputs, list):
        for output in raw_outputs:
            if not isinstance(output, dict):
                continue
            outputs.append(
                {
                    "id": str(output.get("id") or ""),
                    "kind": str(output.get("kind") or ""),
                    "preview": str(output.get("preview") or ""),
                    "default_checked": output.get("default_checked") is not False,
                    "data": output.get("data") if isinstance(output.get("data"), dict) else {},
                }
            )

    raw_review_items = task_report.get("review_items")
    review_items = raw_review_items if isinstance(raw_review_items, list) else None

    raw_errors = task_report.get("errors")
    errors: list[dict[str, Any]] = []
    if isinstance(raw_errors, list):
        for error in raw_errors:
            if not isinstance(error, dict):
                continue
            errors.append(
                {
                    "message": str(error.get("error") or error.get("message") or ""),
                    "phase": error.get("phase"),
                    "task": error.get("task"),
                }
            )

    return {
        "execution_id": str(task_report.get("execution_id") or execution_id),
        "capability_name": task_report.get("capability_id"),
        "status": task_report.get("status") or "completed",
        "outputs": outputs,
        "review_items": review_items,
        "narrative": task_report.get("narrative"),
        "duration_seconds": task_report.get("duration_seconds"),
        "errors": errors,
    }


async def _persist_result_card_for_execution(db: Any, execution: Any) -> None:
    """Persist a result_card block so completed executions survive reloads."""
    result = getattr(execution, "result", None)
    task_report = result.get("task_report") if isinstance(result, dict) else None
    if not isinstance(task_report, dict):
        return

    thread_id = str(getattr(execution, "thread_id", "") or "")
    if not thread_id:
        return

    from src.services import ThreadService

    thread_service = ThreadService(db)
    thread = await thread_service.get_by_id(thread_id)
    if thread is None:
        return

    execution_id = str(getattr(execution, "id", "") or task_report.get("execution_id") or "")
    if not execution_id:
        return

    messages = await thread_service.list_thread_messages(thread)
    for message in messages:
        for block in message.get("blocks") or []:
            if not isinstance(block, dict) or block.get("kind") != "result_card":
                continue
            data = block.get("data")
            if isinstance(data, dict) and str(data.get("execution_id") or "") == execution_id:
                return

    result_card_data = _result_card_data_from_task_report(execution_id, task_report)
    await thread_service.add_message(
        thread,
        role="assistant",
        content=str(task_report.get("narrative") or "执行已完成。"),
        blocks=[{"kind": "result_card", "data": result_card_data}],
        metadata={"source": "execution_completion", "execution_id": execution_id},
    )


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
        if is_terminal_execution_status(getattr(record, "status", None)):
            return {
                "ok": True,
                "execution_id": execution_id,
                "status": getattr(record, "status", "unknown"),
                "skipped": True,
                "reason": "execution_already_terminal",
            }

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
            # Persist per-node lifecycle into ``executions.node_states`` so the
            # FE ``GET /executions/{id}/nodes/{node_id}`` endpoint returns real
            # input/output/thinking.  (That endpoint reads the JSONB blob on
            # the executions row, not the ``execution_nodes`` table.)
            # Best-effort: a DB hiccup must not abort the run.
            try:
                await execution_service.upsert_node_event(
                    execution_id=kw["execution_id"],
                    node_id=kw["node_id"],
                    node_type=kw.get("node_type") or "subagent",
                    label=kw.get("label"),
                    status=kw.get("status") or "running",
                    input_data=kw.get("input_data"),
                    output_data=kw.get("output_data"),
                    thinking=kw.get("thinking"),
                    tool_calls=kw.get("tool_calls"),
                    token_usage=kw.get("token_usage"),
                    started_at=kw.get("started_at"),
                    completed_at=kw.get("completed_at"),
                )
                await execution_service.update_node_state(
                    execution_id=kw["execution_id"],
                    node_id=kw["node_id"],
                    status=kw.get("status"),
                    input_data=kw.get("input_data"),
                    output_data=kw.get("output_data"),
                    thinking=kw.get("thinking"),
                    tool_calls=kw.get("tool_calls"),
                    token_usage=kw.get("token_usage"),
                    started_at=kw.get("started_at"),
                    completed_at=kw.get("completed_at"),
                )
                await execution_service.append_execution_event(
                    kw["execution_id"],
                    "execution.node",
                    workspace_id=workspace_id,
                    node_id=kw.get("node_id"),
                    payload_json={
                        "node_type": kw.get("node_type"),
                        "label": kw.get("label"),
                        "status": kw.get("status"),
                        "input": kw.get("input_data"),
                        "output": kw.get("output_data"),
                        "thinking": kw.get("thinking"),
                        "tool_calls": kw.get("tool_calls"),
                        "token_usage": kw.get("token_usage"),
                    },
                )
            except Exception:
                logger.warning("update_node_state failed", exc_info=True)

        runtime = LeadAgentRuntime(
            resolver=resolver,
            publish_event=_publish_fn,
            get_workspace_type=_resolve_ws_type_with_fallback,
            redis=redis_client.client,
            db=db,
            record_node_event=_record_node_event,
        )
        engine = ExecutionEngineV2(
            runtime=runtime,
            execution_service=execution_service,
        )

        try:
            await engine.run(execution_id)
            final = await execution_service.get_by_id(execution_id)
            if final is not None and final.status in {"completed", "failed_partial", "cancelled"}:
                try:
                    await _persist_result_card_for_execution(db, final)
                except Exception:
                    logger.warning("persist result_card failed", exc_info=True)
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

"""Shared HTTP helpers for run lifecycle routers."""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from src.gateway.services.run_lifecycle import sse_consumer
from src.observability.prometheus import observe_run_wait
from src.runtime.runs import RunManager, RunRecord, RunStatus
from src.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge


def build_run_stream_headers(run_id: str) -> dict[str, str]:
    """Build SSE headers for run stream responses."""
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Location": f"/api/runs/{run_id}/stream",
    }


async def get_run_or_404(
    run_manager: RunManager,
    run_id: str,
    *,
    thread_id: str | None = None,
) -> RunRecord:
    """Get run record and optionally enforce thread scope."""
    record = await run_manager.get_or_load(run_id, refresh=True)
    if record is None or (thread_id is not None and record.thread_id != thread_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return record


async def await_run_task(
    record: RunRecord,
    *,
    run_manager: RunManager,
    bridge: StreamBridge | None = None,
    timeout_seconds: float = 3600.0,
    poll_interval_seconds: float = 0.5,
) -> RunRecord:
    """Await run task completion while swallowing cancellation/runtime errors."""
    started_at = time.perf_counter()
    polls = 0
    if record.task is None:
        if bridge is not None:
            deadline = time.monotonic() + max(1.0, timeout_seconds)
            heartbeat_seconds = max(0.5, float(poll_interval_seconds))
            try:
                async for item in bridge.subscribe(
                    record.run_id,
                    heartbeat_interval=heartbeat_seconds,
                ):
                    if time.monotonic() >= deadline:
                        observe_run_wait("timeout", time.perf_counter() - started_at, polls)
                        raise HTTPException(
                            status_code=504,
                            detail=f"Run {record.run_id} wait timed out",
                        )

                    if item is HEARTBEAT_SENTINEL:
                        polls += 1
                        latest = await run_manager.get_or_load(record.run_id, refresh=True)
                        if latest is not None:
                            record = latest
                        if record.status not in (RunStatus.pending, RunStatus.running):
                            observe_run_wait(
                                record.status.value,
                                time.perf_counter() - started_at,
                                polls,
                            )
                            return record
                        continue

                    if item is END_SENTINEL:
                        polls += 1
                        latest = await run_manager.get_or_load(record.run_id, refresh=True)
                        if latest is not None:
                            record = latest
                        if record.status not in (RunStatus.pending, RunStatus.running):
                            observe_run_wait(
                                record.status.value,
                                time.perf_counter() - started_at,
                                polls,
                            )
                            return record
                        break
            except HTTPException:
                raise
            except Exception:
                # Fall back to status polling when stream consumption fails.
                pass

        deadline = time.monotonic() + max(1.0, timeout_seconds)
        while True:
            polls += 1
            latest = await run_manager.get_or_load(record.run_id, refresh=True)
            if latest is not None:
                record = latest
            if record.status not in (RunStatus.pending, RunStatus.running):
                observe_run_wait(record.status.value, time.perf_counter() - started_at, polls)
                return record
            if time.monotonic() >= deadline:
                observe_run_wait("timeout", time.perf_counter() - started_at, polls)
                raise HTTPException(
                    status_code=504,
                    detail=f"Run {record.run_id} wait timed out",
                )
            await asyncio.sleep(max(0.05, poll_interval_seconds))

    try:
        await record.task
    except (asyncio.CancelledError, Exception):
        pass
    latest = await run_manager.get_or_load(record.run_id, refresh=True)
    resolved = latest or record
    observe_run_wait(resolved.status.value, time.perf_counter() - started_at, polls)
    return resolved


def stream_run_response(
    *,
    bridge: StreamBridge,
    record: RunRecord,
    request: Request,
    run_manager: RunManager,
) -> StreamingResponse:
    """Build the standard streaming response for an existing run."""
    return StreamingResponse(
        sse_consumer(
            bridge=bridge,
            record=record,
            request=request,
            run_manager=run_manager,
        ),
        media_type="text/event-stream",
        headers=build_run_stream_headers(record.run_id),
    )


async def cancel_run_with_http_response(
    *,
    run_manager: RunManager,
    record: RunRecord,
    action: Literal["interrupt", "rollback"],
    wait: bool,
) -> Response:
    """Cancel a run and return canonical HTTP response semantics."""
    cancelled = await run_manager.cancel(record.run_id, action=action)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run {record.run_id} is not cancellable "
                f"(status: {record.status.value})"
            ),
        )

    if wait:
        await await_run_task(record, run_manager=run_manager)
        return Response(status_code=204)

    return Response(status_code=202)


async def maybe_cancel_then_wait(
    *,
    run_manager: RunManager,
    record: RunRecord,
    action: Literal["interrupt", "rollback"] | None,
    wait: bool,
) -> Response | None:
    """Handle optional cancel action for stream/join endpoints."""
    if action is None:
        return None

    cancelled = await run_manager.cancel(record.run_id, action=action)
    if cancelled and wait:
        await await_run_task(record, run_manager=run_manager)
        return Response(status_code=204)
    return None

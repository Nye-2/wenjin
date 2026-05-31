"""Execution endpoints — converged with run stream protocol.

Uses the SAME Redis Streams prefix (`runtime:runs:stream`) and SAME SSE
framing as the run stream endpoints in ``thread_runs.py`` / ``runs.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.gateway.services.run_lifecycle import format_sse
from src.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL
from src.services.execution_event_publisher import _get_stream_bridge
from src.services.execution_service import ExecutionService, serialize_execution_record

router = APIRouter(prefix="/executions", tags=["executions"])


def _jsonable_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _execution_sse_consumer(
    *,
    execution_id: str,
    request: Request,
) -> Any:
    """Consume execution stream events and emit SSE frames.

    Mirrors ``sse_consumer()`` in ``run_lifecycle.py`` — same protocol,
    same sentinel handling, same heartbeat semantics.
    """
    bridge = _get_stream_bridge()
    if bridge is None:
        raise RuntimeError("Stream bridge is not available")

    last_event_id = request.headers.get("Last-Event-ID")
    reached_stream_end = False
    subscription_failed = False

    try:
        try:
            async for item in bridge.subscribe(
                execution_id,
                last_event_id=last_event_id,
                heartbeat_interval=15.0,
            ):
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
            if not await request.is_disconnected():
                yield format_sse(
                    "error",
                    {"type": "error", "error": "Stream subscription failed"},
                )
    finally:
        if not reached_stream_end and not subscription_failed:
            yield format_sse("end", None)


@router.get("/{execution_id}/stream")
async def stream_execution(
    execution_id: str,
    request: Request,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> StreamingResponse:
    """Subscribe to execution events via SSE (unified stream protocol)."""
    svc = ExecutionService(dataservice=dataservice)
    record = await svc.get_by_id(execution_id)
    if record is None or record.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return StreamingResponse(
        _execution_sse_consumer(execution_id=execution_id, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/executions/{execution_id}/stream",
        },
    )


@router.get("/{execution_id}")
async def get_execution(
    execution_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    """Get a single execution record by ID."""
    svc = ExecutionService(dataservice=dataservice)
    record = await svc.get_by_id(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    if record.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return serialize_execution_record(record)


@router.get("/{execution_id}/nodes/{node_id}")
async def get_node_detail(
    execution_id: str,
    node_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    """Return full detail for a single node within an execution."""
    svc = ExecutionService(dataservice=dataservice)
    record = await svc.get_by_id(execution_id)
    if record is None or record.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Execution not found")

    graph_structure = record.graph_structure or {"nodes": [], "edges": []}
    static_node = None
    for n in graph_structure.get("nodes", []):
        if n.get("id") == node_id:
            static_node = n
            break

    node_record = await svc.find_node_by_node_id(execution_id, node_id)

    if static_node is None and node_record is None:
        raise HTTPException(status_code=404, detail="Node not found")

    return {
        "id": node_id,
        "label": (node_record.label if node_record else None) or (static_node or {}).get("label"),
        "status": node_record.status if node_record else "pending",
        "phase_index": (static_node or {}).get("phase_index"),
        "input": node_record.input_data if node_record else None,
        "output": node_record.output_data if node_record else None,
        "thinking": node_record.thinking if node_record else None,
        "tools": node_record.tool_calls if node_record else None,
        "token_usage": node_record.token_usage if node_record else None,
        "started_at": _jsonable_timestamp(node_record.started_at) if node_record else None,
        "completed_at": _jsonable_timestamp(node_record.completed_at) if node_record else None,
    }


@router.post("/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    action: str = Query(default="interrupt"),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    """Cancel an active execution.

    The current implementation uses the canonical execution abort signal and
    does not distinguish interrupt vs rollback behavior yet.
    """
    _ = action
    svc = ExecutionService(dataservice=dataservice)
    record = await svc.get_by_id(execution_id)
    if record is None or record.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Execution not found")

    updated = await svc.cancel_execution(execution_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "execution_id": execution_id,
        "status": updated.status,
    }


@router.get("")
async def list_executions(
    workspace_id: str | None = Query(default=None),
    thread_id: str | None = Query(default=None),
    execution_type: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    """List execution records for the current user."""
    svc = ExecutionService(dataservice=dataservice)
    items = await svc.list_executions(
        user_id=str(current_user.id),
        workspace_id=workspace_id,
        thread_id=thread_id,
        execution_type=execution_type,
        status=status,
        limit=limit,
    )
    return {
        "items": [serialize_execution_record(r) for r in items],
        "count": len(items),
    }

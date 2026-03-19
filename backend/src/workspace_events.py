"""Workspace-scoped event publishing and streaming helpers."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from src.academic.cache.redis_client import redis_client


def _workspace_channel(workspace_id: str) -> str:
    """Redis pub/sub channel for a workspace event stream."""
    return f"workspace:{workspace_id}:events"


def _serialize_event(
    workspace_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> str:
    """Serialize a workspace event to JSON."""
    event = {
        "type": event_type,
        "workspace_id": workspace_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if payload:
        event.update(payload)
    return json.dumps(event, ensure_ascii=False, default=str)


async def publish_workspace_event(
    workspace_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish a workspace event if Redis is available."""
    resolved_workspace_id = (workspace_id or "").strip()
    if not resolved_workspace_id:
        return
    if redis_client._client is None:
        return

    try:
        await redis_client.client.publish(
            _workspace_channel(resolved_workspace_id),
            _serialize_event(resolved_workspace_id, event_type, payload),
        )
    except Exception:
        # Workspace event delivery is best-effort and must never break
        # the underlying business operation.
        return


async def stream_workspace_events(workspace_id: str):
    """Subscribe to workspace events as an SSE generator."""
    if redis_client._client is None:
        raise RuntimeError("Redis not connected")

    pubsub = redis_client.client.pubsub()
    await pubsub.subscribe(_workspace_channel(workspace_id))

    ready_payload = _serialize_event(
        workspace_id,
        "workspace.ready",
        {"message": "Workspace event stream connected"},
    )

    async def _generator():
        try:
            yield f"data: {ready_payload}\n\n"

            timeout = 3600
            start_time = asyncio.get_event_loop().time()
            last_ping = start_time

            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"

                now = asyncio.get_event_loop().time()
                if now - last_ping > 30:
                    yield ": ping\n\n"
                    last_ping = now

                if now - start_time > timeout:
                    break
        finally:
            await pubsub.unsubscribe(_workspace_channel(workspace_id))
            await pubsub.close()

    return _generator()

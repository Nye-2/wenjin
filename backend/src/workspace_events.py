"""Workspace-scoped event publishing and streaming helpers."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from src.academic.cache.redis_client import redis_client
from src.runtime.serialization import dumps_json, encode_sse_data

logger = logging.getLogger(__name__)


class WorkspaceEventStreamUnavailable(RuntimeError):
    """Raised when the workspace event stream cannot be initialized."""


def _workspace_channel(workspace_id: str) -> str:
    """Redis pub/sub channel for a workspace event stream."""
    return f"workspace:{workspace_id}:events"


def _serialize_event(
    workspace_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a workspace event payload."""
    event = {
        "type": event_type,
        "workspace_id": workspace_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if payload:
        event.update(payload)
    return event


def _decode_workspace_stream_payload(raw_payload: Any) -> dict[str, Any] | str:
    """Normalize pub/sub payloads into dicts when JSON is available."""
    payload = raw_payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        if isinstance(decoded, dict):
            return decoded
        return payload
    if isinstance(payload, dict):
        return payload
    return str(payload)


async def publish_workspace_event(
    workspace_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish a workspace event if Redis is available."""
    resolved_workspace_id = (workspace_id or "").strip()
    if not resolved_workspace_id:
        return
    try:
        await redis_client.connect()
        event_payload = _serialize_event(resolved_workspace_id, event_type, payload)
        await redis_client.client.publish(
            _workspace_channel(resolved_workspace_id),
            dumps_json(event_payload, ensure_ascii=False),
        )
    except Exception:
        # Workspace event delivery is best-effort and must never break
        # the underlying business operation.
        logger.warning(
            "Failed to publish workspace event: workspace_id=%s type=%s",
            resolved_workspace_id,
            event_type,
            exc_info=True,
        )
        return


async def stream_workspace_events(workspace_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to workspace events as an SSE generator."""
    try:
        pubsub = await redis_client.create_pubsub()
    except Exception as exc:
        raise WorkspaceEventStreamUnavailable(
            f"Failed to initialize workspace event stream for {workspace_id}"
        ) from exc
    channel = _workspace_channel(workspace_id)
    subscribed = False
    try:
        await pubsub.subscribe(channel)
        subscribed = True
    except Exception as exc:
        try:
            await pubsub.close()
        except Exception:
            logger.debug(
                "Failed to close workspace event pubsub after subscribe error",
                exc_info=True,
            )
        raise WorkspaceEventStreamUnavailable(
            f"Failed to subscribe workspace event stream for {workspace_id}"
        ) from exc

    ready_payload = _serialize_event(
        workspace_id,
        "workspace.ready",
        {"message": "Workspace event stream connected"},
    )

    async def _stream() -> AsyncGenerator[str, None]:
        try:
            yield encode_sse_data(ready_payload, ensure_ascii=False)

            timeout = 3600
            heartbeat_interval = 15.0
            start_time = asyncio.get_running_loop().time()
            next_ping_at = start_time + heartbeat_interval

            while True:
                now = asyncio.get_running_loop().time()
                if now - start_time > timeout:
                    break

                remaining_until_ping = max(0.0, next_ping_at - now)
                poll_timeout = min(1.0, remaining_until_ping or 1.0)

                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=poll_timeout,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning(
                        "Workspace event stream listen failed: workspace_id=%s",
                        workspace_id,
                        exc_info=True,
                    )
                    break

                if message and message.get("type") == "message":
                    payload = _decode_workspace_stream_payload(message.get("data", ""))
                    yield encode_sse_data(payload, ensure_ascii=False)

                now = asyncio.get_running_loop().time()
                if now >= next_ping_at:
                    yield ": ping\n\n"
                    next_ping_at = now + heartbeat_interval
        finally:
            try:
                if subscribed:
                    await pubsub.unsubscribe(channel)
            except Exception:
                logger.debug(
                    "Failed to unsubscribe workspace event stream: workspace_id=%s",
                    workspace_id,
                    exc_info=True,
                )
            finally:
                try:
                    await pubsub.close()
                except Exception:
                    logger.debug(
                        "Failed to close workspace event stream pubsub: workspace_id=%s",
                        workspace_id,
                        exc_info=True,
                    )

    return _stream()

"""Unified execution event publisher.

Publishes execution events to both:
1. ExecutionStream (Redis Streams) — fine-grained runtime events
2. Workspace Events (Redis Pub/Sub) — lightweight notifications
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.academic.cache.redis_client import redis_client

from src.runtime.stream_bridge import RedisStreamBridge
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)

# Unified stream prefix — converged with run streams from day 1.
# Execution IDs and Run IDs are both UUIDs, so key collisions are impossible.
EXECUTION_STREAM_PREFIX = "runtime:runs:stream"

# Shared RedisStreamBridge instance for execution events
_execution_stream_bridge: RedisStreamBridge | None = None


def _get_stream_bridge() -> RedisStreamBridge | None:
    """Lazy-init the unified stream bridge (workers + gateway).

    Workers call this because they don't have access to ``app.state.stream_bridge``.
    The gateway uses ``app.state.stream_bridge`` directly (same prefix, same Redis client).
    """
    global _execution_stream_bridge
    if _execution_stream_bridge is None:
        try:
            _execution_stream_bridge = RedisStreamBridge(
                redis_backend=redis_client.stream_client,
                key_prefix=EXECUTION_STREAM_PREFIX,
            )
        except Exception:
            logger.debug("Stream bridge not available yet", exc_info=True)
            return None
    return _execution_stream_bridge


async def publish_execution_event(
    execution_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    workspace_id: str | None = None,
    publish_to_workspace: bool = True,
) -> None:
    """Publish an execution event to ExecutionStream and optionally Workspace Events.

    Args:
        execution_id: The execution ID (used as stream key)
        event_type: Event type (e.g., "execution.metadata", "execution.node.started")
        payload: Event-specific payload
        workspace_id: Optional workspace ID for Workspace Events
        publish_to_workspace: Whether to also publish a lightweight notification
    """
    # 1. Publish to ExecutionStream
    bridge = _get_stream_bridge()
    if bridge is not None:
        try:
            event_payload = {
                "execution_id": execution_id,
                "type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
            await bridge.publish(
                execution_id,
                event_type,
                event_payload,
            )
        except Exception:
            logger.warning(
                "Failed to publish execution stream event: execution_id=%s type=%s",
                execution_id,
                event_type,
                exc_info=True,
            )

    # 2. Publish lightweight notification to Workspace Events
    if publish_to_workspace and workspace_id:
        try:
            # Notify frontend on lifecycle boundaries and graph init so it can
            # start/stop the execution stream subscription. graph_structure is
            # included so the frontend can subscribe early enough to catch
            # node-level events (start race is otherwise possible).
            if event_type in (
                "execution.status",
                "execution.graph_structure",
                "execution.completed",
                "execution.error",
            ):
                await publish_workspace_event(
                    workspace_id,
                    "execution.updated",
                    {
                        "execution_id": execution_id,
                        "event_type": event_type,
                        "status": payload.get("status"),
                    },
                )
        except Exception:
            logger.warning(
                "Failed to publish workspace event: workspace_id=%s execution_id=%s",
                workspace_id,
                execution_id,
                exc_info=True,
            )


async def publish_execution_stream_end(execution_id: str) -> None:
    """Publish end sentinel to the execution stream."""
    bridge = _get_stream_bridge()
    if bridge is not None:
        try:
            await bridge.publish_end(execution_id)
        except Exception:
            logger.warning(
                "Failed to publish execution stream end: execution_id=%s",
                execution_id,
                exc_info=True,
            )


def subscribe_execution_events(
    execution_id: str,
    *,
    last_event_id: str | None = None,
    heartbeat_interval: float = 15.0,
):
    """Subscribe to execution events (SSE consumer).

    Returns an AsyncIterator[StreamEvent] for gateway SSE consumption.
    """
    bridge = _get_stream_bridge()
    if bridge is None:
        raise RuntimeError("Execution stream bridge is not available")
    return bridge.subscribe(
        execution_id,
        last_event_id=last_event_id,
        heartbeat_interval=heartbeat_interval,
    )

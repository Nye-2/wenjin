"""Server-Sent Events for task progress streaming."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from src.task.registry import TaskStatus

logger = logging.getLogger(__name__)


async def create_task_sse_stream(task_id: str) -> AsyncGenerator[str, None]:
    """Create SSE stream for task progress updates.

    Args:
        task_id: Task ID to stream

    Yields:
        SSE formatted strings
    """
    from src.academic.cache.redis_client import redis_client

    channel = f"task_progress:{task_id}"
    pubsub = redis_client.client.pubsub()
    await pubsub.subscribe(channel)

    try:
        # Send initial status
        from src.task.store import TaskStore
        from src.database import get_db_session

        async with get_db_session() as db:
            store = TaskStore(redis_client, db)
            initial_state = await store.get_task_state(task_id)
            if initial_state:
                yield _format_sse_event(initial_state)

        # Listen for updates
        timeout = 3600  # 1 hour max
        start_time = asyncio.get_event_loop().time()
        last_ping = start_time

        # Get terminal status values for comparison
        terminal_statuses = {s.value for s in TaskStatus.terminal_statuses()}

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                yield _format_sse_event(data)

                # Check if task is done
                if data.get("status") in terminal_statuses:
                    break

            now = asyncio.get_event_loop().time()

            # Send keepalive ping every 30 seconds
            if now - last_ping > 30:
                yield ": ping\n\n"
                last_ping = now

            # Check timeout (from start, not from last ping)
            if now - start_time > timeout:
                break

    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def _format_sse_event(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"

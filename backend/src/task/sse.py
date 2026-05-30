"""Server-Sent Events for task progress streaming."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.runtime.serialization import encode_sse_data, serialize_lc_object
from src.task.registry import TaskStatus

logger = logging.getLogger(__name__)


class TaskEventStreamUnavailable(RuntimeError):
    """Raised when the task SSE stream cannot be initialized."""


def _terminal_status_values() -> set[str]:
    return {status.value for status in TaskStatus.terminal_statuses()}


def _task_snapshot_from_record(record: Any) -> dict[str, Any]:
    runtime_state = record.runtime_state if isinstance(record.runtime_state, dict) else None
    current_step = None
    if runtime_state is not None:
        raw_current_step = runtime_state.get("current_phase")
        if isinstance(raw_current_step, str) and raw_current_step.strip():
            current_step = raw_current_step.strip()

    return {
        "task_id": str(record.id),
        "status": str(record.status),
        "progress": int(record.progress or 0),
        "message": record.message,
        "current_step": current_step,
        "metadata": (
            serialize_lc_object({"runtime": runtime_state})
            if runtime_state is not None
            else None
        ),
        "result": serialize_lc_object(record.result) if record.result is not None else None,
        "error": record.error,
        "timestamp": (
            record.completed_at.isoformat()
            if record.completed_at is not None
            else record.started_at.isoformat()
            if record.started_at is not None
            else record.created_at.isoformat()
            if record.created_at is not None
            else None
        ),
    }


def _decode_pubsub_payload(raw_payload: Any, task_id: str) -> dict[str, Any] | None:
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, bytes):
        try:
            raw_payload = raw_payload.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Task SSE payload decode failed: task_id=%s", task_id, exc_info=True)
            return None
    if isinstance(raw_payload, str):
        try:
            decoded = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning("Task SSE payload JSON parse failed: task_id=%s", task_id, exc_info=True)
            return None
        if isinstance(decoded, dict):
            return decoded
    return None


async def create_task_sse_stream(task_id: str) -> AsyncGenerator[str, None]:
    """Create SSE stream for task progress updates.

    Args:
        task_id: Task ID to stream

    Yields:
        SSE formatted strings
    """
    from src.academic.cache.redis_client import redis_client

    channel = f"task_progress:{task_id}"
    try:
        pubsub = await redis_client.create_pubsub()
    except Exception as exc:
        raise TaskEventStreamUnavailable(
            f"Failed to initialize task progress stream for {task_id}"
        ) from exc
    subscribed = False
    try:
        await pubsub.subscribe(channel)
        subscribed = True
    except Exception as exc:
        try:
            await pubsub.close()
        except Exception:
            logger.debug(
                "Failed to close task SSE pubsub after subscribe error",
                exc_info=True,
            )
        raise TaskEventStreamUnavailable(
            f"Failed to subscribe task progress stream for {task_id}"
        ) from exc

    async def _stream() -> AsyncGenerator[str, None]:
        try:
            terminal_statuses = _terminal_status_values()

            # Send initial status
            from src.dataservice_client.provider import dataservice_client
            from src.task.store import TaskStore

            async with dataservice_client() as dataservice:
                store = TaskStore(redis_client, dataservice=dataservice)
                initial_state = await store.get_task_state(task_id)
                initial_payload: dict[str, Any] | None = None
                if initial_state:
                    initial_payload = dict(initial_state)
                    initial_payload.setdefault("task_id", task_id)
                else:
                    record = await store.get_task_record(task_id)
                    if record is not None:
                        initial_payload = _task_snapshot_from_record(record)

                if initial_payload is not None:
                    yield _format_sse_event(initial_payload)
                    if str(initial_payload.get("status") or "") in terminal_statuses:
                        return

            # Listen for updates
            timeout = 3600  # 1 hour max
            heartbeat_interval = 30.0
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
                        "Task SSE listen failed: task_id=%s",
                        task_id,
                        exc_info=True,
                    )
                    break

                if message and message.get("type") == "message":
                    payload = _decode_pubsub_payload(message.get("data"), task_id)
                    if payload is not None:
                        payload.setdefault("task_id", task_id)
                        yield _format_sse_event(payload)
                        if str(payload.get("status") or "") in terminal_statuses:
                            break

                now = asyncio.get_running_loop().time()
                if now >= next_ping_at:
                    yield ": ping\n\n"
                    next_ping_at = now + heartbeat_interval

        finally:
            try:
                if subscribed:
                    await pubsub.unsubscribe(channel)
            finally:
                await pubsub.close()

    return _stream()


def _format_sse_event(data: dict[str, Any]) -> str:
    """Format data as SSE event."""
    return encode_sse_data(data)

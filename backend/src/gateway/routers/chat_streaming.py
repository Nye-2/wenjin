"""SSE helpers for chat streaming responses."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def encode_sse_event(payload: Mapping[str, Any]) -> str:
    """Serialize one SSE data frame."""
    return f"data: {json.dumps(dict(payload))}\n\n"


def stream_thread_context_event(*, thread_id: str, skill: str | None) -> str:
    return encode_sse_event(
        {
            "type": "thread_id",
            "thread_id": thread_id,
            "skill": skill,
        }
    )


def stream_content_event(content: str) -> str:
    return encode_sse_event({"type": "content", "content": content})


def stream_reasoning_event(content: str) -> str:
    return encode_sse_event({"type": "reasoning", "content": content})


def stream_assistant_message_event(message: Mapping[str, Any]) -> str:
    return encode_sse_event({"type": "assistant_message", "message": dict(message)})


def stream_error_event(error: str) -> str:
    return encode_sse_event({"type": "error", "error": error})


def stream_done_event() -> str:
    return encode_sse_event({"type": "done"})


def stream_heartbeat_event() -> str:
    """SSE comment line — keeps the connection alive without triggering data handlers."""
    return ": heartbeat\n\n"

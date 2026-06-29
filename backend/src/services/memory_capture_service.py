"""Retired ingress for cross-workspace long-term memory capture writes."""

from __future__ import annotations

import logging
from typing import Any
from src.agents.memory.queue import MemoryQueue, get_default_memory_queue

logger = logging.getLogger(__name__)


class MemoryCaptureService:
    """Retired cross-workspace memory capture boundary.

    Workspace memory is now updated through explicit low-frequency workspace
    memory calls. Ordinary turns must not enqueue extraction jobs.
    """

    def __init__(self, queue: MemoryQueue | None = None) -> None:
        self._queue = queue or get_default_memory_queue()

    async def capture_messages(
        self,
        *,
        thread_id: str,
        user_id: str | None,
        workspace_id: str | None,
        messages: list[Any],
        source: str | None = None,
    ) -> None:
        """Ignore old per-turn capture requests."""
        del thread_id, user_id, workspace_id, messages, source
        return None

    def enqueue_messages(
        self,
        *,
        thread_id: str,
        user_id: str | None,
        workspace_id: str | None,
        messages: list[Any],
        source: str | None = None,
    ) -> None:
        """Ignore old queued capture requests."""
        del thread_id, user_id, workspace_id, messages, source
        return None

    async def persist_conversation(
        self,
        *,
        user_id: str | None,
        conversation_text: str,
        workspace_context: str | None = None,
        source: str | None = None,
    ) -> int:
        """Return zero because cross-workspace memory capture is retired."""
        del user_id, conversation_text, workspace_context, source
        return 0


_DEFAULT_CAPTURE_SERVICE: MemoryCaptureService | None = None


def get_memory_capture_service() -> MemoryCaptureService:
    """Return the process-local default memory capture service."""
    global _DEFAULT_CAPTURE_SERVICE
    if _DEFAULT_CAPTURE_SERVICE is None:
        _DEFAULT_CAPTURE_SERVICE = MemoryCaptureService()
    return _DEFAULT_CAPTURE_SERVICE


def reset_memory_capture_service() -> None:
    """Reset the default service, primarily for tests."""
    global _DEFAULT_CAPTURE_SERVICE
    _DEFAULT_CAPTURE_SERVICE = None

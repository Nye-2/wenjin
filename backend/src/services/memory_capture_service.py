"""Canonical ingress for long-term memory capture writes."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from src.agents.memory.capture import (
    messages_to_conversation_text,
)
from src.agents.memory.queue import MemoryQueue, get_default_memory_queue
from src.services.user_memory_service import extract_and_persist_knowledge

logger = logging.getLogger(__name__)


class MemoryCaptureService:
    """Single write boundary for long-term memory extraction.

    Thread and runtime call sites should submit memory capture through this
    service instead of calling extraction directly. In production, when Celery
    is enabled, capture is dispatched to the broker immediately so pending
    memory writes are not tied to the API process lifetime. Local/dev fallback
    keeps the existing debounced in-process queue behavior.
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
        """Capture a pre-filtered message batch for long-term memory."""
        if not user_id or not thread_id or not messages:
            return

        conversation_text = messages_to_conversation_text(
            messages,
            limit=self._resolve_capture_limit_messages(),
        )
        if not conversation_text:
            return

        payload = {
            "user_id": str(user_id),
            "workspace_id": str(workspace_id) if workspace_id else None,
            "conversation_text": conversation_text,
            "source": source or "thread",
        }
        if self._submit_celery_capture(payload):
            return

        self.enqueue_messages(
            thread_id=str(thread_id),
            user_id=str(user_id),
            workspace_id=str(workspace_id) if workspace_id else None,
            messages=list(messages),
            source=source,
        )

    def enqueue_messages(
        self,
        *,
        thread_id: str,
        user_id: str | None,
        workspace_id: str | None,
        messages: list[Any],
        source: str | None = None,
    ) -> None:
        """Debounced in-process fallback used when durable dispatch is disabled."""
        if not user_id or not thread_id:
            return

        async def _persist(_thread_id: str, queued_messages: list[Any]) -> None:
            conversation_text = messages_to_conversation_text(
                queued_messages,
                limit=self._resolve_capture_limit_messages(),
            )
            if not conversation_text:
                return
            await self.persist_conversation(
                user_id=str(user_id),
                conversation_text=conversation_text,
                workspace_context=workspace_id,
                source=source or "thread",
            )

        self._queue.enqueue(thread_id, list(messages), callback=_persist)

    async def persist_conversation(
        self,
        *,
        user_id: str | None,
        conversation_text: str,
        workspace_context: str | None = None,
        source: str | None = None,
    ) -> int:
        """Persist extracted memory from an already-built transcript."""
        if not user_id:
            return 0
        normalized_text = str(conversation_text or "").strip()
        if not normalized_text:
            return 0
        capture_source = self._capture_source(source or "memory", normalized_text)
        return await extract_and_persist_knowledge(
            str(user_id),
            normalized_text,
            workspace_context=workspace_context,
            source=capture_source,
        )

    @staticmethod
    def _resolve_capture_limit_messages() -> int:
        turns = 3
        try:
            from src.config.config_loader import get_app_config

            memory_config = getattr(get_app_config(), "memory", None)
            turns = int(getattr(memory_config, "max_context_turns", turns) or turns)
        except Exception:
            turns = 3

        turns = max(1, min(12, turns))
        return min(24, turns * 2)

    @staticmethod
    def _submit_celery_capture(payload: dict[str, Any]) -> bool:
        try:
            from src.config import celery_settings

            if not getattr(celery_settings, "enabled", False):
                return False

            from src.task.tasks.memory import capture_memory

            capture_memory.apply_async(args=[payload], queue="memory")
            return True
        except Exception:
            logger.warning(
                "Falling back to in-process memory capture queue after Celery dispatch failure",
                exc_info=True,
            )
            return False

    @staticmethod
    def _capture_source(source: str, conversation_text: str) -> str:
        digest = hashlib.sha256(
            str(conversation_text or "").encode("utf-8")
        ).hexdigest()[:12]
        normalized_source = str(source or "thread").strip() or "thread"
        max_source_len = 100 - len("#") - len(digest)
        return f"{normalized_source[:max_source_len]}#{digest}"


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

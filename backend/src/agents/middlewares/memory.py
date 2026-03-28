"""Memory middleware for the canonical DB-backed memory flow."""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.memory.capture import (
    enqueue_memory_capture,
    filter_messages_for_memory as _filter_messages_for_memory,
    messages_to_conversation_text,
)
from src.agents.memory.queue import MemoryQueue, get_default_memory_queue
from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.services.user_memory_service import (
    _parse_knowledge_json,
    build_memory_context,
    extract_and_persist_knowledge,
    format_knowledge_for_prompt,
    load_user_memory,
)

logger = logging.getLogger(__name__)


class MemoryMiddleware(Middleware):
    """Middleware for persisting conversation context to memory.

    This middleware captures Human-AI message pairs after model responses
    and enqueues them for asynchronous memory updates via the MemoryQueue.

    Attributes:
        queue: MemoryQueue instance for debounced memory updates
        enabled: Whether memory persistence is enabled
        min_messages: Minimum messages required to trigger memory update
    """

    def __init__(
        self,
        queue: MemoryQueue | None = None,
        enabled: bool = True,
        min_messages: int = 2,
        inject_enabled: bool = True,
        capture_enabled: bool = True,
        cache_ttl: float = 300.0,
        max_cache_size: int = 1000,
    ):
        """Initialize MemoryMiddleware.

        Args:
            queue: MemoryQueue instance for batching updates.
                   If None, the configured default queue will be used.
            enabled: Whether to enable memory persistence (default: True)
            min_messages: Minimum message count to trigger enqueue (default: 2)
            inject_enabled: Whether to inject long-term memory before model calls
            capture_enabled: Whether to capture turns back into long-term memory
            cache_ttl: Seconds before a cached memory context expires (default: 300)
            max_cache_size: Maximum number of entries in the memory cache (default: 1000)
        """
        self._queue = queue or get_default_memory_queue()
        self._enabled = enabled
        self._min_messages = min_messages
        self._inject_enabled = inject_enabled
        self._capture_enabled = capture_enabled
        self._cache_ttl = cache_ttl
        if max_cache_size < 1:
            raise ValueError(f"max_cache_size must be >= 1, got {max_cache_size}")
        self._max_cache_size = max_cache_size
        self._memory_cache: collections.OrderedDict[str, tuple[str, float]] = collections.OrderedDict()  # key → (context, cached_at)

    @property
    def queue(self) -> MemoryQueue:
        """Get the memory queue."""
        return self._queue

    @property
    def enabled(self) -> bool:
        """Check if memory persistence is enabled."""
        return self._enabled

    def _cache_key(self, user_id: str, workspace_id: str | None) -> str:
        return f"{user_id}:{workspace_id or ''}"

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Inject persistent user memory into the prompt state."""
        if not self._enabled or not self._inject_enabled:
            return {}

        if state.get("memory_context"):
            return {}

        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")
        if not user_id:
            return {}

        workspace_id = state.get("workspace_id") or configurable.get("workspace_id")

        cache_key = self._cache_key(str(user_id), str(workspace_id) if workspace_id else None)
        cached_context, cached_at = self._memory_cache.get(cache_key, ("", 0.0))
        if cached_context and time.monotonic() - cached_at < self._cache_ttl:
            self._memory_cache.move_to_end(cache_key)   # promote to MRU position
            return {"memory_context": cached_context}

        max_context_turns = 3
        try:
            from src.config.config_loader import get_app_config

            memory_config = getattr(get_app_config(), "memory", None)
            max_context_turns = max(
                1,
                int(getattr(memory_config, "max_context_turns", 3) or 3),
            )
        except Exception:
            logger.debug("Failed to load memory max_context_turns", exc_info=True)

        filtered_messages = _filter_messages_for_memory(list(state.get("messages", [])))
        conversation_context = messages_to_conversation_text(
            filtered_messages,
            limit=max_context_turns * 2,
        )
        try:
            memory_context = await asyncio.wait_for(
                build_memory_context(
                    str(user_id),
                    str(workspace_id) if workspace_id else None,
                    current_context=conversation_context or None,
                ),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "MemoryMiddleware: timed out loading memory context for user %s (5.0s)",
                user_id,
            )
            return {}
        if not memory_context:
            return {}
        if len(self._memory_cache) >= self._max_cache_size:
            self._memory_cache.popitem(last=False)
        self._memory_cache[cache_key] = (memory_context, time.monotonic())
        return {"memory_context": memory_context}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Called after the model generates a response.

        Filters conversation messages and enqueues them for memory updates.

        Args:
            state: Current thread state (contains messages)
            config: Runtime configuration (contains thread_id)

        Returns:
            Empty dict (no state modifications)
        """
        # Skip if disabled
        if not self._enabled or not self._capture_enabled:
            return {}

        # Get messages from state
        messages = state.get("messages", [])

        # Skip if conversation is too short
        if len(messages) < self._min_messages:
            return {}

        # Filter to only Human and AI messages (exclude tool messages, system, etc.)
        filtered_messages = _filter_messages_for_memory(messages)

        # Skip if no meaningful messages after filtering
        if len(filtered_messages) < self._min_messages:
            return {}

        # Get thread_id from config
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "default")
        user_id = configurable.get("user_id")
        workspace_id = configurable.get("workspace_id")

        enqueue_memory_capture(
            thread_id=str(thread_id),
            user_id=str(user_id) if user_id else None,
            workspace_id=str(workspace_id) if workspace_id else None,
            messages=filtered_messages,
            source="chat.middleware",
            queue=self._queue,
        )

        # Invalidate cache so the next request fetches fresh context
        cache_key = self._cache_key(
            str(user_id) if user_id else "",
            str(workspace_id) if workspace_id else None,
        )
        self._memory_cache.pop(cache_key, None)

        logger.debug(
            f"Enqueued {len(filtered_messages)} messages for memory update "
            f"(thread: {thread_id})"
        )

        return {}

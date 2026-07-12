"""Memory middleware for hidden workspace-bound memory injection."""

from __future__ import annotations

import asyncio
import collections
import hashlib
import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.memory.capture import (
    filter_messages_for_memory as _filter_messages_for_memory,
)
from src.agents.memory.capture import messages_to_conversation_text
from src.agents.memory.queue import MemoryQueue, get_default_memory_queue
from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.services.workspace_memory_service import build_workspace_memory_context

logger = logging.getLogger(__name__)

__all__ = [
    "MemoryMiddleware",
    "_filter_messages_for_memory",
    "messages_to_conversation_text",
]


class MemoryMiddleware(Middleware):
    """Middleware for injecting one hidden workspace memory document."""

    def __init__(
        self,
        queue: MemoryQueue | None = None,
        enabled: bool = True,
        min_messages: int = 2,
        inject_enabled: bool = True,
        capture_enabled: bool = True,
        cache_ttl: float = 300.0,
        max_cache_size: int = 1000,
        timeout: float = 5.0,
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
            timeout: Seconds to wait for memory context load before giving up (default: 5.0)
        """
        self._queue = queue or get_default_memory_queue()
        self._enabled = enabled
        self._min_messages = min_messages
        self._inject_enabled = inject_enabled
        self._capture_enabled = capture_enabled
        self._cache_ttl = cache_ttl
        self._timeout = timeout
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

    def _cache_key(self, workspace_id: str, current_context: str) -> str:
        if not current_context:
            return workspace_id
        context_hash = hashlib.sha256(current_context.encode("utf-8")).hexdigest()[:16]
        return f"{workspace_id}:{context_hash}"

    def _cache_set(self, key: str, value: str) -> None:
        """Store *value* under *key* in the LRU cache.

        If *key* already exists it is promoted to MRU position.  When the
        cache is at capacity the least-recently-used entry is evicted and a
        debug log is emitted for operational observability.
        """
        if key in self._memory_cache:
            self._memory_cache.move_to_end(key)
        elif len(self._memory_cache) >= self._max_cache_size:
            evicted_key, _ = self._memory_cache.popitem(last=False)
            logger.debug("Memory cache evicted key: %s", evicted_key)
        self._memory_cache[key] = (value, time.monotonic())

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Inject hidden workspace memory into the prompt state."""
        if not self._enabled or not self._inject_enabled:
            return {}

        if state.get("memory_context"):
            return {}

        configurable = config.get("configurable", {})
        workspace_id = state.get("workspace_id") or configurable.get("workspace_id")
        if not workspace_id:
            return {}

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
        objective = str(
            state.get("mission_objective")
            or configurable.get("mission_objective")
            or configurable.get("objective")
            or ""
        ).strip()
        review_context = "\n".join(
            part
            for part in (
                f"objective: {objective}" if objective else "",
                conversation_context,
            )
            if part
        )
        cache_key = self._cache_key(str(workspace_id), review_context)
        cached_context, cached_at = self._memory_cache.get(cache_key, ("", 0.0))
        if cached_context and time.monotonic() - cached_at < self._cache_ttl:
            self._memory_cache.move_to_end(cache_key)
            return {"memory_context": cached_context}

        try:
            memory_context = await asyncio.wait_for(
                build_workspace_memory_context(
                    str(workspace_id),
                    current_context=review_context or None,
                ),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.warning(
                "MemoryMiddleware: timed out loading workspace memory for workspace %s (%.1fs)",
                workspace_id,
                self._timeout,
            )
            return {}
        if not memory_context:
            return {}
        self._cache_set(cache_key, memory_context)
        return {"memory_context": memory_context}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Ordinary turns no longer auto-write workspace memory."""
        del state, config
        return {}

"""Memory middleware for persisting conversation context.

This middleware intercepts conversations and enqueues them for memory updates,
enabling persistent learning from user interactions.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.memory.queue import MemoryQueue
from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

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
    ):
        """Initialize MemoryMiddleware.

        Args:
            queue: MemoryQueue instance for batching updates.
                   If None, a new queue will be created.
            enabled: Whether to enable memory persistence (default: True)
            min_messages: Minimum message count to trigger enqueue (default: 2)
        """
        self._queue = queue or MemoryQueue()
        self._enabled = enabled
        self._min_messages = min_messages

    @property
    def queue(self) -> MemoryQueue:
        """Get the memory queue."""
        return self._queue

    @property
    def enabled(self) -> bool:
        """Check if memory persistence is enabled."""
        return self._enabled

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Called before the model processes messages.

        This middleware does not modify state before model processing.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict (no state modifications)
        """
        return {}

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
        if not self._enabled:
            return {}

        # Get messages from state
        messages = state.get("messages", [])

        # Skip if conversation is too short
        if len(messages) < self._min_messages:
            return {}

        # Filter to only Human and AI messages (exclude tool messages, system, etc.)
        filtered_messages = [
            msg for msg in messages
            if isinstance(msg, (HumanMessage, AIMessage))
        ]

        # Skip if no meaningful messages after filtering
        if len(filtered_messages) < self._min_messages:
            return {}

        # Get thread_id from config
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Enqueue for memory update
        self._queue.enqueue(thread_id, filtered_messages)

        logger.debug(
            f"Enqueued {len(filtered_messages)} messages for memory update "
            f"(thread: {thread_id})"
        )

        return {}

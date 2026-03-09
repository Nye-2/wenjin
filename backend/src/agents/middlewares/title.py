"""Title middleware - auto-generates thread title after first exchange."""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class TitleMiddleware(Middleware):
    """Generates a thread title from the first user message."""

    def __init__(self, max_words: int = 8, max_chars: int = 60):
        self._max_words = max_words
        self._max_chars = max_chars

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op before model."""
        return {}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        if state.get("title"):
            return {}

        messages = state.get("messages", [])
        # Need at least one human + one AI message
        has_human = any(isinstance(m, HumanMessage) for m in messages)
        has_ai = any(isinstance(m, AIMessage) for m in messages)
        if not (has_human and has_ai):
            return {}

        # Extract first human message for title
        first_human = next(m for m in messages if isinstance(m, HumanMessage))
        content = first_human.content if isinstance(first_human.content, str) else str(first_human.content)

        # Clean and truncate
        title = content.strip().replace("\n", " ")
        words = title.split()
        if len(words) > self._max_words:
            title = " ".join(words[: self._max_words]) + "..."
        if len(title) > self._max_chars:
            title = title[: self._max_chars - 3] + "..."

        return {"title": title}

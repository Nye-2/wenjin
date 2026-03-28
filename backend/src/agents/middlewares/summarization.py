"""Summarization middleware for token limit management."""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class SummarizationMiddleware(Middleware):
    """Summarizes conversation history when approaching token limits.

    This middleware monitors token usage and triggers summarization
    when the conversation exceeds the configured threshold.
    """

    def __init__(
        self,
        trigger_tokens: int = 80000,
        keep_messages: int = 10,
        model_name: str | None = None,
    ):
        """Initialize summarization middleware.

        Args:
            trigger_tokens: Token count threshold to trigger summarization
            keep_messages: Number of recent messages to keep after summarization
            model_name: Model to use for summarization (defaults to fast model)
        """
        self._trigger_tokens = trigger_tokens
        self._keep_messages = keep_messages
        self._model_name = model_name

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Check token count and summarize if needed."""
        messages = state.get("messages", [])
        if not messages:
            return {}

        token_count = self._count_tokens(messages)
        if token_count < self._trigger_tokens:
            return {}

        # Perform summarization
        summary = await self._summarize(messages[: -self._keep_messages])
        if not summary:
            return {}

        # Replace old messages with summary
        kept_messages = messages[-self._keep_messages :]
        summary_message = SystemMessage(
            content=f"<conversation_summary>\n{summary}\n</conversation_summary>"
        )

        return {"messages": [summary_message] + kept_messages}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op after model."""
        return {}

    def _count_tokens(self, messages: list) -> int:
        """Estimate token count using UTF-8 byte length.

        Heuristic: 3 bytes ≈ 1 token. This handles CJK content significantly
        better than the naive chars//4 approach (a single Chinese character is
        3 UTF-8 bytes and roughly 1 token, whereas chars//4 would give 0.25).
        """
        total_bytes = 0
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            total_bytes += len(content.encode("utf-8"))
        return total_bytes // 3

    async def _summarize(self, messages: list) -> str | None:
        """Generate a summary of the messages."""
        try:
            from src.models.factory import create_chat_model
            from src.models.router import route_model

            model_id = route_model(
                requested_model=self._model_name,
                preferred_categories=("utility", "gen", "tool"),
                allowed_categories=("utility", "gen", "tool"),
                require_tools=False,
            )
            model = create_chat_model(model_id)
        except Exception:
            return None

        # Format messages for summarization
        formatted = []
        for msg in messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            formatted.append(f"{role}: {content}")

        prompt = f"""Summarize the following conversation, preserving key information:
- Main topics discussed
- Decisions made
- Important context for continuing the conversation

Conversation:
{chr(10).join(formatted[-20:])}  # Last 20 messages

Summary:"""

        try:
            response = await model.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception:
            return None

"""Clarification middleware - intercepts ask_clarification tool calls."""

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class ClarificationMiddleware(Middleware):
    """Intercepts ask_clarification tool calls for human-in-the-loop interaction.

    MUST be the last middleware in the chain.
    """

    position = "last"

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
        messages = state.get("messages", [])
        if not messages:
            return {}

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return {}

        tool_calls = getattr(last_msg, "tool_calls", None) or []
        clarification_calls = [tc for tc in tool_calls if tc.get("name") == "ask_clarification"]

        if not clarification_calls:
            return {}

        # Signal that clarification is needed - the agent loop should interrupt
        return {"_clarification_requested": True, "messages": messages}

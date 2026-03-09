"""SubagentLimit middleware - enforces max concurrent task tool calls."""

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class SubagentLimitMiddleware(Middleware):
    """Truncates excess `task` tool calls from model response."""

    def __init__(self, max_concurrent: int = 3):
        self._max = max(1, min(max_concurrent, 4))  # Clamp to [1, 4]

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
        task_calls = [tc for tc in tool_calls if tc.get("name") == "task"]

        if len(task_calls) <= self._max:
            return {}

        # Keep first N task calls + all non-task calls
        kept_task_ids = {tc["id"] for tc in task_calls[: self._max]}
        filtered = [tc for tc in tool_calls if tc.get("name") != "task" or tc["id"] in kept_task_ids]

        updated = AIMessage(content=last_msg.content, tool_calls=filtered)
        return {"messages": messages[:-1] + [updated]}

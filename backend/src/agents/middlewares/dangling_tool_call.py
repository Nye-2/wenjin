"""DanglingToolCall middleware - patches missing ToolMessages for interrupted calls."""

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class DanglingToolCallMiddleware(Middleware):
    """Inserts synthetic ToolMessages for tool_calls that lack responses."""

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return {}

        # Collect all tool_call IDs and their responses
        pending_calls: dict[str, int] = {}  # call_id -> index of AIMessage
        responded_calls: set[str] = set()

        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage):
                for tc in getattr(msg, "tool_calls", None) or []:
                    call_id = tc.get("id")
                    if call_id:
                        pending_calls[call_id] = i
            elif isinstance(msg, ToolMessage):
                call_id = getattr(msg, "tool_call_id", None)
                if call_id:
                    responded_calls.add(call_id)

        dangling = set(pending_calls.keys()) - responded_calls
        if not dangling:
            return {}

        # Insert synthetic ToolMessages right after the AIMessage
        patched = list(messages)
        offset = 0
        for call_id in sorted(dangling, key=lambda c: pending_calls[c]):
            ai_idx = pending_calls[call_id] + offset
            synthetic = ToolMessage(
                content="[Tool call interrupted - no response received]",
                tool_call_id=call_id,
                status="error",
            )
            patched.insert(ai_idx + 1, synthetic)
            offset += 1

        return {"messages": patched}

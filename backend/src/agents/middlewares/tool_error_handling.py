"""Tool error handling middleware."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

_MISSING_TOOL_CALL_ID = "missing_tool_call_id"


class ToolErrorHandlingMiddleware(Middleware):
    """Convert tool exceptions into standardized error ToolMessage objects."""

    def __init__(self, *, max_detail_chars: int = 500):
        self._max_detail_chars = max(100, max_detail_chars)

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        return {}

    async def on_tool_error(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_args: dict[str, Any],
        error: Exception,
    ) -> ToolMessage:
        configurable = dict(config.get("configurable", {})) if isinstance(config, dict) else {}
        tool_call_id = str(configurable.get("tool_call_id") or _MISSING_TOOL_CALL_ID)

        detail = str(error).strip() or error.__class__.__name__
        if len(detail) > self._max_detail_chars:
            detail = detail[: self._max_detail_chars - 3] + "..."

        content = (
            f"Error: Tool '{tool_name}' failed with {error.__class__.__name__}: {detail}. "
            "Continue with available context, or choose an alternative tool."
        )
        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name=tool_name,
            status="error",
        )

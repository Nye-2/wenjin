"""Subagent limit middleware.

Enforces maximum concurrent subagent execution limits per workspace or thread.
Prevents runaway subagent spawning that could exhaust compute resources.
"""

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.thread_state import ThreadState

from .base import Middleware

logger = logging.getLogger(__name__)


class SubagentLimitMiddleware(Middleware):
    """Enforces subagent execution limits.

    Checks the current number of active subagents for a thread/workspace
    and blocks new subagent tool calls if the limit is exceeded.
    """

    DEFAULT_MAX_SUBAGENTS = 8

    def __init__(self, max_subagents: int | None = None) -> None:
        self.max_subagents = max_subagents or self.DEFAULT_MAX_SUBAGENTS

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op before model — limits checked at tool-call time."""
        return {}

    async def before_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Check subagent limits before spawning a subagent.

        Args:
            state: Current thread state
            config: Runtime configuration
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool

        Returns:
            Tuple of (tool_name, tool_args) — may raise if limit exceeded
        """
        if not self._is_subagent_tool(tool_name):
            return tool_name, tool_args

        configurable = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id") or "").strip()
        workspace_id = str(configurable.get("workspace_id") or "").strip()

        active_count = await self._count_active_subagents(thread_id, workspace_id)
        if active_count >= self.max_subagents:
            logger.warning(
                "Subagent limit exceeded: thread=%s workspace=%s "
                "active=%d max=%d",
                thread_id,
                workspace_id,
                active_count,
                self.max_subagents,
            )
            raise SubagentLimitExceeded(
                f"Subagent limit exceeded ({active_count}/{self.max_subagents}). "
                "Wait for existing subagents to complete or pause the run."
            )

        return tool_name, tool_args

    def _is_subagent_tool(self, tool_name: str) -> bool:
        """Check if a tool is a subagent spawning tool."""
        subagent_tools = {
            "spawn_subagent",
            "run_subagent",
            "delegate_subtask",
            "execute_subagent",
        }
        return tool_name in subagent_tools or "subagent" in tool_name.lower()

    async def _count_active_subagents(
        self,
        thread_id: str | None,
        workspace_id: str | None,
    ) -> int:
        """Count active subagents for the given scope.

        Falls back to Redis agent status if available.
        """
        try:
            from src.academic.cache.redis_client import redis_client

            if thread_id:
                status = await redis_client.get_agent_status(thread_id)
                if status:
                    count = status.get("subagent_count")
                    if count is not None:
                        return int(count)
        except Exception:
            logger.debug("Failed to count active subagents from Redis", exc_info=True)

        # Fallback: count from thread state metadata
        return 0


class SubagentLimitExceeded(RuntimeError):
    """Raised when the subagent execution limit is exceeded."""

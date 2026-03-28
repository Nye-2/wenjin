"""Base middleware interface."""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.thread_state import ThreadState


class Middleware(ABC):
    """Abstract base class for middlewares.

    Middlewares can intercept and modify state before/after model calls.
    """

    position: str | None = None  # "first", "last", or None

    @abstractmethod
    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Called before the model processes messages.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Updated state dict (partial update)
        """
        return state

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Called after the model generates a response.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Updated state dict (partial update)
        """
        return state

    async def before_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_args: dict,
    ) -> tuple[str, dict]:
        """Called before a tool is executed.

        Args:
            state: Current thread state
            config: Runtime configuration
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool

        Returns:
            Tuple of (tool_name, tool_args) - can modify either
        """
        return tool_name, tool_args

    async def after_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_result: Any,
    ) -> Any:
        """Called after a tool is executed.

        Args:
            state: Current thread state
            config: Runtime configuration
            tool_name: Name of the executed tool
            tool_result: Result from the tool

        Returns:
            Modified tool result
        """
        return tool_result

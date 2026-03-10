"""Todo list middleware for plan mode task management."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class TodoListMiddleware(Middleware):
    """Middleware that manages todo list injection for plan mode.

    This middleware:
    1. Checks if plan_mode is enabled in config
    2. Injects todos into state when plan_mode is active
    3. Provides methods to update and query the todo list
    """

    def __init__(self) -> None:
        """Initialize the middleware with an empty todo list."""
        self._todos: list[dict[str, Any]] = []

    @property
    def todos(self) -> list[dict[str, Any]]:
        """Get the current todo list."""
        return self._todos

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Inject todos into state when plan_mode is enabled.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Dict with todos if plan_mode is enabled, empty dict otherwise
        """
        configurable = config.get("configurable", {})
        is_plan_mode = configurable.get("is_plan_mode", False)

        if not is_plan_mode:
            return {}

        return {"todos": self._todos}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op after model processing.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Empty dict (no state modifications needed)
        """
        return {}

    def update_todos(self, todos: list[dict[str, Any]]) -> None:
        """Update the todo list.

        Args:
            todos: New list of todos to store
        """
        self._todos = todos

    def get_next_todo(self) -> dict[str, Any] | None:
        """Get the next incomplete todo from the list.

        Returns:
            The first todo with completed=False, or None if all are completed
        """
        for todo in self._todos:
            if not todo.get("completed", False):
                return todo
        return None

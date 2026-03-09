"""Workspace context middleware for loading workspace configuration."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class WorkspaceContextMiddleware(Middleware):
    """Middleware that loads and injects workspace context.

    This middleware:
    1. Checks if workspace_id is present in state
    2. Loads workspace configuration from database
    3. Injects workspace type, discipline, and config into state
    """

    def __init__(self, workspace_service):
        """Initialize with workspace service.

        Args:
            workspace_service: Service for workspace CRUD operations
        """
        self.workspace_service = workspace_service

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Load workspace context and inject into state."""
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        workspace = await self.workspace_service.get(workspace_id)
        if not workspace:
            return dict(state)

        return {
            **state,
            "workspace_type": workspace.type,
            "discipline": workspace.discipline,
            "workspace_config": workspace.config,
        }

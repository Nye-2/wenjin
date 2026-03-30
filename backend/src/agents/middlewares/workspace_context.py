"""Workspace context middleware for loading workspace configuration."""

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class WorkspaceContextMiddleware(Middleware):
    """Middleware that loads and injects workspace context.

    This middleware:
    1. Checks if workspace_id is present in state
    2. Loads workspace configuration from database
    3. Injects workspace type, discipline, and config into state
    """

    def __init__(self, workspace_service, timeout: float = 5.0):
        """Initialize with workspace service.

        Args:
            workspace_service: Service for workspace CRUD operations
            timeout: Seconds to wait for the service call before giving up
        """
        self.workspace_service = workspace_service
        self._timeout = timeout

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Load workspace context and inject into state."""
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        try:
            workspace = await asyncio.wait_for(
                self.workspace_service.get(workspace_id),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "WorkspaceContextMiddleware: timed out loading workspace %s (%.1fs)",
                workspace_id,
                self._timeout,
            )
            return {}
        if not workspace:
            return dict(state)

        # Load active template for this workspace
        template_dict = None
        try:
            from src.services.template_service import TemplateService
            from src.database import get_db_session
            async with get_db_session() as template_db:
                ts = TemplateService(template_db)
                active_template = await ts.get_active(workspace_id)
                if active_template:
                    template_dict = {
                        "name": active_template.name,
                        "structure": active_template.structure,
                        "format_spec": active_template.format_spec,
                        "content_guidelines": active_template.content_guidelines,
                    }
        except Exception:
            logger.warning("Failed to load workspace template, skipping")

        return {
            **state,
            "workspace_type": workspace.type,
            "discipline": workspace.discipline,
            "workspace_config": workspace.config,
            "template_context": template_dict,
        }

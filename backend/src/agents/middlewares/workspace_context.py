"""Workspace context middleware for loading workspace configuration."""

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.services.template_service import TemplateService

logger = logging.getLogger(__name__)

class WorkspaceContextMiddleware(Middleware):
    """Middleware that loads and injects workspace context.

    This middleware:
    1. Checks if workspace_id is present in state
    2. Loads workspace configuration from DataService-backed services
    3. Injects workspace type, discipline, and config into state
    """

    def __init__(
        self,
        workspace_service: Any,
        timeout: float = 5.0,
        template_service: Any | None = None,
    ) -> None:
        """Initialize with workspace service.

        Args:
            workspace_service: Service for workspace CRUD operations
            timeout: Seconds to wait for the service call before giving up
        """
        self.workspace_service = workspace_service
        self.template_service = template_service or TemplateService()
        self._timeout = timeout

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Load workspace context and inject into state."""
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return {}

        try:
            workspace = await asyncio.wait_for(
                self.workspace_service.get(workspace_id),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.warning(
                "WorkspaceContextMiddleware: timed out loading workspace %s (%.1fs)",
                workspace_id,
                self._timeout,
            )
            return {}
        if not workspace:
            return {}

        # Load active template for this workspace
        template_dict = None
        try:
            active_template = await asyncio.wait_for(
                self.template_service.get_active(workspace_id),
                timeout=self._timeout,
            )
            if active_template:
                template_dict = {
                    "name": active_template.name,
                    "structure": active_template.structure,
                    "format_spec": active_template.format_spec,
                    "content_guidelines": active_template.content_guidelines,
                }
        except TimeoutError:
            logger.warning(
                "WorkspaceContextMiddleware: timed out loading active template for workspace %s (%.1fs)",
                workspace_id,
                self._timeout,
            )
        except Exception:
            logger.warning("Failed to load workspace template, skipping")

        return {
            "workspace_type": workspace.type,
            "discipline": workspace.discipline,
            "workspace_config": workspace.config,
            "template_context": template_dict,
        }

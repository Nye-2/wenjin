"""Literature context middleware for index-based TOC navigation."""

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class LiteratureContextMiddleware(Middleware):
    """Middleware that provides index-based literature context.

    This middleware provides TOC-based navigation context for agents:
    1. Extracts workspace_id from state
    2. Gets formatted TOC summary from IndexService
    3. Injects literature_context into state for agent use

    Unlike RAG-based retrieval, this approach gives agents a high-level
    overview of available literature structure, allowing them to make
    informed decisions about what to read.

    If no workspace_id is present, the middleware skips loading context.
    """

    def __init__(self, index_service, timeout: float = 5.0):
        """Initialize with index service.

        Args:
            index_service: Service for index-based literature navigation
                          (IndexService instance)
            timeout: Seconds to wait for the service call before giving up
        """
        self.index_service = index_service
        self._timeout = timeout

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Retrieve literature TOC context and inject into state.

        This method:
        1. Checks if workspace_id exists in state
        2. Gets formatted TOC summary for the workspace
        3. Injects context into state as literature_context

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Updated state dict with literature_context if workspace_id exists
        """
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return {}

        # Get TOC summary for workspace
        try:
            toc_summary = await asyncio.wait_for(
                self.index_service.get_workspace_toc_summary(workspace_id),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.warning(
                "LiteratureContextMiddleware: timed out loading TOC for workspace %s (%.1fs)",
                workspace_id,
                self._timeout,
            )
            return {}

        # Only inject if we have content
        if not toc_summary:
            return {}

        return {
            "literature_context": toc_summary,
        }

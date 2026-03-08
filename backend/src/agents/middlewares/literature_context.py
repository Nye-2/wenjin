"""Literature context middleware for index-based TOC navigation."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class LiteratureContextMiddleware(Middleware):
    """Middleware that provides index-based literature context.

    This middleware provides TOC-based navigation context for agents:
    1. Extracts workspace_id from state
    2. Gets formatted TOC summary from IndexService
    3. Injects _literature_context into state for agent use

    Unlike RAG-based retrieval, this approach gives agents a high-level
    overview of available literature structure, allowing them to make
    informed decisions about what to read.

    If no workspace_id is present, the middleware skips loading context.
    """

    def __init__(self, index_service):
        """Initialize with index service.

        Args:
            index_service: Service for index-based literature navigation
                          (IndexService instance)
        """
        self.index_service = index_service

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Retrieve literature TOC context and inject into state.

        This method:
        1. Checks if workspace_id exists in state
        2. Gets formatted TOC summary for the workspace
        3. Injects context into state as _literature_context

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Updated state dict with _literature_context if workspace_id exists
        """
        workspace_id = state.workspace_id
        if not workspace_id:
            return state.model_dump()

        # Get TOC summary for workspace
        toc_summary = await self.index_service.get_workspace_toc_summary(workspace_id)

        # Only inject if we have content
        if not toc_summary:
            return state.model_dump()

        return {
            **state.model_dump(),
            "_literature_context": toc_summary,
        }

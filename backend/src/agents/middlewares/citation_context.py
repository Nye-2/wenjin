"""Citation context middleware for tracking and validating reference citations."""

import logging
import re
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class CitationContextMiddleware(Middleware):
    """Middleware that tracks and validates citations in AI responses.

    This middleware:
    1. Extracts citations from AI responses
    2. Validates citations against workspace references
    3. Updates cited_references in state
    """

    # Patterns for citation extraction
    CITATION_PATTERNS = [
        r"\(([^)]+),\s*(\d{4})\)",  # (Author, Year)
        r"\[(\d+)\]",  # [1]
        r"\(([^)]+)\s+et\s+al\.?,\s*(\d{4})\)",  # (Author et al., Year)
        r"doi:(10\.[^\s]+)",  # doi:10.xxx
    ]

    def __init__(self, reference_service):
        """Initialize with reference service.

        Args:
            reference_service: Service for reference-library operations
        """
        self.reference_service = reference_service

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op before model - citation tracking happens after model.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Unchanged state dict
        """
        return dict(state)

    def _extract_citations(self, content: str) -> list[str]:
        """Extract citation identifiers from content."""
        citations = []

        for pattern in self.CITATION_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    citations.append(" ".join(match))
                else:
                    citations.append(match)

        unique = list(set(citations))
        if unique:
            logger.debug("Extracted %d citation(s) from response", len(unique))
        return unique

    async def _validate_citations(self, citations: list[str], workspace_id: str) -> list[str]:
        """Validate citations against workspace references.

        Returns list of valid reference IDs.
        """
        valid_reference_ids = []

        for citation in citations:
            # Try to find reference by DOI, citation key, title, or author/year.
            references = await self.reference_service.search_in_workspace(
                workspace_id=workspace_id,
                query=citation,
            )
            if references:
                valid_reference_ids.append(str(references[0].id))

        return list(set(valid_reference_ids))

    async def _record_reference_usage(
        self,
        *,
        workspace_id: str,
        reference_ids: list[str],
        content: str,
        state: ThreadState,
        config: RunnableConfig,
    ) -> None:
        if not reference_ids or self.reference_service is None:
            return
        recorder = getattr(self.reference_service, "record_reference_usage", None)
        if recorder is None:
            return
        configurable = config.get("configurable", {}) if isinstance(config, Mapping) else {}
        if not isinstance(configurable, Mapping):
            configurable = {}
        try:
            await recorder(
                workspace_id=workspace_id,
                reference_ids=reference_ids,
                execution_session_id=(
                    state.get("execution_session_id")
                    or configurable.get("execution_session_id")
                    or None
                ),
                task_id=state.get("task_id") or configurable.get("task_id") or None,
                artifact_id=state.get("artifact_id") or configurable.get("artifact_id") or None,
                target_section=state.get("current_skill") or configurable.get("skill_id") or None,
                generated_text=content[:4000],
            )
        except Exception:
            logger.warning(
                "Failed to record reference usage for workspace %s",
                workspace_id,
                exc_info=True,
            )

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Extract and validate citations from AI response."""
        workspace_id = state.get("workspace_id")
        if not workspace_id:
            return dict(state)

        messages = list(state.get("messages", []))
        if not messages:
            return dict(state)

        # Get last AI message
        last_message = messages[-1]
        if not hasattr(last_message, "type") or last_message.type != "ai":
            return dict(state)

        content = last_message.content
        if not isinstance(content, str):
            content = str(content)

        # Extract citations
        citations = self._extract_citations(content)
        if not citations:
            return dict(state)

        # Validate citations
        valid_reference_ids = await self._validate_citations(citations, workspace_id)
        await self._record_reference_usage(
            workspace_id=workspace_id,
            reference_ids=valid_reference_ids,
            content=content,
            state=state,
            config=config,
        )

        # Update state
        existing_cited = list(state.get("cited_references", []))
        new_cited = list(dict.fromkeys(existing_cited + valid_reference_ids))

        return {
            **state,
            "cited_references": new_cited,
        }

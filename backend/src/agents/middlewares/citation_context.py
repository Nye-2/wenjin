"""Citation context middleware for tracking and validating reference citations."""

import logging
import re
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.dataservice.source_api import SourceCitationUsageCreateCommand


class CitationContextMiddleware(Middleware):
    """Middleware that tracks and validates citations in AI responses.

    This middleware:
    1. Extracts citations from AI responses
    2. Validates citations against workspace references
    3. Updates cited_references in state
    """

    # Patterns for citation extraction
    CITATION_PATTERNS = [
        r"\\cite\w*\{([^}]+)\}",  # \cite{key1,key2}
        r"\(([^)]+),\s*(\d{4})\)",  # (Author, Year)
        r"\[(\d+)\]",  # [1]
        r"\(([^)]+)\s+et\s+al\.?,\s*(\d{4})\)",  # (Author et al., Year)
        r"doi:(10\.[^\s]+)",  # doi:10.xxx
    ]

    def __init__(self, reference_service: Any) -> None:
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
                    citations.extend(item.strip() for item in str(match).split(",") if item.strip())

        unique = list(set(citations))
        if unique:
            logger.debug("Extracted %d citation(s) from response", len(unique))
        return unique

    async def _validate_citations(self, citations: list[str], workspace_id: str) -> list[str]:
        """Validate citations against workspace references.

        Returns list of valid reference IDs.
        """
        valid_source_ids = []

        if self.reference_service is None:
            return []
        list_sources = getattr(self.reference_service, "list_sources", None)
        if not callable(list_sources):
            return []
        for citation in citations:
            sources = await list_sources(
                workspace_id=workspace_id,
                query=citation,
                include_excluded=False,
                limit=1,
            )
            if sources:
                valid_source_ids.append(str(sources[0].id))

        return list(set(valid_source_ids))

    async def _record_source_usage(
        self,
        *,
        workspace_id: str,
        source_ids: list[str],
        citation_keys: list[str],
        content: str,
        state: ThreadState,
        config: RunnableConfig,
    ) -> None:
        if not source_ids or self.reference_service is None:
            return
        source_recorder = getattr(self.reference_service, "record_citation_usage", None)
        if source_recorder is None:
            return
        configurable = config.get("configurable", {}) if isinstance(config, Mapping) else {}
        if not isinstance(configurable, Mapping):
            configurable = {}
        try:
            await source_recorder(
                SourceCitationUsageCreateCommand(
                    workspace_id=workspace_id,
                    citation_keys=citation_keys,
                    execution_id=(
                        state.get("execution_id")
                        or configurable.get("execution_id")
                        or None
                    ),
                    task_id=state.get("task_id") or configurable.get("task_id") or None,
                    artifact_id=state.get("artifact_id") or configurable.get("artifact_id") or None,
                    target_section=state.get("current_skill") or configurable.get("skill_id") or None,
                    generated_text=content[:4000],
                )
            )
        except Exception:
            logger.warning(
                "Failed to record Source citation usage for workspace %s",
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
        valid_source_ids = await self._validate_citations(citations, workspace_id)
        await self._record_source_usage(
            workspace_id=workspace_id,
            source_ids=valid_source_ids,
            citation_keys=citations,
            content=content,
            state=state,
            config=config,
        )

        # Update state
        existing_cited = list(state.get("cited_references", []))
        new_cited = list(dict.fromkeys(existing_cited + valid_source_ids))

        return {
            **state,
            "cited_references": new_cited,
        }

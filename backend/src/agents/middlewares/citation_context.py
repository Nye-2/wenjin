"""Citation context middleware for tracking and validating citations."""

import re
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class CitationContextMiddleware(Middleware):
    """Middleware that tracks and validates citations in AI responses.

    This middleware:
    1. Extracts citations from AI responses
    2. Validates citations against workspace papers
    3. Updates cited_papers in state
    """

    # Patterns for citation extraction
    CITATION_PATTERNS = [
        r"\(([^)]+),\s*(\d{4})\)",  # (Author, Year)
        r"\[(\d+)\]",  # [1]
        r"\(([^)]+)\s+et\s+al\.?,\s*(\d{4})\)",  # (Author et al., Year)
        r"doi:(10\.[^\s]+)",  # doi:10.xxx
    ]

    def __init__(self, paper_service):
        """Initialize with paper service.

        Args:
            paper_service: Service for paper operations
        """
        self.paper_service = paper_service

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
        return state.model_dump()

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

        return list(set(citations))

    async def _validate_citations(self, citations: list[str], workspace_id: str) -> list[str]:
        """Validate citations against workspace papers.

        Returns list of valid paper IDs.
        """
        valid_paper_ids = []

        for citation in citations:
            # Try to find paper by DOI or author/year
            papers = await self.paper_service.search_in_workspace(
                workspace_id=workspace_id,
                query=citation,
            )
            if papers:
                valid_paper_ids.append(papers[0].id)

        return list(set(valid_paper_ids))

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Extract and validate citations from AI response."""
        workspace_id = state.workspace_id
        if not workspace_id:
            return state.model_dump()

        messages = list(state.messages)
        if not messages:
            return state.model_dump()

        # Get last AI message
        last_message = messages[-1]
        if not hasattr(last_message, "type") or last_message.type != "ai":
            return state.model_dump()

        content = last_message.content
        if not isinstance(content, str):
            content = str(content)

        # Extract citations
        citations = self._extract_citations(content)
        if not citations:
            return state.model_dump()

        # Validate citations
        valid_paper_ids = await self._validate_citations(citations, workspace_id)

        # Update state
        existing_cited = list(state.cited_papers)
        new_cited = list(set(existing_cited + valid_paper_ids))

        return {
            **state.model_dump(),
            "cited_papers": new_cited,
        }

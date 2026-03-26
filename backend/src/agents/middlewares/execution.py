"""Execution middleware for handling execution tools."""

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.citation.bibtex.exporter import BibTeXExporter
from src.agents.thread_state import ThreadState
from src.database.models.paper import Paper
from src.execution.types import (
    ExecutionRequest,
    ExecutionType,
)

from .base import Middleware

logger = logging.getLogger(__name__)


class ExecutionMiddleware(Middleware):
    """Middleware for handling execution tool calls.

    Intercepts execution tool calls and routes them through
    the ExecutionService for Docker-based or API-based execution.
    """

    # Mapping of tool names to execution types
    EXECUTION_TOOLS = {
        "compile_latex_tool": ExecutionType.LATEX_COMPILE,
        # More tools added in later phases:
        # "plot_chart_tool": ExecutionType.PYTHON_PLOT,
        # "create_diagram_tool": ExecutionType.MERMAID_DIAGRAM,
        # "generate_image_tool": ExecutionType.AI_IMAGE,
    }

    def __init__(self, execution_service: Any, *, paper_service: Any | None = None):
        """Initialize middleware.

        Args:
            execution_service: ExecutionService instance.
            paper_service: Optional PaperService for citation bibliography lookup.
        """
        self.execution_service = execution_service
        self.paper_service = paper_service

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op before model.

        Args:
            state: Current thread state.
            config: Runtime configuration.

        Returns:
            Empty dict (no state changes).
        """
        return {}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """No-op after model.

        Args:
            state: Current thread state.
            config: Runtime configuration.

        Returns:
            Empty dict (no state changes).
        """
        return {}

    async def before_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_args: dict,
    ) -> tuple[str, dict]:
        """Process tool before execution.

        Args:
            state: Current thread state
            config: Runtime configuration
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool

        Returns:
            Tuple of (tool_name, tool_args) - can modify either
        """
        if tool_name not in self.EXECUTION_TOOLS:
            return tool_name, tool_args  # Not an execution tool, continue normally

        # Get execution type
        exec_type = self.EXECUTION_TOOLS[tool_name]

        # Extract context
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        workspace_id = configurable.get("workspace_id")

        # Handle citation_ids: generate bibliography if needed
        citation_ids = tool_args.get("citation_ids")
        explicit_bib = tool_args.get("bibliography")

        if citation_ids and not explicit_bib:
            db: AsyncSession | None = configurable.get("db")
            if db is None and self.paper_service is not None:
                db = getattr(self.paper_service, "db", None)
            if db:
                bibliography = await self._generate_bibliography(db, citation_ids)
                if bibliography:
                    tool_args = {**tool_args, "bibliography": bibliography}
                    logger.info(f"Generated bibliography for {len(citation_ids)} citations")
            else:
                try:
                    from src.database import get_db_session

                    async with get_db_session() as session:
                        bibliography = await self._generate_bibliography(session, citation_ids)
                    if bibliography:
                        tool_args = {**tool_args, "bibliography": bibliography}
                        logger.info(
                            "Generated bibliography for %s citations via ad-hoc session",
                            len(citation_ids),
                        )
                except Exception:
                    logger.debug(
                        "Failed to resolve ad-hoc DB session for bibliography generation",
                        exc_info=True,
                    )

        # Build execution request
        request = self._build_request(
            exec_type=exec_type,
            tool_args=tool_args,
            thread_id=thread_id,
            workspace_id=workspace_id,
        )

        # Execute
        result = await self.execution_service.execute(request)

        # Store result for after_tool
        configurable["execution_result"] = result

        return tool_name, tool_args

    async def after_tool(
        self,
        state: ThreadState,
        config: RunnableConfig,
        tool_name: str,
        tool_result: Any,
    ) -> Any:
        """Process tool output after execution.

        Args:
            state: Current thread state
            config: Runtime configuration
            tool_name: Name of the executed tool
            tool_result: Result from the tool

        Returns:
            Modified tool result
        """
        if tool_name not in self.EXECUTION_TOOLS:
            return tool_result

        configurable = config.get("configurable", {})
        result = configurable.pop("execution_result", None)
        if result:
            return result.to_tool_output()

        return tool_result

    async def _generate_bibliography(
        self,
        db: AsyncSession,
        citation_ids: list[str],
    ) -> str | None:
        """Generate BibTeX content from citation IDs.

        Args:
            db: Database session.
            citation_ids: List of paper IDs.

        Returns:
            BibTeX formatted string or None if no papers found.
        """
        if not citation_ids:
            return None

        try:
            # Fetch papers
            result = await db.execute(
                select(Paper).where(Paper.id.in_(citation_ids))
            )
            papers = result.scalars().all()

            if not papers:
                logger.warning(f"No papers found for citation_ids: {citation_ids}")
                return None

            # Convert to dicts for exporter
            paper_dicts = [
                {
                    "title": p.title,
                    "authors": p.authors,
                    "year": p.year,
                    "venue": p.venue,
                    "doi": p.doi,
                    "abstract": p.abstract,
                }
                for p in papers
            ]

            # Generate BibTeX
            exporter = BibTeXExporter()
            return exporter.export(paper_dicts)

        except Exception as e:
            logger.error(f"Failed to generate bibliography: {e}")
            return None

    def _build_request(
        self,
        exec_type: ExecutionType,
        tool_args: dict,
        thread_id: str | None,
        workspace_id: str | None,
    ) -> ExecutionRequest:
        """Build execution request from tool arguments.

        Args:
            exec_type: Execution type.
            tool_args: Tool arguments.
            thread_id: Thread ID.
            workspace_id: Workspace ID.

        Returns:
            ExecutionRequest instance.
        """
        if exec_type == ExecutionType.LATEX_COMPILE:
            return ExecutionRequest(
                execution_type=exec_type,
                content=tool_args.get("latex_source", ""),
                options={
                    "compiler": tool_args.get("compiler", "xelatex"),
                    "bibliography": tool_args.get("bibliography"),
                    "bibliography_style": tool_args.get("bibliography_style", "plain"),
                },
                timeout=tool_args.get("timeout", 120),
                thread_id=thread_id,
                workspace_id=workspace_id,
            )

        # Other execution types will be added here
        raise ValueError(f"Unsupported execution type: {exec_type}")

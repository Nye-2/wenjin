"""Skill-based task handler for the async task system.

This module provides the bridge between the Async Task System and the Skill
execution framework, allowing skills to be executed as async tasks with
progress tracking.
"""

import asyncio
import logging
from typing import Any, Callable

from src.skills.base import SkillInput, SkillOutput
from src.skills.executor import SkillExecutor, SkillNotFoundError
from src.task.progress import ProgressTracker
from src.task.registry import TaskStatus

logger = logging.getLogger(__name__)


class SkillTaskHandler:
    """Handles task execution by dispatching to registered skills.

    This class bridges the async task system with the skill execution framework.
    It maps task types to skill names and provides progress-aware execution.

    Mapping Convention:
        Task Type          → Skill Name
        ─────────────────────────────────
        deep_research      → deep-research
        thesis_generation  → thesis-generation
        literature_search  → literature-search
        paper_processing   → paper-processing

    Usage:
        handler = SkillTaskHandler(executor)
        result = await handler.execute_skill(
            task_type="deep_research",
            payload={"query": "AI in healthcare", "workspace_id": "..."},
            progress=progress_tracker
        )
    """

    # Mapping from task_type to skill_name
    TASK_TO_SKILL_MAP = {
        "deep_research": "deep-research",
        "thesis_generation": "thesis-generation",
        "literature_search": "literature-search",
        "paper_processing": "paper-processing",
    }

    def __init__(self, skill_executor: SkillExecutor | None = None):
        """Initialize the handler.

        Args:
            skill_executor: Optional SkillExecutor instance. If None, a new
                           one will be created and skills will be auto-loaded.
        """
        self._executor = skill_executor or SkillExecutor()
        self._skills_loaded = False

    def _ensure_skills_loaded(self) -> None:
        """Ensure skills are loaded into the executor."""
        if self._skills_loaded:
            return

        # Auto-discover and register skills
        self._load_skills()
        self._skills_loaded = True

    def _load_skills(self) -> None:
        """Load and register all available skills."""
        try:
            # Import and register skill implementations
            from src.skills.implementations.deep_research import DeepResearchSkillV2
            from src.skills.implementations.literature_review import LiteratureReviewSkill
            from src.skills.implementations.framework_designer import FrameworkDesignerSkill
            from src.skills.implementations.fullpaper_writer import FullPaperWriterSkill

            # Register skills
            self._executor.register_skill(DeepResearchSkillV2())
            self._executor.register_skill(LiteratureReviewSkill())
            self._executor.register_skill(FrameworkDesignerSkill())
            self._executor.register_skill(FullPaperWriterSkill())

            logger.info(f"Loaded {len(self._executor._skills)} skills: {self._executor.list_skills()}")

        except ImportError as e:
            logger.warning(f"Could not load some skills: {e}")

    def get_skill_name(self, task_type: str) -> str | None:
        """Get the skill name for a task type.

        Args:
            task_type: The task type from TASK_REGISTRY.

        Returns:
            The corresponding skill name, or None if not mapped.
        """
        return self.TASK_TO_SKILL_MAP.get(task_type)

    def register_skill_mapping(self, task_type: str, skill_name: str) -> None:
        """Register a custom task type to skill name mapping.

        Args:
            task_type: The task type identifier.
            skill_name: The corresponding skill name.
        """
        self.TASK_TO_SKILL_MAP[task_type] = skill_name

    async def execute_skill(
        self,
        task_type: str,
        payload: dict[str, Any],
        progress: ProgressTracker,
    ) -> dict[str, Any]:
        """Execute a skill as an async task.

        This method:
        1. Maps task_type to skill_name
        2. Creates SkillInput from payload
        3. Executes the skill with progress tracking
        4. Returns the result as a dict

        Args:
            task_type: The type of task (must be in TASK_TO_SKILL_MAP).
            payload: Task payload containing:
                - workspace_id: Required workspace context
                - query: User's query/request
                - context: Additional context data
            progress: ProgressTracker for reporting progress.

        Returns:
            Dict containing:
                - success: bool
                - content: str (main output)
                - artifacts: list (produced artifacts)
                - metadata: dict (execution metadata)

        Raises:
            ValueError: If task_type is not mapped or required fields missing.
            SkillNotFoundError: If the skill is not registered.
        """
        self._ensure_skills_loaded()

        # Get skill name
        skill_name = self.get_skill_name(task_type)
        if not skill_name:
            raise ValueError(f"No skill mapping for task type: {task_type}")

        # Check if skill is registered
        if not self._executor.has_skill(skill_name):
            raise SkillNotFoundError(skill_name)

        # Extract required fields from payload
        workspace_id = payload.get("workspace_id", "default-workspace")
        user_query = payload.get("query") or payload.get("user_query", "")
        context = payload.get("context", {})

        # Merge additional payload fields into context
        for key in ["search_limit", "year_range", "options", "paper_ids"]:
            if key in payload:
                context[key] = payload[key]

        # Create skill input
        skill_input = SkillInput(
            workspace_id=workspace_id,
            user_query=user_query,
            context=context,
        )

        # Report progress: starting
        await progress.update(5, f"Initializing {skill_name}...")

        # Create a minimal thread state for skill execution
        state: dict[str, Any] = {
            "workspace_id": workspace_id,
            "cited_papers": [],
            "artifacts": [],
        }

        # Execute skill with progress wrapper
        try:
            await progress.update(10, f"Executing {skill_name}...")

            # Run skill execution in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            output: SkillOutput = await loop.run_in_executor(
                None,
                self._executor.execute,
                skill_name,
                skill_input,
                state,
            )

            # Report completion
            if output.success:
                await progress.update(90, "Processing results...")
                await progress.complete(output.content[:200] if output.content else "Task completed")
            else:
                await progress.fail(output.error_message or "Skill execution failed")

            # Return result
            return {
                "success": output.success,
                "content": output.content,
                "artifacts": [
                    {
                        "id": a.id if hasattr(a, "id") else str(i),
                        "type": a.type if hasattr(a, "type") else "unknown",
                        "content": a.content if hasattr(a, "content") else {},
                    }
                    for i, a in enumerate(output.artifacts)
                ],
                "metadata": output.metadata,
                "error": output.error_message,
            }

        except SkillNotFoundError as e:
            await progress.fail(f"Skill not found: {e.skill_name}")
            raise
        except Exception as e:
            logger.exception(f"Skill execution failed: {e}")
            await progress.fail(str(e))
            raise

    async def execute_skill_with_progress_callback(
        self,
        task_type: str,
        payload: dict[str, Any],
        progress: ProgressTracker,
        progress_callback: Callable | None = None,
    ) -> dict[str, Any]:
        """Execute a skill with custom progress callback support.

        This method is for skills that support progress callbacks,
        allowing more granular progress reporting.

        Args:
            task_type: The type of task.
            payload: Task payload.
            progress: ProgressTracker for reporting.
            progress_callback: Optional callback(skill_name, phase, percent, message).

        Returns:
            Execution result dict.
        """
        # For now, delegate to execute_skill
        # Skills can be enhanced to call progress_callback internally
        return await self.execute_skill(task_type, payload, progress)


# Global handler instance (lazy-initialized)
_handler_instance: SkillTaskHandler | None = None


def get_skill_task_handler() -> SkillTaskHandler:
    """Get the global SkillTaskHandler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = SkillTaskHandler()
    return _handler_instance

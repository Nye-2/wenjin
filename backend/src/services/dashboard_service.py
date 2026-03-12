"""Dashboard service for workspace overview.

This service provides dashboard overview functionality including:
- Module status aggregation
- Recent artifacts listing
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, TaskRecord, WorkspaceLiterature


class DashboardService:
    """Service for workspace dashboard overview.

    This class aggregates data from multiple sources to provide
    a comprehensive dashboard view of workspace progress.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize DashboardService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def get_dashboard(self, workspace_id: str) -> dict[str, Any]:
        """Get dashboard overview for a workspace.

        Aggregates status from multiple modules and returns recent artifacts.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Dictionary with modules status list and recent artifacts
        """
        # Get status for each module
        modules = [
            await self._get_deep_research_status(workspace_id),
            await self._get_literature_status(workspace_id),
            await self._get_opening_research_status(workspace_id),
            await self._get_thesis_writing_status(workspace_id),
            await self._get_figure_generation_status(workspace_id),
            await self._get_compile_export_status(workspace_id),
        ]

        # Get recent artifacts
        recent_artifacts = await self._get_recent_artifacts(workspace_id)

        return {
            "modules": modules,
            "recent_artifacts": recent_artifacts,
        }

    async def _get_deep_research_status(self, workspace_id: str) -> dict[str, Any]:
        """Get deep research module status.

        Status is determined by checking for completed deep_research tasks.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Module status dictionary
        """
        # Check for completed deep research tasks
        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "deep_research")
            .where(TaskRecord.status == "completed")
        )
        completed_tasks = result.scalars().all()

        # Check for in-progress tasks
        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "deep_research")
            .where(TaskRecord.status == "running")
        )
        running_tasks = result.scalars().all()

        if running_tasks:
            status = "in_progress"
        elif completed_tasks:
            status = "completed"
        else:
            status = "not_started"

        return {
            "id": "deep_research",
            "status": status,
            "summary": {},
        }

    async def _get_literature_status(self, workspace_id: str) -> dict[str, Any]:
        """Get literature module status.

        Status is determined by counting literature entries.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Module status dictionary
        """
        # Get total count
        total_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceLiterature.workspace_id == workspace_id
            )
        )
        total = total_result.scalar() or 0

        # Get core count
        core_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceLiterature.workspace_id == workspace_id,
                WorkspaceLiterature.is_core == True,  # noqa: E712
            )
        )
        core = core_result.scalar() or 0

        # Determine status
        if total > 0:
            status = "completed" if core >= 5 else "in_progress"
        else:
            status = "not_started"

        return {
            "id": "literature",
            "status": status,
            "summary": {"total": total, "core": core},
        }

    async def _get_opening_research_status(self, workspace_id: str) -> dict[str, Any]:
        """Get opening research module status.

        Status is determined by checking for opening_research artifacts.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Module status dictionary
        """
        # Check for opening research artifacts
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == "opening_research")
        )
        artifacts = result.scalars().all()

        if artifacts:
            status = "completed"
        else:
            # Check for in-progress tasks
            task_result = await self.db.execute(
                select(TaskRecord)
                .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
                .where(TaskRecord.task_type == "opening_research")
                .where(TaskRecord.status == "running")
            )
            running_tasks = task_result.scalars().all()
            status = "in_progress" if running_tasks else "not_started"

        return {
            "id": "opening_research",
            "status": status,
            "summary": {},
        }

    async def _get_thesis_writing_status(self, workspace_id: str) -> dict[str, Any]:
        """Get thesis writing module status.

        Status is determined by checking for thesis outline and chapters.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Module status dictionary
        """
        # Check for outline artifact
        outline_result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == "thesis_outline")
        )
        outline_artifact = outline_result.scalar_one_or_none()
        outline_done = outline_artifact is not None

        # Check for chapter artifacts
        chapters_result = await self.db.execute(
            select(func.count())
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == "thesis_chapter")
        )
        chapters_count = chapters_result.scalar() or 0

        if chapters_count > 0:
            status = "completed" if chapters_count >= 3 else "in_progress"
        elif outline_done:
            status = "in_progress"
        else:
            status = "not_started"

        return {
            "id": "thesis_writing",
            "status": status,
            "summary": {"outline_done": outline_done, "chapters": chapters_count},
        }

    async def _get_figure_generation_status(self, workspace_id: str) -> dict[str, Any]:
        """Get figure generation module status.

        Status is determined by counting figure artifacts.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Module status dictionary
        """
        # Check for figure artifacts
        result = await self.db.execute(
            select(func.count())
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == "figure")
        )
        count = result.scalar() or 0

        # Determine status
        if count > 0:
            status = "completed" if count >= 3 else "in_progress"
        else:
            status = "not_started"

        return {
            "id": "figure_generation",
            "status": status,
            "summary": {"count": count},
        }

    async def _get_compile_export_status(self, workspace_id: str) -> dict[str, Any]:
        """Get compile/export module status.

        Status is determined by checking for compiled PDF artifacts.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Module status dictionary
        """
        # Check for compiled PDF artifacts
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == "compiled_pdf")
        )
        artifacts = result.scalars().all()

        if artifacts:
            status = "completed"
        else:
            status = "not_started"

        return {
            "id": "compile_export",
            "status": status,
            "summary": {},
        }

    async def _get_recent_artifacts(
        self, workspace_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get recent artifacts for a workspace.

        Args:
            workspace_id: UUID of the workspace
            limit: Maximum number of artifacts to return

        Returns:
            List of recent artifacts with id, type, title, and created_at
        """
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .order_by(Artifact.created_at.desc())
            .limit(limit)
        )
        artifacts = result.scalars().all()

        return [
            {
                "id": str(artifact.id),
                "type": artifact.type,
                "title": artifact.title or "",
                "created_at": artifact.created_at.isoformat()
                if artifact.created_at
                else "",
            }
            for artifact in artifacts
        ]


async def get_dashboard_service() -> DashboardService:
    """Get DashboardService instance for dependency injection.

    This is a placeholder that will be overridden in the router.
    The actual implementation requires a database session.

    Returns:
        DashboardService instance
    """
    raise NotImplementedError("This should be overridden via dependency_overrides")

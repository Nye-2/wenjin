"""Dashboard service for workspace overview.

This service provides workspace-specific module aggregation and recent artifacts.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.types import ArtifactType
from src.database import Artifact, TaskRecord, Workspace, WorkspaceLiterature


class DashboardService:
    """Service for workspace dashboard overview."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(
        self,
        workspace_id: str,
        workspace_type: str | None = None,
    ) -> dict[str, Any]:
        """Get dashboard overview for a workspace.

        Args:
            workspace_id: UUID of the workspace
            workspace_type: Optional workspace type override (mainly for tests)

        Returns:
            Dictionary with modules status list and recent artifacts
        """
        resolved_workspace_type = workspace_type or await self._get_workspace_type(
            workspace_id
        )

        modules = await self._get_modules_for_workspace(
            workspace_id,
            resolved_workspace_type,
        )
        recent_artifacts = await self._get_recent_artifacts(workspace_id)

        return {
            "modules": modules,
            "recent_artifacts": recent_artifacts,
        }

    async def _get_workspace_type(self, workspace_id: str) -> str:
        """Resolve workspace type from DB with thesis as safe fallback."""
        result = await self.db.execute(
            select(Workspace.type).where(Workspace.id == workspace_id)
        )
        workspace_type = result.scalar_one_or_none()
        if workspace_type is None:
            return "thesis"
        return (
            workspace_type.value
            if hasattr(workspace_type, "value")
            else str(workspace_type)
        )

    async def _get_modules_for_workspace(
        self,
        workspace_id: str,
        workspace_type: str,
    ) -> list[dict[str, Any]]:
        """Build workspace-specific dashboard modules."""
        if workspace_type == "sci":
            return [
                await self._get_sci_literature_search_status(workspace_id),
                await self._get_sci_paper_analysis_status(workspace_id),
                await self._get_sci_writing_status(workspace_id),
            ]

        if workspace_type == "proposal":
            return [
                await self._get_proposal_outline_status(workspace_id),
                await self._get_background_research_status(workspace_id),
            ]

        if workspace_type == "software_copyright":
            return [
                await self._get_software_copyright_materials_status(workspace_id),
                await self._get_technical_description_status(workspace_id),
            ]

        if workspace_type == "patent":
            return [
                await self._get_patent_outline_status(workspace_id),
                await self._get_prior_art_search_status(workspace_id),
            ]

        return [
            await self._get_deep_research_status(workspace_id),
            await self._get_literature_status(workspace_id),
            await self._get_opening_research_status(workspace_id),
            await self._get_thesis_writing_status(workspace_id),
            await self._get_figure_generation_status(workspace_id),
            await self._get_compile_export_status(workspace_id),
        ]

    async def _count_artifacts(
        self,
        workspace_id: str,
        artifact_type: str,
        *,
        created_by_skill: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == artifact_type)
        )
        if created_by_skill:
            stmt = stmt.where(Artifact.created_by_skill == created_by_skill)
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def _count_running_workspace_feature_tasks(
        self,
        workspace_id: str,
        feature_id: str,
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "workspace_feature")
            .where(TaskRecord.payload["feature_id"].as_string() == feature_id)
            .where(TaskRecord.status.in_(["pending", "running"]))
        )
        return int(result.scalar() or 0)

    async def _get_latest_workspace_feature_task_status(
        self,
        workspace_id: str,
        feature_id: str,
    ) -> str | None:
        result = await self.db.execute(
            select(TaskRecord.status)
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "workspace_feature")
            .where(TaskRecord.payload["feature_id"].as_string() == feature_id)
            .order_by(TaskRecord.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _status_from_count_and_running(
        self,
        *,
        count: int,
        running_count: int,
        latest_task_status: str | None = None,
    ) -> str:
        if running_count > 0:
            return "in_progress"
        if count > 0:
            return "completed"
        if latest_task_status == "failed":
            return "failed"
        return "not_started"

    async def _get_deep_research_status(self, workspace_id: str) -> dict[str, Any]:
        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "deep_research")
            .where(TaskRecord.status == "success")
        )
        completed_tasks = result.scalars().all()

        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "deep_research")
            .where(TaskRecord.status == "running")
        )
        running_tasks = result.scalars().all()

        ideas_result = await self.db.execute(
            select(func.count())
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == ArtifactType.RESEARCH_IDEAS.value)
        )
        ideas_count = ideas_result.scalar() or 0

        latest_task_result = await self.db.execute(
            select(TaskRecord.status)
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
            .where(TaskRecord.task_type == "deep_research")
            .order_by(TaskRecord.created_at.desc())
            .limit(1)
        )
        latest_task_status = latest_task_result.scalar_one_or_none()

        if running_tasks:
            status = "in_progress"
        elif completed_tasks:
            status = "completed"
        elif latest_task_status == "failed":
            status = "failed"
        else:
            status = "not_started"

        return {
            "id": "deep_research",
            "status": status,
            "summary": {"ideas_count": ideas_count, "last_task_status": latest_task_status},
        }

    async def _get_literature_status(self, workspace_id: str) -> dict[str, Any]:
        total_result = await self.db.execute(
            select(func.count()).where(WorkspaceLiterature.workspace_id == workspace_id)
        )
        total = total_result.scalar() or 0

        core_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceLiterature.workspace_id == workspace_id,
                WorkspaceLiterature.is_core == True,  # noqa: E712
            )
        )
        core = core_result.scalar() or 0

        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "literature_management",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "literature_management",
        )

        if running_count > 0:
            status = "in_progress"
        elif total > 0:
            status = "completed" if core >= 5 else "in_progress"
        elif latest_task_status == "failed":
            status = "failed"
        else:
            status = "not_started"

        return {
            "id": "literature_management",
            "status": status,
            "summary": {"total": total, "core": core, "last_task_status": latest_task_status},
        }

    async def _get_opening_research_status(self, workspace_id: str) -> dict[str, Any]:
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.created_by_skill == "thesis.opening_research")
            .where(
                Artifact.type.in_(
                    [
                        ArtifactType.OPENING_REPORT.value,
                        ArtifactType.LITERATURE_REVIEW.value,
                        ArtifactType.FEASIBILITY_ANALYSIS.value,
                    ]
                )
            )
        )
        artifacts = result.scalars().all()

        if artifacts:
            status = "completed"
        else:
            running_count = await self._count_running_workspace_feature_tasks(
                workspace_id,
                "opening_research",
            )
            latest_task_status = await self._get_latest_workspace_feature_task_status(
                workspace_id,
                "opening_research",
            )
            if running_count > 0:
                status = "in_progress"
            elif latest_task_status == "failed":
                status = "failed"
            else:
                status = "not_started"

        return {
            "id": "opening_research",
            "status": status,
            "summary": {"reports_count": len(artifacts)},
        }

    async def _get_thesis_writing_status(self, workspace_id: str) -> dict[str, Any]:
        outline_result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == ArtifactType.FRAMEWORK_OUTLINE.value)
        )
        outline_artifact = outline_result.scalar_one_or_none()
        outline_done = outline_artifact is not None

        chapters_result = await self.db.execute(
            select(func.count())
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == ArtifactType.THESIS_CHAPTER.value)
        )
        chapters_count = int(chapters_result.scalar() or 0)

        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "thesis_writing",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "thesis_writing",
        )

        if running_count > 0:
            status = "in_progress"
        elif chapters_count > 0:
            status = "completed" if chapters_count >= 3 else "in_progress"
        elif outline_done:
            status = "in_progress"
        elif latest_task_status == "failed":
            status = "failed"
        else:
            status = "not_started"

        return {
            "id": "thesis_writing",
            "status": status,
            "summary": {
                "outline_done": outline_done,
                "chapters": chapters_count,
                "last_task_status": latest_task_status,
            },
        }

    async def _get_figure_generation_status(self, workspace_id: str) -> dict[str, Any]:
        count = await self._count_artifacts(
            workspace_id,
            ArtifactType.FIGURE.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "figure_generation",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "figure_generation",
        )

        if running_count > 0:
            status = "in_progress"
        elif count > 0:
            status = "completed" if count >= 3 else "in_progress"
        elif latest_task_status == "failed":
            status = "failed"
        else:
            status = "not_started"

        return {
            "id": "figure_generation",
            "status": status,
            "summary": {"figures_count": count, "last_task_status": latest_task_status},
        }

    async def _get_compile_export_status(self, workspace_id: str) -> dict[str, Any]:
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "compile_export",
        )
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(Artifact.type == ArtifactType.PAPER_DRAFT.value)
            .where(Artifact.created_by_skill == "thesis.compile_export")
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )
        latest_artifact = result.scalar_one_or_none()

        if latest_artifact is None:
            if running_count > 0:
                return {
                    "id": "compile_export",
                    "status": "in_progress",
                    "summary": {
                        "last_compile": None,
                        "compile_status": None,
                        "last_compile_success": False,
                    },
                }
            status = "not_started"
            last_compile = None
            compile_status = None
        else:
            content = (
                latest_artifact.content
                if isinstance(latest_artifact.content, dict)
                else {}
            )
            compile_status = str(content.get("compile_status") or "unknown")
            last_compile = (
                latest_artifact.created_at.isoformat()
                if getattr(latest_artifact, "created_at", None)
                else ""
            )
            if running_count > 0:
                status = "in_progress"
            elif compile_status == "success":
                status = "completed"
            elif compile_status == "failed":
                status = "failed"
            else:
                status = "in_progress"

        return {
            "id": "compile_export",
            "status": status,
            "summary": {
                "last_compile": last_compile,
                "compile_status": compile_status,
                "last_compile_success": compile_status == "success",
            },
        }

    async def _get_sci_literature_search_status(self, workspace_id: str) -> dict[str, Any]:
        results_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.LITERATURE_SEARCH_RESULTS.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "literature_search",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "literature_search",
        )

        status = await self._status_from_count_and_running(
            count=results_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "literature_search",
            "status": status,
            "summary": {
                "results_count": results_count,
                "last_task_status": latest_task_status,
            },
        }

    async def _get_sci_paper_analysis_status(self, workspace_id: str) -> dict[str, Any]:
        analysis_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PAPER_ANALYSIS.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "paper_analysis",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "paper_analysis",
        )

        status = await self._status_from_count_and_running(
            count=analysis_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "paper_analysis",
            "status": status,
            "summary": {
                "analysis_count": analysis_count,
            },
        }

    async def _get_sci_writing_status(self, workspace_id: str) -> dict[str, Any]:
        draft_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PAPER_DRAFT.value,
            created_by_skill="sci.writing",
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "writing",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "writing",
        )
        status = await self._status_from_count_and_running(
            count=draft_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "writing",
            "status": status,
            "summary": {
                "drafts_count": draft_count,
            },
        }

    async def _get_proposal_outline_status(self, workspace_id: str) -> dict[str, Any]:
        outline_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PROPOSAL.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "proposal_outline",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "proposal_outline",
        )
        status = await self._status_from_count_and_running(
            count=outline_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "proposal_outline",
            "status": status,
            "summary": {
                "has_outline": outline_count > 0,
                "count": outline_count,
            },
        }

    async def _get_background_research_status(self, workspace_id: str) -> dict[str, Any]:
        report_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.BACKGROUND_RESEARCH.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "background_research",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "background_research",
        )
        status = await self._status_from_count_and_running(
            count=report_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "background_research",
            "status": status,
            "summary": {
                "count": report_count,
            },
        }

    async def _get_software_copyright_materials_status(
        self,
        workspace_id: str,
    ) -> dict[str, Any]:
        materials_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.COPYRIGHT_MATERIALS.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "copyright_materials",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "copyright_materials",
        )
        status = await self._status_from_count_and_running(
            count=materials_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "copyright_materials",
            "status": status,
            "summary": {
                "has_materials": materials_count > 0,
                "count": materials_count,
            },
        }

    async def _get_technical_description_status(
        self,
        workspace_id: str,
    ) -> dict[str, Any]:
        description_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.TECHNICAL_DESCRIPTION.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "technical_description",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "technical_description",
        )
        status = await self._status_from_count_and_running(
            count=description_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "technical_description",
            "status": status,
            "summary": {
                "has_description": description_count > 0,
                "count": description_count,
            },
        }

    async def _get_patent_outline_status(self, workspace_id: str) -> dict[str, Any]:
        outline_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PATENT_OUTLINE.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "patent_outline",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "patent_outline",
        )
        status = await self._status_from_count_and_running(
            count=outline_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "patent_outline",
            "status": status,
            "summary": {
                "has_outline": outline_count > 0,
                "count": outline_count,
            },
        }

    async def _get_prior_art_search_status(self, workspace_id: str) -> dict[str, Any]:
        report_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.PRIOR_ART_REPORT.value,
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "prior_art_search",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "prior_art_search",
        )
        status = await self._status_from_count_and_running(
            count=report_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "prior_art_search",
            "status": status,
            "summary": {
                "reports_count": report_count,
            },
        }

    async def _get_recent_artifacts(
        self,
        workspace_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
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
                "created_at": artifact.created_at.isoformat() if artifact.created_at else "",
            }
            for artifact in artifacts
        ]

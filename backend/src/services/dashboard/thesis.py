"""Dashboard status builders for thesis workspaces."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from src.artifacts.types import ArtifactType
from src.database import Artifact, ReferenceLibraryStatus, WorkspaceReference
from src.services.dashboard.shared import DashboardStatusSharedMixin


class DashboardThesisStatusMixin(DashboardStatusSharedMixin):
    """Feature status builders for thesis workspace modules."""

    db: Any

    @staticmethod
    def _creator_ids(feature_id: str) -> tuple[str, ...]:
        return ()

    async def _get_deep_research_status(self, workspace_id: str) -> dict[str, Any]:
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "deep_research",
        )

        latest_report = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.DEEP_RESEARCH_REPORT.value,
        )
        latest_report_content = (
            latest_report.content
            if latest_report and isinstance(latest_report.content, dict)
            else {}
        )
        latest_ideas = latest_report_content.get("ideas")
        reports_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.DEEP_RESEARCH_REPORT.value,
        )
        ideas_count = len(latest_ideas) if isinstance(latest_ideas, list) else 0

        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "deep_research",
        )
        status = await self._status_from_count_and_running(
            count=reports_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )

        return {
            "id": "deep_research",
            "status": status,
            "summary": {
                "reports_count": reports_count,
                "ideas_count": ideas_count,
                "last_task_status": latest_task_status,
            },
        }

    async def _get_literature_management_status(self, workspace_id: str) -> dict[str, Any]:
        total_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status != ReferenceLibraryStatus.EXCLUDED,
            )
        )
        total = total_result.scalar() or 0

        core_result = await self.db.execute(
            select(func.count()).where(
                WorkspaceReference.workspace_id == workspace_id,
                WorkspaceReference.is_deleted.is_(False),
                WorkspaceReference.library_status == ReferenceLibraryStatus.CORE,
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
            "summary": {
                "total": total,
                "core": core,
                "last_task_status": latest_task_status,
            },
        }

    async def _get_opening_research_status(self, workspace_id: str) -> dict[str, Any]:
        creator_ids = self._creator_ids("opening_research")
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .where(
                Artifact.type.in_(
                    [
                        ArtifactType.OPENING_REPORT.value,
                        ArtifactType.LITERATURE_REVIEW.value,
                        ArtifactType.FEASIBILITY_ANALYSIS.value,
                    ]
                )
            )
            .where(Artifact.created_by_skill.in_(creator_ids))
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
            "summary": {
                "figures_count": count,
                "last_task_status": latest_task_status,
            },
        }

"""Dashboard status builders for thesis workspaces."""

from __future__ import annotations

from typing import Any

from src.artifacts.types import ArtifactType
from src.dataservice.source_api import SourceDataService
from src.services.dashboard.shared import DashboardStatusSharedMixin


class DashboardThesisStatusMixin(DashboardStatusSharedMixin):
    """Feature status builders for thesis workspace modules."""

    db: Any

    @staticmethod
    def _creator_ids(feature_id: str) -> tuple[str, ...]:
        return ()

    async def _get_deep_research_status(self, workspace_id: str) -> dict[str, Any]:
        running_count = await self._count_running_feature_executions(
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

        latest_task_status = await self._get_latest_feature_execution_status(
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
        source_service = SourceDataService(self.db, autocommit=False)
        total = await source_service.count_sources(
            workspace_id=workspace_id,
            include_deleted=False,
            include_excluded=False,
        )

        core = await source_service.count_sources(
            workspace_id=workspace_id,
            library_status="core",
            include_deleted=False,
        )

        running_count = await self._count_running_feature_executions(
            workspace_id,
            "literature_management",
        )
        latest_task_status = await self._get_latest_feature_execution_status(
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
        artifacts = await self._list_artifacts(
            workspace_id,
            artifact_types=[
                ArtifactType.OPENING_REPORT.value,
                ArtifactType.LITERATURE_REVIEW.value,
                ArtifactType.FEASIBILITY_ANALYSIS.value,
            ],
            created_by_skills=creator_ids,
        )

        if artifacts:
            status = "completed"
        else:
            running_count = await self._count_running_feature_executions(
                workspace_id,
                "opening_research",
            )
            latest_task_status = await self._get_latest_feature_execution_status(
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
        outline_artifact = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.FRAMEWORK_OUTLINE.value,
        )
        outline_done = outline_artifact is not None

        chapters_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.THESIS_CHAPTER.value,
        )

        running_count = await self._count_running_feature_executions(
            workspace_id,
            "thesis_writing",
        )
        latest_task_status = await self._get_latest_feature_execution_status(
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
        running_count = await self._count_running_feature_executions(
            workspace_id,
            "figure_generation",
        )
        latest_task_status = await self._get_latest_feature_execution_status(
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

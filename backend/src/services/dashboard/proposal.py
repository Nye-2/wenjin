"""Dashboard status builders for proposal workspaces."""

from __future__ import annotations

from typing import Any

from src.artifacts.types import ArtifactType
from src.services.dashboard.shared import DashboardStatusSharedMixin


class DashboardProposalStatusMixin(DashboardStatusSharedMixin):
    """Feature status builders for proposal workspace modules."""

    db: Any

    @staticmethod
    def _creator_ids(feature_id: str) -> tuple[str, ...]:
        return ()

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

    async def _get_experiment_design_status(self, workspace_id: str) -> dict[str, Any]:
        design_count = await self._count_artifacts(
            workspace_id,
            ArtifactType.METHODOLOGY.value,
            created_by_skills=self._creator_ids("experiment_design"),
        )
        latest_artifact = await self._get_latest_artifact(
            workspace_id,
            ArtifactType.METHODOLOGY.value,
            created_by_skills=self._creator_ids("experiment_design"),
        )
        running_count = await self._count_running_workspace_feature_tasks(
            workspace_id,
            "experiment_design",
        )
        latest_task_status = await self._get_latest_workspace_feature_task_status(
            workspace_id,
            "experiment_design",
        )
        status = await self._status_from_count_and_running(
            count=design_count,
            running_count=running_count,
            latest_task_status=latest_task_status,
        )
        content = (
            latest_artifact.content
            if latest_artifact and isinstance(latest_artifact.content, dict)
            else {}
        )
        hypotheses = content.get("hypotheses")
        variables = content.get("variables")
        return {
            "id": "experiment_design",
            "status": status,
            "summary": {
                "count": design_count,
                "hypotheses_count": len(hypotheses) if isinstance(hypotheses, list) else 0,
                "variables_count": len(variables) if isinstance(variables, list) else 0,
            },
        }

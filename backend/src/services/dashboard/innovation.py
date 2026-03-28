"""Dashboard status builders for software copyright and patent workspaces."""

from __future__ import annotations

from typing import Any

from src.artifacts.types import ArtifactType
from src.services.dashboard.shared import DashboardStatusSharedMixin


class DashboardInnovationStatusMixin(DashboardStatusSharedMixin):
    """Feature status builders for IP-oriented workspace modules."""

    db: Any

    async def _get_copyright_materials_status(
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

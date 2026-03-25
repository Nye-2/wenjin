"""Dashboard service for workspace overview."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, Workspace
from src.services.dashboard import (
    DashboardInnovationStatusMixin,
    DashboardProposalStatusMixin,
    DashboardSciStatusMixin,
    DashboardStatusSharedMixin,
    DashboardThesisStatusMixin,
)
from src.workspace_features import list_workspace_features


class DashboardService(
    DashboardStatusSharedMixin,
    DashboardThesisStatusMixin,
    DashboardSciStatusMixin,
    DashboardProposalStatusMixin,
    DashboardInnovationStatusMixin,
):
    """Service for workspace dashboard overview."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(
        self,
        workspace_id: str,
        workspace_type: str | None = None,
    ) -> dict[str, Any]:
        """Get dashboard overview for a workspace."""
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
        """Build workspace dashboard modules in canonical registry order."""
        modules: list[dict[str, Any]] = []
        for feature in list_workspace_features(workspace_type):
            method_name = f"_get_{feature.id}_status"
            if not hasattr(self, method_name):
                raise RuntimeError(
                    f"No dashboard status builder registered for feature '{feature.id}'"
                )
            modules.append(await getattr(self, method_name)(workspace_id))
        return modules

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

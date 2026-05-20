"""Dashboard service for workspace overview."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, Workspace
from src.dataservice.catalog_api import CatalogDataService
from src.services.dashboard import (
    DashboardInnovationStatusMixin,
    DashboardProposalStatusMixin,
    DashboardSciStatusMixin,
    DashboardThesisStatusMixin,
)


class DashboardService(
    DashboardThesisStatusMixin,
    DashboardSciStatusMixin,
    DashboardProposalStatusMixin,
    DashboardInnovationStatusMixin,
):
    """Service for workspace dashboard overview."""

    def __init__(self, db: AsyncSession, *, capability_model: type | None = None):
        self.db = db
        self._capability_model = capability_model

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
        """Resolve workspace type from DB without guessing a fallback type."""
        result = await self.db.execute(
            select(Workspace.type).where(Workspace.id == workspace_id)
        )
        workspace_type = result.scalar_one_or_none()
        if workspace_type is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
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
        """Build workspace dashboard modules from the capabilities DB table.

        Capabilities are ordered by ``ui_meta.order`` (ascending), with capability
        ``id`` as a stable tie-breaker. Dispatch uses ``dashboard_meta.status_kind``
        when present, falling back to ``capability.id``.
        """
        if self._capability_model is not None:
            capability_model = self._capability_model
            result = await self.db.execute(
                select(capability_model)
                .where(capability_model.workspace_type == workspace_type)
                .where(capability_model.enabled == True)  # noqa: E712
            )
            raw_capabilities = result.scalars().all()
        else:
            raw_capabilities = await CatalogDataService(self.db, autocommit=False).list_capabilities(
                workspace_type=workspace_type,
                enabled_only=True,
            )
        capabilities = sorted(raw_capabilities, key=lambda c: ((c.ui_meta or {}).get("order", 0), c.id))

        modules: list[dict[str, Any]] = []
        for cap in capabilities:
            status_kind = (cap.dashboard_meta or {}).get("status_kind", cap.id)
            # Skip capabilities marked hidden or with no status_kind
            if not status_kind or (cap.dashboard_meta or {}).get("hidden") is True:
                continue
            method_name = f"_get_{status_kind}_status"
            if not hasattr(self, method_name):
                raise RuntimeError(
                    f"No dashboard status builder for status_kind '{status_kind}' "
                    f"(capability {cap.id})"
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

"""Dashboard service for workspace overview."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client
from src.services.dashboard import DashboardStatusSharedMixin


class DashboardService(DashboardStatusSharedMixin):
    """Service for workspace dashboard overview."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self.db = db
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def _list_catalog_capabilities(
        self,
        *,
        workspace_type: str,
        enabled_only: bool,
    ) -> list[Any]:
        async with self._client() as client:
            return await client.list_catalog_capabilities(
                workspace_type=workspace_type,
                enabled_only=enabled_only,
            )

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
        """Resolve workspace type from DataService without guessing a fallback type."""
        async with self._client() as client:
            workspace = await client.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        workspace_type = workspace.type
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
        ``id`` as a stable tie-breaker. Dashboard status is derived generically
        from mission execution history so capability ids remain catalog-owned.
        """
        raw_capabilities = await self._list_catalog_capabilities(
            workspace_type=workspace_type,
            enabled_only=True,
        )
        capabilities = sorted(raw_capabilities, key=lambda c: ((c.ui_meta or {}).get("order", 0), c.id))

        modules: list[dict[str, Any]] = []
        for cap in capabilities:
            if (cap.dashboard_meta or {}).get("hidden") is True:
                continue
            modules.append(await self._get_catalog_capability_status(workspace_id, cap))
        return modules

    async def _get_catalog_capability_status(
        self,
        workspace_id: str,
        capability: Any,
    ) -> dict[str, Any]:
        running_count = await self._count_running_feature_executions(
            workspace_id,
            capability.id,
        )
        latest_task_status = await self._get_latest_feature_execution_status(
            workspace_id,
            capability.id,
        )

        if running_count > 0:
            status = "in_progress"
        elif latest_task_status in {"completed", "succeeded", "success"}:
            status = "completed"
        elif latest_task_status == "failed":
            status = "failed"
        else:
            status = "not_started"

        raw_definition = getattr(capability, "definition_json", None)
        definition = raw_definition if isinstance(raw_definition, dict) else {}
        mission = definition.get("mission") if isinstance(definition.get("mission"), dict) else {}
        return {
            "id": capability.id,
            "status": status,
            "summary": {
                "display_name": capability.display_name,
                "entry_tier": (capability.ui_meta or {}).get("entry_tier"),
                "primary_surface": mission.get("primary_surface"),
                "document_role": mission.get("document_role"),
                "running_count": running_count,
                "last_task_status": latest_task_status,
            },
        }

    async def _get_recent_artifacts(
        self,
        workspace_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        async with self._client() as client:
            artifacts = await client.list_workspace_artifacts(
                workspace_id=workspace_id,
                limit=limit,
            )

        return [
            {
                "id": str(artifact.id),
                "type": artifact.type,
                "title": artifact.title or "",
                "created_at": artifact.created_at.isoformat() if artifact.created_at else "",
            }
            for artifact in artifacts
        ]

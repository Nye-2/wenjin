"""Workspace, template, and room API mixin for AsyncDataServiceClient."""

from __future__ import annotations

from typing import Any

from src.dataservice_client.contracts.rooms import (
    DecisionPayload,
    DecisionSetPayload,
    RoomCandidateApplyPayload,
    RoomCandidatePayload,
    WorkspaceTaskCreatePayload,
    WorkspaceTaskPayload,
    WorkspaceTaskUpdatePayload,
)
from src.dataservice_client.contracts.template import (
    WorkspaceTemplateCreatePayload,
    WorkspaceTemplateDeactivatePayload,
    WorkspaceTemplatePayload,
)
from src.dataservice_client.contracts.workspace import (
    WorkspaceAdminStatsPayload,
    WorkspaceCreatePayload,
    WorkspacePayload,
    WorkspaceSettingsPayload,
    WorkspaceSettingsUpdatePayload,
    WorkspaceStatsPayload,
    WorkspaceUpdatePayload,
)


class WorkspaceDataServiceClientMixin:
    """Typed DataService methods for workspace, templates, and rooms."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_workspace_template(
        self,
        template_id: str,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request("GET", f"/internal/v1/templates/{template_id}")
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def get_active_workspace_template(
        self,
        workspace_id: str,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request("GET", f"/internal/v1/templates/workspaces/{workspace_id}/active")
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def list_workspace_templates(
        self,
        workspace_id: str,
    ) -> list[WorkspaceTemplatePayload]:
        payload = await self._request("GET", f"/internal/v1/templates/workspaces/{workspace_id}")
        return [WorkspaceTemplatePayload.model_validate(item) for item in payload["data"]]

    async def create_workspace_template(
        self,
        command: WorkspaceTemplateCreatePayload,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/templates",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def deactivate_active_workspace_templates(
        self,
        workspace_id: str,
        command: WorkspaceTemplateDeactivatePayload | None = None,
    ) -> bool:
        payload = await self._request(
            "POST",
            f"/internal/v1/templates/workspaces/{workspace_id}/deactivate-active",
            json=(command or WorkspaceTemplateDeactivatePayload()).model_dump(mode="json"),
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deactivated")) if isinstance(data, dict) else False

    async def activate_workspace_template(
        self,
        *,
        workspace_id: str,
        template_id: str,
    ) -> WorkspaceTemplatePayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/templates/workspaces/{workspace_id}/{template_id}/activate",
        )
        data = payload.get("data")
        return WorkspaceTemplatePayload.model_validate(data) if data is not None else None

    async def delete_workspace_template(
        self,
        template_id: str,
        *,
        workspace_id: str | None = None,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/templates/{template_id}",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def list_room_decisions(self, workspace_id: str) -> list[DecisionPayload]:
        payload = await self._request("GET", f"/internal/v1/rooms/workspaces/{workspace_id}/decisions")
        return [DecisionPayload.model_validate(item) for item in payload["data"]]

    async def set_room_decision(self, command: DecisionSetPayload) -> DecisionPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/rooms/decisions",
            json=command.model_dump(mode="json"),
        )
        return DecisionPayload.model_validate(payload["data"])

    async def delete_room_decision(self, decision_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/rooms/decisions/{decision_id}")
        data = payload.get("data")
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def list_room_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[WorkspaceTaskPayload]:
        payload = await self._request(
            "GET",
            f"/internal/v1/rooms/workspaces/{workspace_id}/tasks",
            params={"status": status},
        )
        return [WorkspaceTaskPayload.model_validate(item) for item in payload["data"]]

    async def create_room_task(self, command: WorkspaceTaskCreatePayload) -> WorkspaceTaskPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/rooms/tasks",
            json=command.model_dump(mode="json"),
        )
        return WorkspaceTaskPayload.model_validate(payload["data"])

    async def update_room_task(
        self,
        *,
        workspace_id: str,
        task_id: str,
        command: WorkspaceTaskUpdatePayload,
    ) -> WorkspaceTaskPayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/rooms/workspaces/{workspace_id}/tasks/{task_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return WorkspaceTaskPayload.model_validate(data) if data is not None else None

    async def delete_room_task(self, *, workspace_id: str, task_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/rooms/workspaces/{workspace_id}/tasks/{task_id}")
        data = payload.get("data")
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def stage_and_apply_room_candidates(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        candidates: list[RoomCandidatePayload],
    ) -> RoomCandidateApplyPayload:
        payload = await self._request(
            "POST",
            f"/internal/v1/rooms/workspaces/{workspace_id}/candidate-apply",
            params={"execution_id": execution_id},
            json=[candidate.model_dump(mode="json") for candidate in candidates],
        )
        return RoomCandidateApplyPayload.model_validate(payload["data"])

    async def create_workspace(self, command: WorkspaceCreatePayload) -> WorkspacePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/workspaces",
            json=command.model_dump(mode="json"),
        )
        return WorkspacePayload.model_validate(payload["data"])

    async def list_workspaces(self, *, member_user_id: str) -> list[WorkspacePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/workspaces",
            params={"member_user_id": member_user_id},
        )
        return [WorkspacePayload.model_validate(item) for item in payload["data"]]

    async def get_workspace_stats_for_member(self, user_id: str) -> WorkspaceStatsPayload:
        payload = await self._request("GET", f"/internal/v1/workspaces/stats/member/{user_id}")
        return WorkspaceStatsPayload.model_validate(payload["data"])

    async def get_admin_workspace_stats(self) -> WorkspaceAdminStatsPayload:
        payload = await self._request("GET", "/internal/v1/workspaces/stats/admin")
        return WorkspaceAdminStatsPayload.model_validate(payload["data"])

    async def count_workspaces_by_member_ids(self, user_ids: list[str]) -> dict[str, int]:
        payload = await self._request(
            "GET",
            "/internal/v1/workspaces/stats/member-counts",
            params={"user_id": user_ids},
        )
        return {str(key): int(value) for key, value in dict(payload["data"]).items()}

    async def get_workspace(self, workspace_id: str) -> WorkspacePayload | None:
        payload = await self._request("GET", f"/internal/v1/workspaces/{workspace_id}")
        data = payload.get("data")
        return WorkspacePayload.model_validate(data) if data is not None else None

    async def workspace_has_active_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> bool:
        payload = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/members/{user_id}/active",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("has_active_membership")) if isinstance(data, dict) else False

    async def get_workspace_settings(self, workspace_id: str) -> WorkspaceSettingsPayload | None:
        payload = await self._request("GET", f"/internal/v1/workspaces/{workspace_id}/settings")
        data = payload.get("data")
        return WorkspaceSettingsPayload.model_validate(data) if data is not None else None

    async def update_workspace_settings(
        self,
        workspace_id: str,
        command: WorkspaceSettingsUpdatePayload,
    ) -> WorkspaceSettingsPayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/workspaces/{workspace_id}/settings",
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return WorkspaceSettingsPayload.model_validate(data) if data is not None else None

    async def update_workspace(
        self,
        workspace_id: str,
        command: WorkspaceUpdatePayload,
    ) -> WorkspacePayload | None:
        payload = await self._request(
            "PUT",
            f"/internal/v1/workspaces/{workspace_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return WorkspacePayload.model_validate(data) if data is not None else None

    async def delete_workspace(self, workspace_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/workspaces/{workspace_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

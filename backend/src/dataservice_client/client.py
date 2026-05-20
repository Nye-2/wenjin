"""Async HTTP client for DataService."""

from __future__ import annotations

from typing import Any

import httpx

from src.config import dataservice_settings
from src.dataservice_client.contracts.catalog import (
    CapabilityDefinitionPayload,
    CapabilitySkillPayload,
)
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
    ConversationMessagesRebuildPayload,
)
from src.dataservice_client.contracts.workspace import (
    WorkspaceCreatePayload,
    WorkspacePayload,
    WorkspaceUpdatePayload,
)
from src.dataservice_client.errors import DataServiceClientError


class AsyncDataServiceClient:
    """Small typed client used by gateway, worker, and agent runtime code."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        internal_token: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or dataservice_settings.url).rstrip("/")
        self.internal_token = internal_token if internal_token is not None else dataservice_settings.internal_token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds or dataservice_settings.timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncDataServiceClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def livez(self) -> dict[str, Any]:
        return await self._request("GET", "/livez", authenticated=False)

    async def readyz(self) -> dict[str, Any]:
        return await self._request("GET", "/readyz", authenticated=False)

    async def append_conversation_message(
        self,
        thread_id: str,
        command: ConversationMessageCreatePayload,
    ) -> ConversationMessagePayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/conversations/{thread_id}/messages",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ConversationMessagePayload.model_validate(data) if data is not None else None

    async def rebuild_conversation_messages(
        self,
        thread_id: str,
        command: ConversationMessagesRebuildPayload,
    ) -> list[ConversationMessagePayload]:
        payload = await self._request(
            "PUT",
            f"/internal/v1/conversations/{thread_id}/messages",
            json=command.model_dump(mode="json"),
        )
        return [ConversationMessagePayload.model_validate(item) for item in payload["data"]]

    async def list_conversation_messages(self, thread_id: str) -> list[ConversationMessagePayload]:
        payload = await self._request("GET", f"/internal/v1/conversations/{thread_id}/messages")
        return [ConversationMessagePayload.model_validate(item) for item in payload["data"]]

    async def list_catalog_capabilities(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[CapabilityDefinitionPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/capabilities",
            params={"workspace_type": workspace_type, "enabled_only": enabled_only},
        )
        return [CapabilityDefinitionPayload.model_validate(item) for item in payload["data"]]

    async def get_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        enabled_only: bool = False,
    ) -> CapabilityDefinitionPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}",
            params={"enabled_only": enabled_only},
        )
        data = payload.get("data")
        return CapabilityDefinitionPayload.model_validate(data) if data is not None else None

    async def list_catalog_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkillPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/skills",
            params={"enabled_only": enabled_only},
        )
        return [CapabilitySkillPayload.model_validate(item) for item in payload["data"]]

    async def get_catalog_skill(
        self,
        skill_id: str,
        *,
        enabled_only: bool = False,
    ) -> CapabilitySkillPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/catalog/skills/{skill_id}",
            params={"enabled_only": enabled_only},
        )
        data = payload.get("data")
        return CapabilitySkillPayload.model_validate(data) if data is not None else None

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

    async def get_workspace(self, workspace_id: str) -> WorkspacePayload | None:
        payload = await self._request("GET", f"/internal/v1/workspaces/{workspace_id}")
        data = payload.get("data")
        return WorkspacePayload.model_validate(data) if data is not None else None

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        if authenticated:
            headers["X-Wenjin-Internal-Token"] = self.internal_token
        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise DataServiceClientError.from_response(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise DataServiceClientError(f"DataService returned non-object payload from {path}")
        return payload

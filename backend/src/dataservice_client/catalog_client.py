"""Catalog API mixin for AsyncDataServiceClient."""

from __future__ import annotations

from typing import Any

from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload as CatalogAdminLogCreatePayload,
)
from src.dataservice_client.contracts.catalog import (
    AdminLogPayload as CatalogAdminLogPayload,
)
from src.dataservice_client.contracts.catalog import (
    AgentTemplatePayload,
    CapabilityDefinitionPayload,
    CapabilitySkillPayload,
    CatalogEnabledPayload,
    CatalogSeedLoadPayload,
    CatalogSeedLoadResultPayload,
    CatalogUpsertPayload,
)


class CatalogDataServiceClientMixin:
    """Typed DataService methods for the catalog domain."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

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

    async def has_catalog_capabilities(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/capabilities/exists")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("exists")) if isinstance(data, dict) else False

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

    async def upsert_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        command: CatalogUpsertPayload,
    ) -> CapabilityDefinitionPayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}",
            json=command.model_dump(mode="json"),
        )
        return CapabilityDefinitionPayload.model_validate(payload["data"])

    async def delete_catalog_capability(
        self,
        *,
        workspace_type: str,
        capability_id: str,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def set_catalog_capability_enabled(
        self,
        *,
        workspace_type: str,
        capability_id: str,
        command: CatalogEnabledPayload,
    ) -> CapabilityDefinitionPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/catalog/capabilities/{workspace_type}/{capability_id}/enabled",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CapabilityDefinitionPayload.model_validate(data) if data is not None else None

    async def load_catalog_capability_seed_items(
        self,
        command: CatalogSeedLoadPayload,
    ) -> CatalogSeedLoadResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/capabilities/seed-load",
            json=command.model_dump(mode="json"),
        )
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])

    async def list_catalog_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkillPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/skills",
            params={"enabled_only": enabled_only},
        )
        return [CapabilitySkillPayload.model_validate(item) for item in payload["data"]]

    async def has_catalog_skills(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/skills/exists")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("exists")) if isinstance(data, dict) else False

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

    async def upsert_catalog_skill(
        self,
        skill_id: str,
        command: CatalogUpsertPayload,
    ) -> CapabilitySkillPayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/catalog/skills/{skill_id}",
            json=command.model_dump(mode="json"),
        )
        return CapabilitySkillPayload.model_validate(payload["data"])

    async def delete_catalog_skill(self, skill_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/catalog/skills/{skill_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def set_catalog_skill_enabled(
        self,
        skill_id: str,
        command: CatalogEnabledPayload,
    ) -> CapabilitySkillPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/catalog/skills/{skill_id}/enabled",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return CapabilitySkillPayload.model_validate(data) if data is not None else None

    async def load_catalog_skill_seed_items(
        self,
        command: CatalogSeedLoadPayload,
    ) -> CatalogSeedLoadResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/skills/seed-load",
            json=command.model_dump(mode="json"),
        )
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])

    async def list_agent_templates(self, *, enabled_only: bool = False) -> list[AgentTemplatePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/agent-templates",
            params={"enabled_only": enabled_only},
        )
        return [AgentTemplatePayload.model_validate(item) for item in payload["data"]]

    async def has_agent_templates(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/agent-templates/exists")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("exists")) if isinstance(data, dict) else False

    async def get_agent_template(
        self,
        template_id: str,
        *,
        enabled_only: bool = False,
    ) -> AgentTemplatePayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/catalog/agent-templates/{template_id}",
            params={"enabled_only": enabled_only},
        )
        data = payload.get("data")
        return AgentTemplatePayload.model_validate(data) if data is not None else None

    async def upsert_agent_template(
        self,
        template_id: str,
        command: CatalogUpsertPayload,
    ) -> AgentTemplatePayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/catalog/agent-templates/{template_id}",
            json=command.model_dump(mode="json"),
        )
        return AgentTemplatePayload.model_validate(payload["data"])

    async def delete_agent_template(self, template_id: str) -> bool:
        payload = await self._request("DELETE", f"/internal/v1/catalog/agent-templates/{template_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    async def load_agent_template_seed_items(
        self,
        command: CatalogSeedLoadPayload,
    ) -> CatalogSeedLoadResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/agent-templates/seed-load",
            json=command.model_dump(mode="json"),
        )
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])

    async def record_catalog_admin_log(
        self,
        command: CatalogAdminLogCreatePayload,
    ) -> CatalogAdminLogPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/catalog/admin-logs",
            json=command.model_dump(mode="json"),
        )
        return CatalogAdminLogPayload.model_validate(payload["data"])

    async def list_catalog_admin_logs(
        self,
        *,
        action: str | None = None,
        target_user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[CatalogAdminLogPayload], int]:
        payload = await self._request(
            "GET",
            "/internal/v1/catalog/admin-logs",
            params={
                "action": action,
                "target_user_id": target_user_id,
                "offset": offset,
                "limit": limit,
            },
        )
        data = payload.get("data") or {}
        return (
            [CatalogAdminLogPayload.model_validate(item) for item in data.get("items", [])],
            int(data.get("total", 0)),
        )

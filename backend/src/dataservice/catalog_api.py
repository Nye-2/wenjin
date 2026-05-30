"""Public in-process catalog API for DataService."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.catalog.contracts import (
    AdminLogRecord,
    AgentTemplateRecord,
    CapabilityDefinitionRecord,
    CapabilitySkillRecord,
    SeedLoadResult,
)
from src.dataservice.domains.catalog.seed_loader import DataServiceCatalogSeedLoader
from src.dataservice.domains.catalog.service import DataServiceCatalogService

SeedValidator = Callable[[Path, str], dict[str, Any]]


class CatalogDataService:
    """Catalog API exposed by DataService to runtime modules."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        autocommit: bool = True,
        admin_log_model: Any | None = None,
    ) -> None:
        self._domain = DataServiceCatalogService(
            session,
            autocommit=autocommit,
            admin_log_model=admin_log_model,
        )

    async def has_capabilities(self) -> bool:
        return await self._domain.has_capabilities()

    async def has_skills(self) -> bool:
        return await self._domain.has_skills()

    async def has_agent_templates(self) -> bool:
        return await self._domain.has_agent_templates()

    async def list_capabilities(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[CapabilityDefinitionRecord]:
        return await self._domain.list_capabilities(
            workspace_type=workspace_type,
            enabled_only=enabled_only,
        )

    async def get_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled_only: bool = False,
    ) -> CapabilityDefinitionRecord | None:
        return await self._domain.get_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
            enabled_only=enabled_only,
        )

    async def list_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkillRecord]:
        return await self._domain.list_skills(enabled_only=enabled_only)

    async def get_skill(self, skill_id: str, *, enabled_only: bool = False) -> CapabilitySkillRecord | None:
        return await self._domain.get_skill(skill_id, enabled_only=enabled_only)

    async def list_agent_templates(self, *, enabled_only: bool = False) -> list[AgentTemplateRecord]:
        return await self._domain.list_agent_templates(enabled_only=enabled_only)

    async def get_agent_template(self, template_id: str, *, enabled_only: bool = False) -> AgentTemplateRecord | None:
        return await self._domain.get_agent_template(template_id, enabled_only=enabled_only)

    async def upsert_capability(
        self,
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> CapabilityDefinitionRecord:
        return await self._domain.upsert_capability(
            data,
            checksum=checksum,
            source_path=source_path,
        )

    async def upsert_skill(
        self,
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> CapabilitySkillRecord:
        return await self._domain.upsert_skill(
            data,
            checksum=checksum,
            source_path=source_path,
        )

    async def upsert_agent_template(
        self,
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> AgentTemplateRecord:
        return await self._domain.upsert_agent_template(
            data,
            checksum=checksum,
            source_path=source_path,
        )

    async def delete_all_capabilities(self) -> None:
        await self._domain.delete_all_capabilities()

    async def delete_all_skills(self) -> None:
        await self._domain.delete_all_skills()

    async def delete_all_agent_templates(self) -> None:
        await self._domain.delete_all_agent_templates()

    async def delete_capability(self, *, capability_id: str, workspace_type: str) -> bool:
        return await self._domain.delete_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
        )

    async def delete_skill(self, skill_id: str) -> bool:
        return await self._domain.delete_skill(skill_id)

    async def delete_agent_template(self, template_id: str) -> bool:
        return await self._domain.delete_agent_template(template_id)

    async def set_capability_enabled(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled: bool,
    ) -> CapabilityDefinitionRecord | None:
        return await self._domain.set_capability_enabled(
            capability_id=capability_id,
            workspace_type=workspace_type,
            enabled=enabled,
        )

    async def set_skill_enabled(self, *, skill_id: str, enabled: bool) -> CapabilitySkillRecord | None:
        return await self._domain.set_skill_enabled(skill_id=skill_id, enabled=enabled)

    async def seed_revision_matches(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
    ) -> bool:
        return await self._domain.seed_revision_matches(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=checksum,
        )

    async def record_seed_revision(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
        loaded_count: int,
        metadata_json: dict[str, Any] | None = None,
    ) -> SeedLoadResult:
        return await self._domain.record_seed_revision(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=checksum,
            loaded_count=loaded_count,
            metadata_json=metadata_json,
        )

    async def record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        target_user_id: str | None = None,
        details: dict[str, Any] | None = None,
        target_type: str = "user",
        ip_address: str | None = None,
    ) -> AdminLogRecord:
        return await self._domain.record_admin_log(
            action=action,
            admin_id=admin_id,
            target_user_id=target_user_id,
            details=details,
            target_type=target_type,
            ip_address=ip_address,
        )

    async def list_admin_logs(
        self,
        *,
        action: str | None = None,
        target_user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AdminLogRecord], int]:
        return await self._domain.list_admin_logs(
            action=action,
            target_user_id=target_user_id,
            offset=offset,
            limit=limit,
        )

    async def load_capability_seed_dir(
        self,
        seed_dir: Path,
        *,
        validate_yaml_text: SeedValidator,
        overwrite: bool = False,
    ) -> SeedLoadResult:
        loader = DataServiceCatalogSeedLoader(self._domain, seed_dir)
        return await loader.load_capabilities(
            validate_yaml_text=validate_yaml_text,
            overwrite=overwrite,
        )

    async def load_skill_seed_dir(
        self,
        seed_dir: Path,
        *,
        validate_yaml_text: SeedValidator,
        overwrite: bool = False,
    ) -> SeedLoadResult:
        loader = DataServiceCatalogSeedLoader(self._domain, seed_dir)
        return await loader.load_skills(
            validate_yaml_text=validate_yaml_text,
            overwrite=overwrite,
        )

    async def load_agent_template_seed_dir(
        self,
        seed_dir: Path,
        *,
        validate_yaml_text: SeedValidator,
        overwrite: bool = False,
    ) -> SeedLoadResult:
        loader = DataServiceCatalogSeedLoader(self._domain, seed_dir)
        return await loader.load_agent_templates(
            validate_yaml_text=validate_yaml_text,
            overwrite=overwrite,
        )

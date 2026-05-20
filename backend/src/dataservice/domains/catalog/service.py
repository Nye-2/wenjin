"""Catalog aggregate command/query service."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.catalog.contracts import (
    CapabilityDefinitionRecord,
    CapabilitySkillRecord,
    SeedLoadResult,
)
from src.dataservice.domains.catalog.projection import capability_to_record, skill_to_record
from src.dataservice.domains.catalog.repository import CatalogRepository


class DataServiceCatalogService:
    """DataService-owned capability and skill catalog operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = CatalogRepository(session)

    async def has_capabilities(self) -> bool:
        return await self.repository.has_capabilities()

    async def has_skills(self) -> bool:
        return await self.repository.has_skills()

    async def list_capabilities(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[CapabilityDefinitionRecord]:
        return [
            capability_to_record(item)
            for item in await self.repository.list_capabilities(
                workspace_type=workspace_type,
                enabled_only=enabled_only,
            )
        ]

    async def get_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled_only: bool = False,
    ) -> CapabilityDefinitionRecord | None:
        item = await self.repository.get_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
            enabled_only=enabled_only,
        )
        return capability_to_record(item) if item is not None else None

    async def list_skills(self, *, enabled_only: bool = False) -> list[CapabilitySkillRecord]:
        return [
            skill_to_record(item)
            for item in await self.repository.list_skills(enabled_only=enabled_only)
        ]

    async def get_skill(self, skill_id: str, *, enabled_only: bool = False) -> CapabilitySkillRecord | None:
        item = await self.repository.get_skill(skill_id, enabled_only=enabled_only)
        return skill_to_record(item) if item is not None else None

    async def upsert_capability(
        self,
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> CapabilityDefinitionRecord:
        values = self.capability_values(data, checksum=checksum, source_path=source_path)
        record = await self.repository.upsert_capability(values)
        await self._finish()
        return capability_to_record(record)

    async def upsert_skill(
        self,
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> CapabilitySkillRecord:
        values = self.skill_values(data, checksum=checksum, source_path=source_path)
        record = await self.repository.upsert_skill(values)
        await self._finish()
        return skill_to_record(record)

    async def replace_capabilities(self, items: list[dict[str, Any]]) -> list[CapabilityDefinitionRecord]:
        await self.repository.delete_all_capabilities()
        records = [
            await self.upsert_capability(item, checksum=item.get("checksum"), source_path=item.get("source_path"))
            for item in items
        ]
        await self._finish()
        return records

    async def delete_all_capabilities(self) -> None:
        await self.repository.delete_all_capabilities()
        await self._finish()

    async def delete_all_skills(self) -> None:
        await self.repository.delete_all_skills()
        await self._finish()

    async def delete_capability(self, *, capability_id: str, workspace_type: str) -> bool:
        deleted = await self.repository.delete_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
        )
        await self._finish()
        return deleted

    async def delete_skill(self, skill_id: str) -> bool:
        deleted = await self.repository.delete_skill(skill_id)
        await self._finish()
        return deleted

    async def set_capability_enabled(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled: bool,
    ) -> CapabilityDefinitionRecord | None:
        item = await self.repository.get_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
        )
        if item is None:
            return None
        item.enabled = enabled
        item.definition_json = {**dict(item.definition_json or {}), "enabled": enabled}
        await self._finish()
        return capability_to_record(item)

    async def set_skill_enabled(self, *, skill_id: str, enabled: bool) -> CapabilitySkillRecord | None:
        item = await self.repository.get_skill(skill_id)
        if item is None:
            return None
        item.enabled = enabled
        item.skill_json = {**dict(getattr(item, "skill_json", {}) or {}), "enabled": enabled}
        await self._finish()
        return skill_to_record(item)

    async def seed_revision_matches(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
    ) -> bool:
        latest = await self.repository.latest_seed_revision(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
        )
        return latest is not None and latest.checksum == checksum

    async def record_seed_revision(
        self,
        *,
        catalog_kind: str,
        seed_root: str,
        checksum: str,
        loaded_count: int,
        metadata_json: dict[str, Any] | None = None,
    ) -> SeedLoadResult:
        latest = await self.repository.latest_seed_revision(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
        )
        if latest is not None and latest.checksum == checksum:
            return SeedLoadResult(loaded=0, skipped=True, checksum=checksum)
        self.repository.create_seed_revision(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=checksum,
            loaded_count=loaded_count,
            metadata_json=metadata_json or {},
        )
        await self._finish()
        return SeedLoadResult(loaded=loaded_count, skipped=False, checksum=checksum)

    @staticmethod
    def capability_values(
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        definition_json = {
            "schema_version": data.get("schema_version") or "capability.v2",
            **data,
        }
        ui_meta = dict(data.get("ui_meta") or {})
        runtime = dict(data.get("runtime") or {})
        return {
            "id": str(data["id"]),
            "workspace_type": str(data["workspace_type"]),
            "schema_version": str(data.get("schema_version") or "capability.v2"),
            "enabled": bool(data.get("enabled", True)),
            "tier": str(data.get("tier") or ui_meta.get("tier") or "primary"),
            "entry_surface": str(data.get("entry_surface") or runtime.get("entry_surface") or "workbench"),
            "display_name": str(data["display_name"]),
            "description": str(data.get("description") or ""),
            "intent_description": str(data.get("intent_description") or ""),
            "trigger_phrases": list(data.get("trigger_phrases") or []),
            "required_decisions": list(data.get("required_decisions") or []),
            "brief_schema": dict(data.get("brief_schema") or {}),
            "graph_template": dict(data.get("graph_template") or {}),
            "ui_meta": ui_meta,
            "runtime": runtime,
            "dashboard_meta": dict(data.get("dashboard_meta") or {}),
            "definition_json": definition_json,
            "notes": data.get("notes"),
            "checksum": checksum,
            "source_path": source_path,
        }

    @staticmethod
    def skill_values(
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        worker_type = str(data.get("worker_type") or data.get("subagent_type") or "")
        skill_json = {
            "schema_version": data.get("schema_version") or "capability_skill.v2",
            **data,
            "worker_type": worker_type,
        }
        return {
            "id": str(data["id"]),
            "schema_version": str(data.get("schema_version") or "capability_skill.v2"),
            "enabled": bool(data.get("enabled", True)),
            "display_name": str(data["display_name"]),
            "description": str(data.get("description") or ""),
            "worker_type": worker_type,
            "subagent_type": str(data.get("subagent_type") or worker_type),
            "prompt": str(data.get("prompt") or ""),
            "allowed_tools": list(data.get("allowed_tools") or []),
            "resources": list(data.get("resources") or []),
            "config": dict(data.get("config") or {}),
            "skill_json": skill_json,
            "checksum": checksum,
            "source_path": source_path,
        }

    @staticmethod
    def checksum_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

"""Catalog aggregate command/query service."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.team_presentation import ExpertProfileV1
from src.dataservice.domains.catalog.contracts import (
    AdminLogRecord,
    AgentTemplateRecord,
    CapabilityDefinitionRecord,
    CapabilitySkillRecord,
    SeedLoadResult,
)
from src.dataservice.domains.catalog.projection import (
    admin_log_to_record,
    agent_template_to_record,
    capability_to_record,
    skill_to_record,
)
from src.dataservice.domains.catalog.repository import CatalogRepository


class DataServiceCatalogService:
    """DataService-owned capability and skill catalog operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        autocommit: bool = True,
        admin_log_model: Any | None = None,
    ) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = CatalogRepository(session, admin_log_model=admin_log_model)

    async def has_capabilities(self) -> bool:
        return await self.repository.has_capabilities()

    async def has_skills(self) -> bool:
        return await self.repository.has_skills()

    async def has_agent_templates(self) -> bool:
        return await self.repository.has_agent_templates()

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

    async def list_agent_templates(self, *, enabled_only: bool = False) -> list[AgentTemplateRecord]:
        return [
            agent_template_to_record(item)
            for item in await self.repository.list_agent_templates(enabled_only=enabled_only)
        ]

    async def get_agent_template(self, template_id: str, *, enabled_only: bool = False) -> AgentTemplateRecord | None:
        item = await self.repository.get_agent_template(template_id, enabled_only=enabled_only)
        return agent_template_to_record(item) if item is not None else None

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
        await self._refresh_if_supported(record)
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
        await self._refresh_if_supported(record)
        return skill_to_record(record)

    async def upsert_agent_template(
        self,
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> AgentTemplateRecord:
        values = self.agent_template_values(data, checksum=checksum, source_path=source_path)
        record = await self.repository.upsert_agent_template(values)
        await self._finish()
        await self._refresh_if_supported(record)
        return agent_template_to_record(record)

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

    async def delete_all_agent_templates(self) -> None:
        await self.repository.delete_all_agent_templates()
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

    async def delete_agent_template(self, template_id: str) -> bool:
        deleted = await self.repository.delete_agent_template(template_id)
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
        record = self.repository.create_admin_log(
            action=action,
            admin_id=admin_id,
            target_user_id=target_user_id,
            details=dict(details or {}),
            target_type=target_type,
            ip_address=ip_address,
        )
        await self._finish()
        if self.autocommit:
            await self.session.refresh(record)
        return admin_log_to_record(record)

    async def list_admin_logs(
        self,
        *,
        action: str | None = None,
        target_user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AdminLogRecord], int]:
        rows, total = await self.repository.list_admin_logs(
            action=action,
            target_user_id=target_user_id,
            offset=offset,
            limit=limit,
        )
        return [
            admin_log_to_record(
                log,
                admin_email=admin_email,
                admin_name=admin_name,
                target_email=target_email,
                target_name=target_name,
            )
            for log, admin_email, admin_name, target_email, target_name in rows
        ], total

    @staticmethod
    def capability_values(
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        schema_version = str(data.get("schema_version") or "")
        if schema_version != "capability.v2":
            raise ValueError("Capability catalog records must use schema_version capability.v2")
        display = data.get("display")
        intent = data.get("intent")
        inputs = data.get("inputs")
        if not isinstance(display, dict) or not isinstance(intent, dict) or not isinstance(inputs, dict):
            raise ValueError("Capability v2 records require display, intent, and inputs")
        definition_json = {
            **data,
        }
        ui_meta = dict(data.get("ui_meta") or {})
        runtime = dict(data.get("runtime") or {})
        display_name = str(data.get("display_name") or display["name"])
        description = str(data.get("description") or display.get("description") or "")
        intent_description = str(data.get("intent_description") or intent["description"])
        trigger_phrases = list(data.get("trigger_phrases") or intent.get("trigger_phrases") or [])
        required_decisions = list(data.get("required_decisions") or inputs.get("required_decisions") or [])
        brief_schema = dict(data.get("brief_schema") or inputs.get("brief_schema") or {})
        return {
            "id": str(data["id"]),
            "workspace_type": str(data["workspace_type"]),
            "schema_version": schema_version,
            "enabled": bool(data.get("enabled", True)),
            "tier": str(data.get("tier") or ui_meta.get("entry_tier") or display.get("entry_tier") or "primary"),
            "entry_surface": str(data.get("entry_surface") or runtime.get("entry_surface") or "workbench"),
            "display_name": display_name,
            "description": description,
            "intent_description": intent_description,
            "trigger_phrases": trigger_phrases,
            "required_decisions": required_decisions,
            "brief_schema": brief_schema,
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
        schema_version = str(data.get("schema_version") or "")
        if schema_version != "capability_skill.v2":
            raise ValueError("Skill catalog records must use schema_version capability_skill.v2")
        worker = data.get("worker")
        if not isinstance(worker, dict):
            raise ValueError("Capability skill v2 records require worker")
        tool_policy = data.get("tool_policy") if isinstance(data.get("tool_policy"), dict) else {}
        worker_type = str(data.get("worker_type") or worker.get("category") or "")
        subagent_type = str(data.get("subagent_type") or worker.get("subagent_type") or worker_type)
        skill_json = {
            **data,
            "worker_type": worker_type,
            "subagent_type": subagent_type,
        }
        return {
            "id": str(data["id"]),
            "schema_version": schema_version,
            "enabled": bool(data.get("enabled", True)),
            "display_name": str(data["display_name"]),
            "description": str(data.get("description") or ""),
            "worker_type": worker_type,
            "subagent_type": subagent_type,
            "prompt": str(data.get("prompt") or worker.get("role_prompt") or ""),
            "allowed_tools": list(data.get("allowed_tools") or tool_policy.get("allowed_tools") or []),
            "resources": list(data.get("resources") or []),
            "config": dict(data.get("config") or {}),
            "skill_json": skill_json,
            "checksum": checksum,
            "source_path": source_path,
        }

    @staticmethod
    def agent_template_values(
        data: dict[str, Any],
        *,
        checksum: str | None = None,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        schema_version = str(data.get("schema_version") or "")
        if schema_version != "agent_template.v1":
            raise ValueError("Agent template records must use schema_version agent_template.v1")
        template_id = str(data.get("id") or "").strip()
        display_role = str(data.get("display_role") or "").strip()
        category = str(data.get("category") or "").strip()
        if not template_id:
            raise ValueError("Agent template records require id")
        if not display_role:
            raise ValueError("Agent template records require display_role")
        if not category:
            raise ValueError("Agent template records require category")
        tool_affinity = data.get("tool_affinity")
        risk_profile = data.get("risk_profile")
        if not isinstance(tool_affinity, dict):
            raise ValueError("Agent template records require tool_affinity object")
        if not isinstance(risk_profile, dict):
            raise ValueError("Agent template records require risk_profile object")
        template_json = dict(data)
        raw_expert_profile = template_json.get("expert_profile")
        if raw_expert_profile is not None:
            try:
                expert_profile = ExpertProfileV1.model_validate(raw_expert_profile).model_dump(
                    mode="json",
                    exclude_none=True,
                )
            except Exception as exc:
                raise ValueError(
                    f"Agent template {template_id} has invalid expert_profile: {exc}"
                ) from exc
            template_json["expert_profile"] = expert_profile
        return {
            "id": template_id,
            "schema_version": schema_version,
            "enabled": bool(data.get("enabled", True)),
            "display_role": display_role,
            "category": category,
            "description": str(data.get("description") or ""),
            "persona_prompt": str(data.get("persona_prompt") or ""),
            "default_skills": list(data.get("default_skills") or []),
            "tool_affinity": tool_affinity,
            "risk_profile": risk_profile,
            "output_contracts": list(data.get("output_contracts") or []),
            "quality_expectations": list(data.get("quality_expectations") or []),
            "runtime_defaults": dict(data.get("runtime_defaults") or {}),
            "template_json": template_json,
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

    async def _refresh_if_supported(self, record: Any) -> None:
        refresh = getattr(self.session, "refresh", None)
        if callable(refresh):
            await refresh(record)

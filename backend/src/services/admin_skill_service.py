"""Admin service for capability skill catalog mutations."""

from __future__ import annotations

import hashlib
from typing import Any

import yaml
from pydantic import ValidationError

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload,
    CatalogEnabledPayload,
    CatalogUpsertPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.capability_schema import CapabilitySkillV2YamlModel, CrossRefValidator


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _yaml_to_catalog_data(model: CapabilitySkillV2YamlModel) -> dict[str, Any]:
    return model.to_catalog_data()


def _record_to_yaml_dict(skill: Any) -> dict[str, Any]:
    skill_json = getattr(skill, "skill_json", None)
    if isinstance(skill_json, dict) and skill_json:
        return dict(skill_json)
    return {}


class AdminSkillService:
    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice
        self.validator = CrossRefValidator()

    async def _list_skills(self) -> list[Any]:
        if self._dataservice is not None:
            return await self._dataservice.list_catalog_skills()
        async with dataservice_client() as client:
            return await client.list_catalog_skills()

    async def _get_skill(self, skill_id: str) -> Any | None:
        if self._dataservice is not None:
            return await self._dataservice.get_catalog_skill(skill_id)
        async with dataservice_client() as client:
            return await client.get_catalog_skill(skill_id)

    async def _upsert_skill(self, data: dict[str, Any], *, checksum: str) -> Any:
        command = CatalogUpsertPayload(data=data, checksum=checksum)
        if self._dataservice is not None:
            return await self._dataservice.upsert_catalog_skill(
                skill_id=str(data["id"]),
                command=command,
            )
        async with dataservice_client() as client:
            return await client.upsert_catalog_skill(
                skill_id=str(data["id"]),
                command=command,
            )

    async def _delete_skill(self, skill_id: str) -> bool:
        if self._dataservice is not None:
            return await self._dataservice.delete_catalog_skill(skill_id)
        async with dataservice_client() as client:
            return await client.delete_catalog_skill(skill_id)

    async def _set_skill_enabled(self, *, skill_id: str, enabled: bool) -> Any | None:
        command = CatalogEnabledPayload(enabled=enabled)
        if self._dataservice is not None:
            return await self._dataservice.set_catalog_skill_enabled(
                skill_id=skill_id,
                command=command,
            )
        async with dataservice_client() as client:
            return await client.set_catalog_skill_enabled(
                skill_id=skill_id,
                command=command,
            )

    async def _record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        details: dict[str, Any],
    ) -> None:
        command = AdminLogCreatePayload(
            action=action,
            admin_id=admin_id,
            target_user_id=None,
            details=details,
            target_type="skill",
        )
        if self._dataservice is not None:
            await self._dataservice.record_catalog_admin_log(command)
            return
        async with dataservice_client() as client:
            await client.record_catalog_admin_log(command)

    async def list_all(self) -> list[Any]:
        return await self._list_skills()

    async def get(self, skill_id: str) -> Any | None:
        return await self._get_skill(skill_id)

    async def validate(self, yaml_text: str) -> list[str]:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"yaml parse error: {e}"]
        try:
            model = CapabilitySkillV2YamlModel(**data)
        except ValidationError as e:
            return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
        return await self.validator.validate_skill(model)

    async def create(self, yaml_text: str, admin_id: str) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        if await self.get(model.id):
            raise ValueError(f"skill {model.id} already exists")

        skill = await self._upsert_skill(
            _yaml_to_catalog_data(model),
            checksum=_sha256(yaml_text),
        )

        await self._record_admin_log(
            action="skill_create",
            admin_id=admin_id,
            details={
                "skill_id": model.id,
                "yaml_after_sha256": _sha256(yaml_text),
            },
        )
        return skill

    async def update(self, skill_id: str, yaml_text: str, admin_id: str) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        if model.id != skill_id:
            raise ValueError("yaml id must match URL path")
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_record_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)

        updated = await self._upsert_skill(
            _yaml_to_catalog_data(model),
            checksum=_sha256(yaml_text),
        )

        await self._record_admin_log(
            action="skill_update",
            admin_id=admin_id,
            details={
                "skill_id": skill_id,
                "yaml_before_sha256": _sha256(before_yaml),
                "yaml_after_sha256": _sha256(yaml_text),
            },
        )
        return updated

    async def delete(self, skill_id: str, admin_id: str) -> None:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_record_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)

        await self._delete_skill(skill_id)

        await self._record_admin_log(
            action="skill_delete",
            admin_id=admin_id,
            details={
                "skill_id": skill_id,
                "yaml_before_sha256": _sha256(before_yaml),
            },
        )

    async def toggle(self, skill_id: str, admin_id: str) -> Any:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        previous = skill.enabled

        updated = await self._set_skill_enabled(
            skill_id=skill_id,
            enabled=not previous,
        )
        if updated is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="skill_toggle",
            admin_id=admin_id,
            details={
                "skill_id": skill_id,
                "enabled_before": previous,
                "enabled_after": updated.enabled,
            },
        )
        return updated

    def to_yaml_text(self, skill: Any) -> str:
        return yaml.safe_dump(_record_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)

    async def _parse_and_validate_for_write(self, yaml_text: str) -> CapabilitySkillV2YamlModel:
        errors = await self.validate(yaml_text)
        if errors:
            raise ValueError(f"validation failed: {errors}")
        data = yaml.safe_load(yaml_text)
        return CapabilitySkillV2YamlModel(**data)

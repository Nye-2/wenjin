"""Admin service for capability skill catalog mutations."""

from __future__ import annotations

import hashlib
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload,
    CatalogEnabledPayload,
    CatalogUpsertPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.capability_schema import CapabilitySkillYamlModel, CrossRefValidator

AdminLog: Any | None = None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _yaml_to_catalog_data(model: CapabilitySkillYamlModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "schema_version": "capability_skill.v2",
        "enabled": model.enabled,
        "display_name": model.display_name,
        "description": model.description,
        "worker_type": model.subagent_type,
        "subagent_type": model.subagent_type,
        "prompt": model.prompt,
        "allowed_tools": list(model.allowed_tools),
        "resources": list(model.resources),
        "config": dict(model.config),
    }


def _yaml_to_legacy_model_data(model: CapabilitySkillYamlModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "enabled": model.enabled,
        "display_name": model.display_name,
        "description": model.description,
        "subagent_type": model.subagent_type,
        "prompt": model.prompt,
        "allowed_tools": list(model.allowed_tools),
        "resources": list(model.resources),
        "config": dict(model.config),
    }


def _record_to_yaml_dict(skill: Any) -> dict[str, Any]:
    return {
        "id": skill.id,
        "enabled": skill.enabled,
        "display_name": skill.display_name,
        "description": skill.description,
        "subagent_type": skill.subagent_type,
        "prompt": skill.prompt,
        "allowed_tools": list(skill.allowed_tools or []),
        "resources": list(skill.resources or []),
        "config": dict(skill.config or {}),
    }


class AdminSkillService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        model: Any | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.db = db
        self._model = model
        self._dataservice = dataservice
        self.validator = CrossRefValidator(db)

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
        if self._model is not None:
            if AdminLog is not None:
                self.db.add(
                    AdminLog(
                        action=action,
                        admin_id=admin_id,
                        target_user_id=None,
                        details=details,
                        target_type="skill",
                    )
                )
            return

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
        if self._model is not None:
            result = await self.db.execute(select(self._model).order_by(self._model.id))
            return list(result.scalars().all())
        return await self._list_skills()

    async def get(self, skill_id: str) -> Any | None:
        if self._model is not None:
            result = await self.db.execute(select(self._model).where(self._model.id == skill_id))
            return result.scalars().first()
        return await self._get_skill(skill_id)

    async def validate(self, yaml_text: str) -> list[str]:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"yaml parse error: {e}"]
        try:
            model = CapabilitySkillYamlModel(**data)
        except ValidationError as e:
            return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
        return await self.validator.validate_skill(model)

    async def create(self, yaml_text: str, admin_id: str) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        if await self.get(model.id):
            raise ValueError(f"skill {model.id} already exists")

        if self._model is not None:
            skill = self._model(**_yaml_to_legacy_model_data(model))
            self.db.add(skill)
        else:
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
        if self._model is not None:
            await self.db.commit()
        return skill

    async def update(self, skill_id: str, yaml_text: str, admin_id: str) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        if model.id != skill_id:
            raise ValueError("yaml id must match URL path")
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_record_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)

        if self._model is not None:
            for key, value in _yaml_to_legacy_model_data(model).items():
                if key == "id":
                    continue
                setattr(skill, key, value)
            updated = skill
        else:
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
        if self._model is not None:
            await self.db.commit()
        return updated

    async def delete(self, skill_id: str, admin_id: str) -> None:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_record_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)

        if self._model is not None:
            await self.db.delete(skill)
        else:
            await self._delete_skill(skill_id)

        await self._record_admin_log(
            action="skill_delete",
            admin_id=admin_id,
            details={
                "skill_id": skill_id,
                "yaml_before_sha256": _sha256(before_yaml),
            },
        )
        if self._model is not None:
            await self.db.commit()

    async def toggle(self, skill_id: str, admin_id: str) -> Any:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        previous = skill.enabled

        if self._model is not None:
            skill.enabled = not previous
            updated = skill
        else:
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
        if self._model is not None:
            await self.db.commit()
        return updated

    def to_yaml_text(self, skill: Any) -> str:
        return yaml.safe_dump(_record_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)

    async def _parse_and_validate_for_write(self, yaml_text: str) -> CapabilitySkillYamlModel:
        errors = await self.validate(yaml_text)
        if errors:
            raise ValueError(f"validation failed: {errors}")
        data = yaml.safe_load(yaml_text)
        return CapabilitySkillYamlModel(**data)

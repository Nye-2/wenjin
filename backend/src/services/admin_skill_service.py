"""Admin service for capability skill catalog mutations."""

from __future__ import annotations

import hashlib
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.catalog_api import CatalogDataService
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
    def __init__(self, db: AsyncSession, *, model: Any | None = None) -> None:
        self.db = db
        self._model = model
        self.validator = CrossRefValidator(db)

    def _catalog(self) -> CatalogDataService:
        return CatalogDataService(
            self.db,
            autocommit=False,
            admin_log_model=AdminLog,
        )

    async def _record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        details: dict[str, Any],
    ) -> None:
        await self._catalog().record_admin_log(
            action=action,
            admin_id=admin_id,
            target_user_id=None,
            details=details,
        )

    async def list_all(self) -> list[Any]:
        if self._model is not None:
            result = await self.db.execute(select(self._model).order_by(self._model.id))
            return list(result.scalars().all())
        return await self._catalog().list_skills()

    async def get(self, skill_id: str) -> Any | None:
        if self._model is not None:
            result = await self.db.execute(select(self._model).where(self._model.id == skill_id))
            return result.scalars().first()
        return await self._catalog().get_skill(skill_id)

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
            skill = await self._catalog().upsert_skill(
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
            updated = await self._catalog().upsert_skill(
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
            await self._catalog().delete_skill(skill_id)

        await self._record_admin_log(
            action="skill_delete",
            admin_id=admin_id,
            details={
                "skill_id": skill_id,
                "yaml_before_sha256": _sha256(before_yaml),
            },
        )
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
            updated = await self._catalog().set_skill_enabled(
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

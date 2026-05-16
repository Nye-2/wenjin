"""Admin service for capability_skill mutations.

No EventBus channel because CapabilitySkill has no resolver cache today.
Reintroduce subscription when a skill cache is added.
"""

from __future__ import annotations

import hashlib
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.admin_log import AdminLog
from src.database.models.capability_skill import CapabilitySkill
from src.services.capability_schema import CapabilitySkillYamlModel, CrossRefValidator


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _yaml_to_orm(model: CapabilitySkillYamlModel) -> dict[str, Any]:
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


def _orm_to_yaml_dict(skill: CapabilitySkill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "enabled": skill.enabled,
        "display_name": skill.display_name,
        "description": skill.description,
        "subagent_type": skill.subagent_type,
        "prompt": skill.prompt,
        "allowed_tools": skill.allowed_tools,
        "resources": skill.resources,
        "config": skill.config,
    }


class AdminSkillService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.validator = CrossRefValidator(db)

    async def list_all(self) -> list[CapabilitySkill]:
        result = await self.db.execute(
            select(CapabilitySkill).order_by(CapabilitySkill.id)
        )
        return list(result.scalars().all())

    async def get(self, skill_id: str) -> CapabilitySkill | None:
        result = await self.db.execute(
            select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
        )
        return result.scalars().first()

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

    async def create(self, yaml_text: str, admin_id: str) -> CapabilitySkill:
        errors = await self.validate(yaml_text)
        if errors:
            raise ValueError(f"validation failed: {errors}")
        data = yaml.safe_load(yaml_text)
        model = CapabilitySkillYamlModel(**data)
        if await self.get(model.id):
            raise ValueError(f"skill {model.id} already exists")
        skill = CapabilitySkill(**_yaml_to_orm(model))
        self.db.add(skill)
        self.db.add(
            AdminLog(
                action="skill_create",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "skill_id": model.id,
                    "yaml_after_sha256": _sha256(yaml_text),
                },
            )
        )
        await self.db.commit()
        return skill

    async def update(
        self, skill_id: str, yaml_text: str, admin_id: str
    ) -> CapabilitySkill:
        errors = await self.validate(yaml_text)
        if errors:
            raise ValueError(f"validation failed: {errors}")
        data = yaml.safe_load(yaml_text)
        model = CapabilitySkillYamlModel(**data)
        if model.id != skill_id:
            raise ValueError("yaml id must match URL path")
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(
            _orm_to_yaml_dict(skill), sort_keys=False, allow_unicode=True
        )
        for k, v in _yaml_to_orm(model).items():
            if k == "id":
                continue
            setattr(skill, k, v)
        self.db.add(
            AdminLog(
                action="skill_update",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "skill_id": skill_id,
                    "yaml_before_sha256": _sha256(before_yaml),
                    "yaml_after_sha256": _sha256(yaml_text),
                },
            )
        )
        await self.db.commit()
        return skill

    async def delete(self, skill_id: str, admin_id: str) -> None:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(
            _orm_to_yaml_dict(skill), sort_keys=False, allow_unicode=True
        )
        await self.db.delete(skill)
        self.db.add(
            AdminLog(
                action="skill_delete",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "skill_id": skill_id,
                    "yaml_before_sha256": _sha256(before_yaml),
                },
            )
        )
        await self.db.commit()

    async def toggle(self, skill_id: str, admin_id: str) -> CapabilitySkill:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        previous = skill.enabled
        skill.enabled = not previous
        self.db.add(
            AdminLog(
                action="skill_toggle",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "skill_id": skill_id,
                    "enabled_before": previous,
                    "enabled_after": skill.enabled,
                },
            )
        )
        await self.db.commit()
        return skill

    def to_yaml_text(self, skill: CapabilitySkill) -> str:
        return yaml.safe_dump(
            _orm_to_yaml_dict(skill), sort_keys=False, allow_unicode=True
        )

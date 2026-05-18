"""Admin service for capability mutations.

Owns: list / get / create / update / delete / toggle / validate.
Publishes capability.invalidated EventBus events.
Writes AdminLog audit entries with sha256 + diff_fields.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.admin_log import AdminLog
from src.database.models.capability import Capability
from src.services.capability_schema import CapabilityYamlModel, CrossRefValidator
from src.services.event_bus import EventBus

logger = logging.getLogger(__name__)

INVALIDATE_CHANNEL = "capability.invalidated"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed.append(key)
    return sorted(changed)


def _yaml_to_orm_kwargs(model: CapabilityYamlModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "workspace_type": model.workspace_type,
        "enabled": model.enabled,
        "display_name": model.display_name,
        "description": model.description,
        "intent_description": model.intent_description,
        "trigger_phrases": list(model.trigger_phrases),
        "required_decisions": [d.model_dump() for d in model.required_decisions],
        "brief_schema": model.brief_schema,
        "graph_template": model.graph_template.model_dump(),
        "ui_meta": model.ui_meta.model_dump(),
        "runtime": model.runtime.model_dump(),
        "dashboard_meta": model.dashboard_meta.model_dump(),
        "notes": model.notes,
    }


def _orm_to_yaml_dict(cap: Capability) -> dict[str, Any]:
    return {
        "id": cap.id,
        "workspace_type": cap.workspace_type,
        "enabled": cap.enabled,
        "display_name": cap.display_name,
        "description": cap.description,
        "intent_description": cap.intent_description,
        "trigger_phrases": cap.trigger_phrases,
        "required_decisions": cap.required_decisions,
        "brief_schema": cap.brief_schema,
        "graph_template": cap.graph_template,
        "ui_meta": cap.ui_meta,
        "runtime": cap.runtime,
        "dashboard_meta": cap.dashboard_meta,
        "notes": cap.notes,
    }


class AdminCapabilityService:
    def __init__(self, db: AsyncSession, event_bus: EventBus) -> None:
        self.db = db
        self.event_bus = event_bus
        self.validator = CrossRefValidator(db)

    async def list_all(self) -> list[Capability]:
        result = await self.db.execute(
            select(Capability).order_by(Capability.workspace_type, Capability.id)
        )
        return list(result.scalars().all())

    async def get(
        self, capability_id: str, workspace_type: str
    ) -> Capability | None:
        result = await self.db.execute(
            select(Capability).where(
                Capability.id == capability_id,
                Capability.workspace_type == workspace_type,
            )
        )
        return result.scalars().first()

    async def validate(self, yaml_text: str) -> list[str]:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"yaml parse error: {e}"]
        try:
            model = CapabilityYamlModel(**data)
        except ValidationError as e:
            return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
        return await self.validator.validate_capability(model)

    async def create(self, yaml_text: str, admin_id: str) -> Capability:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ValueError(f"yaml parse error: {e}") from e
        try:
            model = CapabilityYamlModel(**data)
        except ValidationError as e:
            raise ValueError(f"schema validation failed: {e.errors()}") from e
        errors = await self.validator.validate_capability(model)
        if errors:
            raise ValueError(f"cross-ref validation failed: {errors}")

        existing = await self.get(model.id, model.workspace_type)
        if existing is not None:
            raise ValueError(
                f"capability {model.id} for {model.workspace_type} already exists"
            )

        cap = Capability(**_yaml_to_orm_kwargs(model))
        self.db.add(cap)

        self.db.add(
            AdminLog(
                action="capability_create",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": model.id,
                    "workspace_type": model.workspace_type,
                    "yaml_after_sha256": _sha256(yaml_text),
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": model.id, "workspace_type": model.workspace_type},
        )
        return cap

    async def update(
        self,
        capability_id: str,
        workspace_type: str,
        yaml_text: str,
        admin_id: str,
    ) -> Capability:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ValueError(f"yaml parse error: {e}") from e
        try:
            model = CapabilityYamlModel(**data)
        except ValidationError as e:
            raise ValueError(f"schema validation failed: {e.errors()}") from e
        if model.id != capability_id or model.workspace_type != workspace_type:
            raise ValueError("yaml id/workspace_type must match URL path")
        errors = await self.validator.validate_capability(model)
        if errors:
            raise ValueError(f"cross-ref validation failed: {errors}")

        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError(f"capability {capability_id} not found")

        before_dict = _orm_to_yaml_dict(cap)
        before_yaml = yaml.safe_dump(before_dict, sort_keys=False, allow_unicode=True)
        after_kwargs = _yaml_to_orm_kwargs(model)
        for k, v in after_kwargs.items():
            if k in ("id", "workspace_type"):
                continue
            setattr(cap, k, v)

        self.db.add(
            AdminLog(
                action="capability_update",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": model.id,
                    "workspace_type": model.workspace_type,
                    "yaml_before_sha256": _sha256(before_yaml),
                    "yaml_after_sha256": _sha256(yaml_text),
                    "diff_fields": _diff_fields(
                        before_dict, _orm_to_yaml_dict(cap)
                    ),
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": model.id, "workspace_type": model.workspace_type},
        )
        return cap

    async def delete(
        self, capability_id: str, workspace_type: str, admin_id: str
    ) -> None:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(
            _orm_to_yaml_dict(cap), sort_keys=False, allow_unicode=True
        )
        await self.db.delete(cap)
        self.db.add(
            AdminLog(
                action="capability_delete",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": capability_id,
                    "workspace_type": workspace_type,
                    "yaml_before_sha256": _sha256(before_yaml),
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )

    async def toggle(
        self, capability_id: str, workspace_type: str, admin_id: str
    ) -> Capability:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        previous = cap.enabled
        cap.enabled = not previous
        self.db.add(
            AdminLog(
                action="capability_toggle",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": capability_id,
                    "workspace_type": workspace_type,
                    "enabled_before": previous,
                    "enabled_after": cap.enabled,
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )
        return cap

    async def publish_invalidation(
        self, capability_id: str, workspace_type: str
    ) -> None:
        """Publish a capability.invalidated event to clear caches."""
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )

    def to_yaml_text(self, cap: Capability) -> str:
        return yaml.safe_dump(
            _orm_to_yaml_dict(cap), sort_keys=False, allow_unicode=True
        )

"""Admin service for capability catalog mutations."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.admin_log import AdminLog
from src.dataservice.catalog_api import CatalogDataService
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


def _yaml_to_catalog_data(model: CapabilityYamlModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "workspace_type": model.workspace_type,
        "schema_version": "capability.v2",
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


def _record_to_yaml_dict(cap: Any) -> dict[str, Any]:
    return {
        "id": cap.id,
        "workspace_type": cap.workspace_type,
        "enabled": cap.enabled,
        "display_name": cap.display_name,
        "description": cap.description,
        "intent_description": cap.intent_description,
        "trigger_phrases": list(cap.trigger_phrases or []),
        "required_decisions": list(cap.required_decisions or []),
        "brief_schema": dict(cap.brief_schema or {}),
        "graph_template": dict(cap.graph_template or {}),
        "ui_meta": dict(cap.ui_meta or {}),
        "runtime": dict(cap.runtime or {}),
        "dashboard_meta": dict(cap.dashboard_meta or {}),
        "notes": cap.notes,
    }


class AdminCapabilityService:
    def __init__(
        self,
        db: AsyncSession,
        event_bus: EventBus,
        *,
        model: Any | None = None,
    ) -> None:
        self.db = db
        self.event_bus = event_bus
        self._model = model
        self.validator = CrossRefValidator(db)

    async def list_all(self) -> list[Any]:
        if self._model is not None:
            result = await self.db.execute(
                select(self._model).order_by(self._model.workspace_type, self._model.id)
            )
            return list(result.scalars().all())
        return await CatalogDataService(self.db, autocommit=False).list_capabilities()

    async def get(self, capability_id: str, workspace_type: str) -> Any | None:
        if self._model is not None:
            result = await self.db.execute(
                select(self._model).where(
                    self._model.id == capability_id,
                    self._model.workspace_type == workspace_type,
                )
            )
            return result.scalars().first()
        return await CatalogDataService(self.db, autocommit=False).get_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
        )

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

    async def create(self, yaml_text: str, admin_id: str) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        existing = await self.get(model.id, model.workspace_type)
        if existing is not None:
            raise ValueError(f"capability {model.id} for {model.workspace_type} already exists")

        if self._model is not None:
            model_data = {
                key: value
                for key, value in _yaml_to_catalog_data(model).items()
                if key != "schema_version"
            }
            cap = self._model(**model_data)
            self.db.add(cap)
        else:
            cap = await CatalogDataService(self.db, autocommit=False).upsert_capability(
                _yaml_to_catalog_data(model),
                checksum=_sha256(yaml_text),
            )

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
        await self.publish_invalidation(model.id, model.workspace_type)
        return cap

    async def update(
        self,
        capability_id: str,
        workspace_type: str,
        yaml_text: str,
        admin_id: str,
    ) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        if model.id != capability_id or model.workspace_type != workspace_type:
            raise ValueError("yaml id/workspace_type must match URL path")

        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError(f"capability {capability_id} not found")

        before_dict = _record_to_yaml_dict(cap)
        before_yaml = yaml.safe_dump(before_dict, sort_keys=False, allow_unicode=True)
        after_data = _yaml_to_catalog_data(model)

        if self._model is not None:
            for key, value in after_data.items():
                if key in ("id", "workspace_type", "schema_version"):
                    continue
                setattr(cap, key, value)
            updated = cap
        else:
            updated = await CatalogDataService(self.db, autocommit=False).upsert_capability(
                after_data,
                checksum=_sha256(yaml_text),
            )

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
                    "diff_fields": _diff_fields(before_dict, _record_to_yaml_dict(updated)),
                },
            )
        )
        await self.db.commit()
        await self.publish_invalidation(model.id, model.workspace_type)
        return updated

    async def delete(self, capability_id: str, workspace_type: str, admin_id: str) -> None:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_record_to_yaml_dict(cap), sort_keys=False, allow_unicode=True)

        if self._model is not None:
            await self.db.delete(cap)
        else:
            await CatalogDataService(self.db, autocommit=False).delete_capability(
                capability_id=capability_id,
                workspace_type=workspace_type,
            )

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
        await self.publish_invalidation(capability_id, workspace_type)

    async def toggle(self, capability_id: str, workspace_type: str, admin_id: str) -> Any:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        previous = cap.enabled

        if self._model is not None:
            cap.enabled = not previous
            updated = cap
        else:
            updated = await CatalogDataService(self.db, autocommit=False).set_capability_enabled(
                capability_id=capability_id,
                workspace_type=workspace_type,
                enabled=not previous,
            )
            if updated is None:
                raise ValueError("not found")

        self.db.add(
            AdminLog(
                action="capability_toggle",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": capability_id,
                    "workspace_type": workspace_type,
                    "enabled_before": previous,
                    "enabled_after": updated.enabled,
                },
            )
        )
        await self.db.commit()
        await self.publish_invalidation(capability_id, workspace_type)
        return updated

    async def publish_invalidation(self, capability_id: str, workspace_type: str) -> None:
        """Publish a capability.invalidated event to clear caches."""
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )

    def to_yaml_text(self, cap: Any) -> str:
        return yaml.safe_dump(_record_to_yaml_dict(cap), sort_keys=False, allow_unicode=True)

    async def _parse_and_validate_for_write(self, yaml_text: str) -> CapabilityYamlModel:
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
        return model

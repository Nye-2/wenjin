"""Admin service for capability catalog mutations."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import (
    AdminLogCreatePayload,
    CatalogEnabledPayload,
    CatalogUpsertPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.capability_schema import CapabilityV2YamlModel, CrossRefValidator
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


def _yaml_to_catalog_data(model: CapabilityV2YamlModel) -> dict[str, Any]:
    return model.to_catalog_data()


def _record_to_yaml_dict(cap: Any) -> dict[str, Any]:
    definition_json = getattr(cap, "definition_json", None)
    if isinstance(definition_json, dict) and definition_json:
        return dict(definition_json)
    return {}


class AdminCapabilityService:
    def __init__(
        self,
        db: AsyncSession,
        event_bus: EventBus,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.db = db
        self.event_bus = event_bus
        self._dataservice = dataservice
        self.validator = CrossRefValidator(db)

    async def _list_capabilities(self) -> list[Any]:
        if self._dataservice is not None:
            return await self._dataservice.list_catalog_capabilities()
        async with dataservice_client() as client:
            return await client.list_catalog_capabilities()

    async def _get_capability(self, capability_id: str, workspace_type: str) -> Any | None:
        if self._dataservice is not None:
            return await self._dataservice.get_catalog_capability(
                capability_id=capability_id,
                workspace_type=workspace_type,
            )
        async with dataservice_client() as client:
            return await client.get_catalog_capability(
                capability_id=capability_id,
                workspace_type=workspace_type,
            )

    async def _upsert_capability(
        self,
        data: dict[str, Any],
        *,
        checksum: str,
    ) -> Any:
        command = CatalogUpsertPayload(data=data, checksum=checksum)
        if self._dataservice is not None:
            return await self._dataservice.upsert_catalog_capability(
                workspace_type=str(data["workspace_type"]),
                capability_id=str(data["id"]),
                command=command,
            )
        async with dataservice_client() as client:
            return await client.upsert_catalog_capability(
                workspace_type=str(data["workspace_type"]),
                capability_id=str(data["id"]),
                command=command,
            )

    async def _delete_capability(self, *, capability_id: str, workspace_type: str) -> bool:
        if self._dataservice is not None:
            return await self._dataservice.delete_catalog_capability(
                capability_id=capability_id,
                workspace_type=workspace_type,
            )
        async with dataservice_client() as client:
            return await client.delete_catalog_capability(
                capability_id=capability_id,
                workspace_type=workspace_type,
            )

    async def _set_capability_enabled(
        self,
        *,
        capability_id: str,
        workspace_type: str,
        enabled: bool,
    ) -> Any | None:
        command = CatalogEnabledPayload(enabled=enabled)
        if self._dataservice is not None:
            return await self._dataservice.set_catalog_capability_enabled(
                capability_id=capability_id,
                workspace_type=workspace_type,
                command=command,
            )
        async with dataservice_client() as client:
            return await client.set_catalog_capability_enabled(
                capability_id=capability_id,
                workspace_type=workspace_type,
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
            target_type="capability",
        )
        if self._dataservice is not None:
            await self._dataservice.record_catalog_admin_log(command)
            return
        async with dataservice_client() as client:
            await client.record_catalog_admin_log(command)

    async def list_all(self) -> list[Any]:
        return await self._list_capabilities()

    async def get(self, capability_id: str, workspace_type: str) -> Any | None:
        return await self._get_capability(capability_id, workspace_type)

    async def validate(self, yaml_text: str) -> list[str]:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"yaml parse error: {e}"]
        try:
            model = CapabilityV2YamlModel(**data)
        except ValidationError as e:
            return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
        return await self.validator.validate_capability(model)

    async def create(self, yaml_text: str, admin_id: str) -> Any:
        model = await self._parse_and_validate_for_write(yaml_text)
        existing = await self.get(model.id, model.workspace_type)
        if existing is not None:
            raise ValueError(f"capability {model.id} for {model.workspace_type} already exists")

        cap = await self._upsert_capability(
            _yaml_to_catalog_data(model),
            checksum=_sha256(yaml_text),
        )

        await self._record_admin_log(
            action="capability_create",
            admin_id=admin_id,
            details={
                "capability_id": model.id,
                "workspace_type": model.workspace_type,
                "yaml_after_sha256": _sha256(yaml_text),
            },
        )
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

        updated = await self._upsert_capability(
            after_data,
            checksum=_sha256(yaml_text),
        )

        await self._record_admin_log(
            action="capability_update",
            admin_id=admin_id,
            details={
                "capability_id": model.id,
                "workspace_type": model.workspace_type,
                "yaml_before_sha256": _sha256(before_yaml),
                "yaml_after_sha256": _sha256(yaml_text),
                "diff_fields": _diff_fields(before_dict, _record_to_yaml_dict(updated)),
            },
        )
        await self.publish_invalidation(model.id, model.workspace_type)
        return updated

    async def delete(self, capability_id: str, workspace_type: str, admin_id: str) -> None:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_record_to_yaml_dict(cap), sort_keys=False, allow_unicode=True)

        await self._delete_capability(
            capability_id=capability_id,
            workspace_type=workspace_type,
        )

        await self._record_admin_log(
            action="capability_delete",
            admin_id=admin_id,
            details={
                "capability_id": capability_id,
                "workspace_type": workspace_type,
                "yaml_before_sha256": _sha256(before_yaml),
            },
        )
        await self.publish_invalidation(capability_id, workspace_type)

    async def toggle(self, capability_id: str, workspace_type: str, admin_id: str) -> Any:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        previous = cap.enabled

        updated = await self._set_capability_enabled(
            capability_id=capability_id,
            workspace_type=workspace_type,
            enabled=not previous,
        )
        if updated is None:
            raise ValueError("not found")

        await self._record_admin_log(
            action="capability_toggle",
            admin_id=admin_id,
            details={
                "capability_id": capability_id,
                "workspace_type": workspace_type,
                "enabled_before": previous,
                "enabled_after": updated.enabled,
            },
        )
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

    async def _parse_and_validate_for_write(self, yaml_text: str) -> CapabilityV2YamlModel:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ValueError(f"yaml parse error: {e}") from e
        try:
            model = CapabilityV2YamlModel(**data)
        except ValidationError as e:
            raise ValueError(f"schema validation failed: {e.errors()}") from e
        errors = await self.validator.validate_capability(model)
        if errors:
            raise ValueError(f"cross-ref validation failed: {errors}")
        return model

"""Model catalog aggregate service."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.model_catalog import (
    ModelCategory,
    ModelHealthStatus,
    ModelProviderProtocol,
    ModelTrustLevel,
)
from src.dataservice.common.errors import DataServiceConflictError, DataServiceNotFoundError, DataServiceValidationError
from src.dataservice.domains.model_catalog.contracts import ModelCatalogRecord, ModelRuntimeConfig
from src.dataservice.domains.model_catalog.repository import ModelCatalogRepository
from src.dataservice.domains.model_catalog.security import (
    api_key_fingerprint,
    api_key_last4,
    decrypt_api_key,
    encrypt_api_key,
    load_model_secret_key,
    redact_api_key,
    validate_model_base_url,
)

_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9._-]{6,}")


class DataServiceModelCatalogService:
    """DataService-owned model catalog operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        master_key: str | bytes | None = None,
        autocommit: bool = True,
        allow_private_network: bool = False,
        require_https: bool = True,
    ) -> None:
        self.session = session
        self.autocommit = autocommit
        self.master_key = master_key if master_key is not None else load_model_secret_key()
        self.allow_private_network = allow_private_network
        self.require_https = require_https
        self.repository = ModelCatalogRepository(session)

    async def create_model(self, data: dict[str, Any], *, admin_id: str | None = None) -> ModelCatalogRecord:
        values = self._create_values(data, admin_id=admin_id)
        if values["is_default"]:
            await self.repository.unset_default_models(category=values["category"].value)
        record = await self.repository.create_model(values)
        await self._finish(record)
        return self.to_record(record)

    async def list_models(
        self,
        *,
        category: str | ModelCategory | None = None,
        enabled_only: bool = False,
    ) -> list[ModelCatalogRecord]:
        rows = await self.repository.list_models(
            category=_enum_value(category) if category is not None else None,
            enabled_only=enabled_only,
        )
        return [self.to_record(row) for row in rows]

    async def get_model(self, model_id: str) -> ModelCatalogRecord | None:
        row = await self.repository.get_model(model_id)
        return self.to_record(row) if row is not None else None

    async def list_runtime_models(
        self,
        *,
        category: str | ModelCategory | None = None,
    ) -> list[ModelRuntimeConfig]:
        rows = await self.repository.list_models(
            category=_enum_value(category) if category is not None else None,
            enabled_only=True,
        )
        return [self.to_runtime_config(row) for row in rows]

    async def update_model(
        self,
        model_id: str,
        data: dict[str, Any],
        *,
        admin_id: str | None = None,
    ) -> ModelCatalogRecord | None:
        row = await self.repository.get_model(model_id)
        if row is None:
            return None
        requested_model_id = data.get("model_id")
        if requested_model_id is not None and requested_model_id != model_id:
            raise DataServiceValidationError("model_id is immutable")
        requested_category = data.get("category")
        if requested_category is not None and _coerce_enum(ModelCategory, requested_category) != row.category:
            raise DataServiceValidationError("category is immutable")

        if data.get("is_default") is False and bool(row.is_default):
            raise DataServiceConflictError("default model cannot be unset directly")
        effective_enabled = bool(row.enabled) if data.get("enabled") is None else bool(data["enabled"])
        effective_default = bool(row.is_default) if data.get("is_default") is None else bool(data["is_default"])
        if effective_default and not effective_enabled:
            raise DataServiceConflictError("default model must be enabled")

        update_values = self._update_values(row, data, admin_id=admin_id)
        if update_values.get("is_default") is True:
            await self.repository.unset_default_models(category=_enum_value(row.category), except_model_id=model_id)
        for key, value in update_values.items():
            setattr(row, key, value)
        row.config_version = int(getattr(row, "config_version", 1) or 1) + 1
        await self._finish(row)
        return self.to_record(row)

    async def set_default_model(self, model_id: str, *, admin_id: str | None = None) -> ModelCatalogRecord | None:
        row = await self.repository.get_model(model_id)
        if row is None:
            return None
        if not bool(row.enabled):
            raise DataServiceConflictError("Cannot make a disabled model default")
        await self.repository.unset_default_models(category=_enum_value(row.category), except_model_id=model_id)
        row.is_default = True
        row.updated_by_admin_id = admin_id
        row.config_version = int(getattr(row, "config_version", 1) or 1) + 1
        await self._finish(row)
        return self.to_record(row)

    async def update_health(
        self,
        model_id: str,
        *,
        status: str | ModelHealthStatus,
        error_message: str | None = None,
    ) -> ModelCatalogRecord | None:
        row = await self.repository.get_model(model_id)
        if row is None:
            return None
        row.health_status = _coerce_enum(ModelHealthStatus, status)
        row.last_tested_at = datetime.now(UTC)
        row.last_test_error = _redact_error(error_message)
        await self._finish(row)
        return self.to_record(row)

    async def require_model(self, model_id: str) -> ModelCatalogRecord:
        record = await self.get_model(model_id)
        if record is None:
            raise DataServiceNotFoundError("Model catalog entry not found")
        return record

    def to_record(self, row: Any) -> ModelCatalogRecord:
        return ModelCatalogRecord(
            id=str(row.id) if getattr(row, "id", None) is not None else None,
            model_id=row.model_id,
            display_name=row.display_name,
            provider_protocol=_enum_value(row.provider_protocol),
            provider_name=row.provider_name,
            category=_enum_value(row.category),
            model_name=row.model_name,
            base_url=row.base_url,
            api_key_redacted=redact_api_key(getattr(row, "api_key_last4", None)),
            enabled=bool(row.enabled),
            is_default=bool(row.is_default),
            supports_streaming=bool(row.supports_streaming),
            supports_tools=bool(row.supports_tools),
            supports_json_mode=bool(row.supports_json_mode),
            supports_json_schema=bool(row.supports_json_schema),
            supports_vision=bool(row.supports_vision),
            supports_reasoning_effort=bool(row.supports_reasoning_effort),
            max_tokens=int(row.max_tokens),
            temperature=float(row.temperature),
            timeout_seconds=getattr(row, "timeout_seconds", None),
            max_retries=getattr(row, "max_retries", None),
            trust_level=_enum_value(row.trust_level),
            pricing_policy_id=getattr(row, "pricing_policy_id", None),
            config_version=int(getattr(row, "config_version", 1) or 1),
            health_status=_enum_value(row.health_status),
            last_tested_at=getattr(row, "last_tested_at", None),
            last_test_error=getattr(row, "last_test_error", None),
            default_headers=dict(getattr(row, "default_headers", {}) or {}),
            created_by_admin_id=getattr(row, "created_by_admin_id", None),
            updated_by_admin_id=getattr(row, "updated_by_admin_id", None),
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )

    def to_runtime_config(self, row: Any) -> ModelRuntimeConfig:
        return ModelRuntimeConfig(
            model_id=row.model_id,
            display_name=row.display_name,
            provider_protocol=_enum_value(row.provider_protocol),
            provider_name=row.provider_name,
            category=_enum_value(row.category),
            model_name=row.model_name,
            base_url=row.base_url,
            api_key=decrypt_api_key(row.encrypted_api_key, model_id=row.model_id, master_key=self.master_key),
            is_default=bool(row.is_default),
            supports_streaming=bool(row.supports_streaming),
            supports_tools=bool(row.supports_tools),
            supports_json_mode=bool(row.supports_json_mode),
            supports_json_schema=bool(row.supports_json_schema),
            supports_vision=bool(row.supports_vision),
            supports_reasoning_effort=bool(row.supports_reasoning_effort),
            max_tokens=int(row.max_tokens),
            temperature=float(row.temperature),
            timeout_seconds=getattr(row, "timeout_seconds", None),
            max_retries=getattr(row, "max_retries", None),
            trust_level=_enum_value(row.trust_level),
            pricing_policy_id=getattr(row, "pricing_policy_id", None),
            config_version=int(getattr(row, "config_version", 1) or 1),
            default_headers=dict(getattr(row, "default_headers", {}) or {}),
        )

    def _create_values(self, data: dict[str, Any], *, admin_id: str | None) -> dict[str, Any]:
        model_id = _required_string(data, "model_id")
        api_key = _required_string(data, "api_key")
        category = _coerce_enum(ModelCategory, data.get("category", ModelCategory.LLM.value))
        enabled = bool(data.get("enabled", True))
        is_default = bool(data.get("is_default", False))
        if is_default and not enabled:
            raise DataServiceValidationError("default model must be enabled")
        return {
            "model_id": model_id,
            "display_name": _required_string(data, "display_name"),
            "provider_protocol": _coerce_enum(ModelProviderProtocol, data.get("provider_protocol", ModelProviderProtocol.OPENAI_COMPATIBLE.value)),
            "provider_name": str(data.get("provider_name") or "Custom").strip(),
            "category": category,
            "model_name": _required_string(data, "model_name"),
            "base_url": validate_model_base_url(
                _required_string(data, "base_url"),
                allow_private_network=self.allow_private_network,
                require_https=self.require_https,
            ),
            "encrypted_api_key": encrypt_api_key(api_key, model_id=model_id, master_key=self.master_key),
            "api_key_last4": api_key_last4(api_key),
            "api_key_fingerprint": api_key_fingerprint(api_key, master_key=self.master_key),
            "enabled": enabled,
            "is_default": is_default,
            "supports_streaming": bool(data.get("supports_streaming", True)),
            "supports_tools": bool(data.get("supports_tools", False)),
            "supports_json_mode": bool(data.get("supports_json_mode", True)),
            "supports_json_schema": bool(data.get("supports_json_schema", False)),
            "supports_vision": bool(data.get("supports_vision", False)),
            "supports_reasoning_effort": bool(data.get("supports_reasoning_effort", False)),
            "max_tokens": int(data.get("max_tokens", 4096)),
            "temperature": float(data.get("temperature", 0.7)),
            "timeout_seconds": data.get("timeout_seconds"),
            "max_retries": data.get("max_retries"),
            "trust_level": _coerce_enum(ModelTrustLevel, data.get("trust_level", ModelTrustLevel.CUSTOM.value)),
            "pricing_policy_id": data.get("pricing_policy_id"),
            "config_version": 1,
            "health_status": ModelHealthStatus.UNKNOWN,
            "default_headers": _dict_value(data.get("default_headers")),
            "created_by_admin_id": admin_id,
            "updated_by_admin_id": admin_id,
        }

    def _update_values(self, row: Any, data: dict[str, Any], *, admin_id: str | None) -> dict[str, Any]:
        values: dict[str, Any] = {}
        simple_fields = {
            "display_name",
            "provider_name",
            "model_name",
            "enabled",
            "is_default",
            "supports_streaming",
            "supports_tools",
            "supports_json_mode",
            "supports_json_schema",
            "supports_vision",
            "supports_reasoning_effort",
            "max_tokens",
            "temperature",
            "timeout_seconds",
            "max_retries",
            "pricing_policy_id",
        }
        for field in simple_fields:
            if field in data:
                values[field] = data[field]
        if "provider_protocol" in data:
            values["provider_protocol"] = _coerce_enum(ModelProviderProtocol, data["provider_protocol"])
        if "category" in data:
            values["category"] = _coerce_enum(ModelCategory, data["category"])
        if "trust_level" in data:
            values["trust_level"] = _coerce_enum(ModelTrustLevel, data["trust_level"])
        if "base_url" in data:
            values["base_url"] = validate_model_base_url(
                _required_string(data, "base_url"),
                allow_private_network=self.allow_private_network,
                require_https=self.require_https,
            )
        if "default_headers" in data:
            values["default_headers"] = _dict_value(data.get("default_headers"))
        api_key = data.get("api_key")
        if api_key:
            key_value = str(api_key)
            values["encrypted_api_key"] = encrypt_api_key(key_value, model_id=row.model_id, master_key=self.master_key)
            values["api_key_last4"] = api_key_last4(key_value)
            values["api_key_fingerprint"] = api_key_fingerprint(key_value, master_key=self.master_key)
        values["updated_by_admin_id"] = admin_id
        return values

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None and hasattr(self.session, "refresh"):
                await self.session.refresh(record)
            return
        await self.session.flush()
        if record is not None and hasattr(self.session, "refresh"):
            await self.session.refresh(record)


def _required_string(data: dict[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise DataServiceValidationError(f"{field} is required")
    return value


def _dict_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DataServiceValidationError("default_headers must be an object")
    return dict(value)


def _coerce_enum(enum_cls: type[StrEnum], value: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value))
    except ValueError as exc:
        raise DataServiceValidationError(f"Unsupported {enum_cls.__name__}: {value}") from exc


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _redact_error(message: str | None) -> str | None:
    if message is None:
        return None
    return _SECRET_PATTERN.sub(lambda match: redact_api_key(api_key_last4(match.group(0))) or "sk-****", message)[:500]

"""Model catalog aggregate service."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.model_catalog import (
    ModelCategory,
    ModelHealthStatus,
    ModelTrustLevel,
)
from src.database.models.pricing_policy import PricingPolicyKind
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
from src.dataservice.domains.pricing.repository import PricingPolicyRepository
from src.models.capability_profile import (
    CapabilityProfileAssessment,
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelCapabilityProfile,
    assess_profile_freshness,
    unverified_capability_assessment,
)
from src.security.redaction import redact_secret_text, redact_sensitive_headers

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
        self.pricing_repository = PricingPolicyRepository(session)

    async def create_model(self, data: dict[str, Any], *, admin_id: str | None = None) -> ModelCatalogRecord:
        values = self._create_values(data, admin_id=admin_id)
        await self._validate_model_usage_pricing_policy(
            enabled=bool(values["enabled"]),
            pricing_policy_id=values.get("pricing_policy_id"),
        )
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

    async def get_runtime_model(self, model_id: str) -> ModelRuntimeConfig | None:
        """Return one internal runtime config regardless of enabled state."""

        row = await self.repository.get_model(model_id)
        return self.to_runtime_config(row) if row is not None else None

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
        await self._validate_model_usage_pricing_policy(
            enabled=effective_enabled,
            pricing_policy_id=update_values.get("pricing_policy_id", getattr(row, "pricing_policy_id", None)),
        )
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

    async def update_capability_assessment(
        self,
        model_id: str,
        *,
        profile: ModelCapabilityProfile | dict[str, Any],
        evidence: ModelCapabilityProbeEvidence | dict[str, Any],
    ) -> ModelCatalogRecord | None:
        """Persist an exact endpoint-bound result from the explicit probe runner."""

        row = await self.repository.get_model(model_id)
        if row is None:
            return None
        try:
            assessment = CapabilityProfileAssessment.model_validate(
                {"profile": profile, "evidence": evidence}
            )
        except ValidationError as exc:
            raise DataServiceValidationError(
                "capability assessment is not derived from its probe evidence"
            ) from exc
        freshness = assess_profile_freshness(
            assessment.profile,
            assessment.evidence,
            model_id=row.model_id,
            model_name=row.model_name,
            base_url=row.base_url,
            generation_api=_generation_api_value(row.generation_api),
        )
        if not freshness.current:
            joined = ", ".join(freshness.reasons)
            raise DataServiceValidationError(
                f"capability assessment does not match the current endpoint: {joined}"
            )

        row.capability_profile_json = assessment.profile.model_dump(mode="json")
        row.capability_probe_json = assessment.evidence.model_dump(mode="json")
        row.capability_probe_hash = assessment.profile.probe_hash
        row.capability_observed_at = assessment.profile.observed_at
        row.last_tested_at = assessment.profile.observed_at
        if assessment.profile.protocol_conformance:
            row.health_status = ModelHealthStatus.HEALTHY
            row.last_test_error = None
        else:
            row.health_status = ModelHealthStatus.FAILED
            row.last_test_error = "capability probe did not satisfy protocol conformance"
        row.config_version = int(getattr(row, "config_version", 1) or 1) + 1
        await self._finish(row)
        return self.to_record(row)

    async def require_model(self, model_id: str) -> ModelCatalogRecord:
        record = await self.get_model(model_id)
        if record is None:
            raise DataServiceNotFoundError("Model catalog entry not found")
        return record

    def to_record(self, row: Any) -> ModelCatalogRecord:
        assessment = _assessment_from_row(row)
        return ModelCatalogRecord(
            id=str(row.id) if getattr(row, "id", None) is not None else None,
            model_id=row.model_id,
            display_name=row.display_name,
            generation_api=_generation_api_value(row.generation_api),
            provider_name=row.provider_name,
            category=_enum_value(row.category),
            model_name=row.model_name,
            base_url=row.base_url,
            api_key_redacted=redact_api_key(getattr(row, "api_key_last4", None)),
            enabled=bool(row.enabled),
            is_default=bool(row.is_default),
            capability_profile=assessment.profile,
            capability_probe=assessment.evidence,
            capability_probe_hash=assessment.profile.probe_hash,
            capability_observed_at=assessment.profile.observed_at,
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
            default_headers=redact_sensitive_headers(getattr(row, "default_headers", {}) or {}),
            created_by_admin_id=getattr(row, "created_by_admin_id", None),
            updated_by_admin_id=getattr(row, "updated_by_admin_id", None),
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )

    def to_runtime_config(self, row: Any) -> ModelRuntimeConfig:
        assessment = _assessment_from_row(row)
        return ModelRuntimeConfig(
            model_id=row.model_id,
            display_name=row.display_name,
            generation_api=_generation_api_value(row.generation_api),
            provider_name=row.provider_name,
            category=_enum_value(row.category),
            model_name=row.model_name,
            base_url=row.base_url,
            api_key=decrypt_api_key(row.encrypted_api_key, model_id=row.model_id, master_key=self.master_key),
            is_default=bool(row.is_default),
            capability_profile=assessment.profile,
            capability_probe=assessment.evidence,
            capability_probe_hash=assessment.profile.probe_hash,
            capability_observed_at=assessment.profile.observed_at,
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
        _reject_unknown_fields(
            data,
            allowed={
                "api_key",
                "base_url",
                "category",
                "default_headers",
                "display_name",
                "enabled",
                "generation_api",
                "is_default",
                "max_retries",
                "max_tokens",
                "model_id",
                "model_name",
                "pricing_policy_id",
                "provider_name",
                "temperature",
                "timeout_seconds",
                "trust_level",
            },
        )
        model_id = _required_string(data, "model_id")
        api_key = _required_string(data, "api_key")
        category = _coerce_enum(ModelCategory, data.get("category", ModelCategory.LLM.value))
        generation_api = _generation_api_for_category(
            category=category,
            value=data.get("generation_api"),
        )
        model_name = _required_string(data, "model_name")
        base_url = validate_model_base_url(
            _required_string(data, "base_url"),
            allow_private_network=self.allow_private_network,
            require_https=self.require_https,
        )
        assessment = unverified_capability_assessment(
            model_id=model_id,
            model_name=model_name,
            base_url=base_url,
            generation_api=generation_api,
        )
        enabled = bool(data.get("enabled", True))
        is_default = bool(data.get("is_default", False))
        if is_default and not enabled:
            raise DataServiceValidationError("default model must be enabled")
        return {
            "model_id": model_id,
            "display_name": _required_string(data, "display_name"),
            "generation_api": generation_api,
            "provider_name": str(data.get("provider_name") or "Custom").strip(),
            "category": category,
            "model_name": model_name,
            "base_url": base_url,
            "encrypted_api_key": encrypt_api_key(api_key, model_id=model_id, master_key=self.master_key),
            "api_key_last4": api_key_last4(api_key),
            "api_key_fingerprint": api_key_fingerprint(api_key, master_key=self.master_key),
            "enabled": enabled,
            "is_default": is_default,
            "capability_profile_json": assessment.profile.model_dump(mode="json"),
            "capability_probe_json": assessment.evidence.model_dump(mode="json"),
            "capability_probe_hash": assessment.profile.probe_hash,
            "capability_observed_at": assessment.profile.observed_at,
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
        _reject_unknown_fields(
            data,
            allowed={
                "api_key",
                "base_url",
                "category",
                "default_headers",
                "display_name",
                "enabled",
                "generation_api",
                "is_default",
                "max_retries",
                "max_tokens",
                "model_id",
                "model_name",
                "pricing_policy_id",
                "provider_name",
                "temperature",
                "timeout_seconds",
                "trust_level",
            },
        )
        values: dict[str, Any] = {}
        simple_fields = {
            "display_name",
            "provider_name",
            "model_name",
            "enabled",
            "is_default",
            "max_tokens",
            "temperature",
            "timeout_seconds",
            "max_retries",
            "pricing_policy_id",
        }
        for field in simple_fields:
            if field in data:
                values[field] = data[field]
        if "generation_api" in data:
            values["generation_api"] = _generation_api_for_category(
                category=row.category,
                value=data["generation_api"],
            )
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
        capability_inputs = {
            "model_name",
            "base_url",
            "generation_api",
            "default_headers",
            "api_key",
        }
        if capability_inputs.intersection(data):
            effective_generation_api = values.get(
                "generation_api",
                _generation_api_value(row.generation_api),
            )
            assessment = unverified_capability_assessment(
                model_id=row.model_id,
                model_name=str(values.get("model_name", row.model_name)),
                base_url=str(values.get("base_url", row.base_url)),
                generation_api=(
                    effective_generation_api
                    if isinstance(effective_generation_api, GenerationAPI)
                    else GenerationAPI(str(effective_generation_api))
                    if effective_generation_api is not None
                    else None
                ),
            )
            values.update(
                {
                    "capability_profile_json": assessment.profile.model_dump(mode="json"),
                    "capability_probe_json": assessment.evidence.model_dump(mode="json"),
                    "capability_probe_hash": assessment.profile.probe_hash,
                    "capability_observed_at": assessment.profile.observed_at,
                    "health_status": ModelHealthStatus.UNKNOWN,
                    "last_tested_at": None,
                    "last_test_error": None,
                }
            )
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

    async def _validate_model_usage_pricing_policy(
        self,
        *,
        enabled: bool,
        pricing_policy_id: Any,
    ) -> None:
        if not enabled:
            return
        policy_key = str(pricing_policy_id or "").strip()
        if not policy_key:
            raise DataServiceValidationError("enabled model requires enabled model_usage pricing policy")
        policy = await self.pricing_repository.get_policy(policy_key)
        if policy is None:
            raise DataServiceValidationError("enabled model requires enabled model_usage pricing policy")
        policy_kind = _enum_value(getattr(policy, "policy_kind", None))
        if policy_kind != PricingPolicyKind.MODEL_USAGE.value:
            raise DataServiceValidationError("enabled model requires enabled model_usage pricing policy")
        if not bool(getattr(policy, "enabled", True)):
            raise DataServiceValidationError("enabled model requires enabled model_usage pricing policy")


def _required_string(data: dict[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise DataServiceValidationError(f"{field} is required")
    return value


def _reject_unknown_fields(data: dict[str, Any], *, allowed: set[str]) -> None:
    unknown = sorted(set(data).difference(allowed))
    if unknown:
        raise DataServiceValidationError(
            "unsupported model catalog fields: " + ", ".join(unknown)
        )


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


def _generation_api_for_category(
    *,
    category: ModelCategory | str,
    value: Any,
) -> GenerationAPI | None:
    normalized_category = _enum_value(category)
    if normalized_category == ModelCategory.IMAGE.value:
        if value not in (None, ""):
            raise DataServiceValidationError(
                "image catalog entries do not use an LLM generation_api"
            )
        return None
    if value in (None, ""):
        raise DataServiceValidationError("LLM catalog entries require generation_api")
    try:
        return value if isinstance(value, GenerationAPI) else GenerationAPI(str(value))
    except ValueError as exc:
        raise DataServiceValidationError(f"Unsupported GenerationAPI: {value}") from exc


def _generation_api_value(value: Any) -> GenerationAPI | None:
    if value is None:
        return None
    if isinstance(value, GenerationAPI):
        return value
    try:
        return GenerationAPI(str(_enum_value(value)))
    except ValueError as exc:
        raise DataServiceValidationError(f"Unsupported GenerationAPI: {value}") from exc


def _assessment_from_row(row: Any) -> CapabilityProfileAssessment:
    try:
        assessment = CapabilityProfileAssessment.model_validate(
            {
                "profile": row.capability_profile_json,
                "evidence": row.capability_probe_json,
            }
        )
    except Exception as exc:
        raise DataServiceValidationError(
            f"model {row.model_id!r} has an invalid capability assessment"
        ) from exc
    stored_hash = str(getattr(row, "capability_probe_hash", "") or "")
    if stored_hash != assessment.profile.probe_hash:
        raise DataServiceValidationError(
            f"model {row.model_id!r} capability probe hash does not match its evidence"
        )
    stored_observed_at = getattr(row, "capability_observed_at", None)
    if stored_observed_at is None or stored_observed_at != assessment.profile.observed_at:
        raise DataServiceValidationError(
            f"model {row.model_id!r} capability observation timestamp is inconsistent"
        )
    return assessment


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _redact_error(message: str | None) -> str | None:
    if message is None:
        return None
    redacted = _SECRET_PATTERN.sub(
        lambda match: redact_api_key(api_key_last4(match.group(0))) or "sk-****",
        message,
    )
    return redact_secret_text(redacted)[:500]

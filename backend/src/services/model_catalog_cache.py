"""Runtime cache for DataService-backed model catalog configs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any

from src.models.capability_profile import (
    CapabilityProfileAssessment,
    CapabilityProfileFreshness,
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelCapabilityProfile,
    assess_profile_freshness,
)
from src.security.redaction import redact_sensitive_headers

MODEL_CAPABILITY_MAX_AGE = timedelta(days=7)


@dataclass(frozen=True)
class RuntimeModelConfig:
    id: str
    name: str
    category: str
    provider: str
    model: str
    api_key: str
    base_url: str
    generation_api: GenerationAPI | None
    max_tokens: int
    temperature: float
    timeout_seconds: float | None
    max_retries: int | None
    capability_profile: ModelCapabilityProfile
    capability_probe: ModelCapabilityProbeEvidence
    capability_probe_hash: str
    capability_observed_at: datetime
    default_headers: dict[str, str]
    pricing_policy_id: str | None
    is_default: bool
    config_version: int

    def __post_init__(self) -> None:
        CapabilityProfileAssessment(
            profile=self.capability_profile,
            evidence=self.capability_probe,
        )
        if self.capability_probe_hash != self.capability_profile.probe_hash:
            raise ValueError(
                f"Model {self.id!r} capability probe hash is inconsistent"
            )
        if self.capability_observed_at != self.capability_profile.observed_at:
            raise ValueError(
                f"Model {self.id!r} capability observation timestamp is inconsistent"
            )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.id,
            "display_name": self.name,
            "category": self.category,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "generation_api": self.generation_api.value if self.generation_api else None,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "capability_profile": self.capability_profile.model_dump(mode="json"),
            "capability_probe_hash": self.capability_probe_hash,
            "capability_observed_at": self.capability_observed_at.isoformat(),
            "default_headers": redact_sensitive_headers(self.default_headers),
            "pricing_policy_id": self.pricing_policy_id,
            "is_default": self.is_default,
            "config_version": self.config_version,
        }

    def capability_freshness(
        self,
        *,
        now: datetime | None = None,
    ) -> CapabilityProfileFreshness:
        return assess_profile_freshness(
            self.capability_profile,
            self.capability_probe,
            model_id=self.id,
            model_name=self.model,
            base_url=self.base_url,
            generation_api=self.generation_api,
            now=now,
            max_age=MODEL_CAPABILITY_MAX_AGE,
        )

    def has_strict_tools(self) -> bool:
        return self.capability_freshness().current and self.capability_profile.has_strict_tools()


@dataclass(frozen=True)
class ModelCatalogSnapshot:
    by_id: dict[str, RuntimeModelConfig]
    version: int = 0
    loaded_at: datetime | None = None

    def models(self, *, category: str | None = None) -> list[RuntimeModelConfig]:
        values = list(self.by_id.values())
        if category is not None:
            values = [model for model in values if model.category == category]
        return values

    def safe_models(self, *, category: str | None = None) -> list[dict[str, Any]]:
        return [model.safe_dict() for model in self.models(category=category)]


_snapshot = ModelCatalogSnapshot(by_id={})
_lock = RLock()


def get_model_catalog_snapshot() -> ModelCatalogSnapshot:
    with _lock:
        return _snapshot


def install_model_catalog_snapshot(items: list[Any]) -> ModelCatalogSnapshot:
    configs = [_to_runtime_config(item) for item in items]
    version = max((config.config_version for config in configs), default=0)
    snapshot = ModelCatalogSnapshot(
        by_id={config.id: config for config in configs},
        version=version,
        loaded_at=datetime.now(UTC),
    )
    with _lock:
        global _snapshot
        _snapshot = snapshot
    return snapshot


async def refresh_model_catalog_cache(dataservice: Any) -> ModelCatalogSnapshot:
    items = await dataservice.list_model_catalog_runtime_models(category=None)
    return install_model_catalog_snapshot(items)


def reset_model_catalog_cache() -> None:
    with _lock:
        global _snapshot
        _snapshot = ModelCatalogSnapshot(by_id={})


def get_runtime_model_config(model_id: str) -> RuntimeModelConfig | None:
    return get_model_catalog_snapshot().by_id.get(model_id)


def get_default_runtime_model_id() -> str:
    snapshot = get_model_catalog_snapshot()
    for model in snapshot.by_id.values():
        if model.is_default:
            return model.id
    if snapshot.by_id:
        return next(iter(snapshot.by_id.keys()))
    raise ValueError("No models configured in model catalog cache")


def resolve_runtime_model_id(model_id: str | None) -> str:
    requested = (model_id or "").strip()
    if not requested or requested == "default":
        return get_default_runtime_model_id()
    if requested in get_model_catalog_snapshot().by_id:
        return requested
    raise ValueError(f"Unknown model id: {requested}")


def _to_runtime_config(item: Any) -> RuntimeModelConfig:
    if isinstance(item, RuntimeModelConfig):
        return item
    profile = item.capability_profile
    evidence = item.capability_probe
    if item.capability_probe_hash != profile.probe_hash:
        raise ValueError(
            f"Model {item.model_id!r} capability probe hash is inconsistent"
        )
    if item.capability_observed_at != profile.observed_at:
        raise ValueError(
            f"Model {item.model_id!r} capability observation timestamp is inconsistent"
        )
    return RuntimeModelConfig(
        id=item.model_id,
        name=item.display_name,
        category=item.category,
        provider=item.provider_name,
        model=item.model_name,
        api_key=item.api_key,
        base_url=item.base_url,
        generation_api=item.generation_api,
        max_tokens=item.max_tokens,
        temperature=item.temperature,
        timeout_seconds=item.timeout_seconds,
        max_retries=item.max_retries,
        capability_profile=profile,
        capability_probe=evidence,
        capability_probe_hash=item.capability_probe_hash,
        capability_observed_at=item.capability_observed_at,
        default_headers={str(key): str(value) for key, value in item.default_headers.items()},
        pricing_policy_id=getattr(item, "pricing_policy_id", None),
        is_default=item.is_default,
        config_version=item.config_version,
    )

"""Runtime cache for DataService-backed model catalog configs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class RuntimeModelConfig:
    id: str
    name: str
    category: str
    provider: str
    model: str
    api_key: str
    base_url: str
    max_tokens: int
    temperature: float
    supports_streaming: bool
    supports_tools: bool
    supports_thinking: bool
    supports_json_mode: bool
    supports_json_schema: bool
    supports_vision: bool
    supports_reasoning_effort: bool
    default_headers: dict[str, str]
    is_default: bool
    config_version: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.id,
            "display_name": self.name,
            "category": self.category,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "supports_streaming": self.supports_streaming,
            "supports_tools": self.supports_tools,
            "supports_thinking": self.supports_thinking,
            "supports_json_mode": self.supports_json_mode,
            "supports_json_schema": self.supports_json_schema,
            "supports_vision": self.supports_vision,
            "supports_reasoning_effort": self.supports_reasoning_effort,
            "default_headers": dict(self.default_headers),
            "is_default": self.is_default,
            "config_version": self.config_version,
        }


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
    return RuntimeModelConfig(
        id=item.model_id,
        name=item.display_name,
        category=item.category,
        provider=item.provider_name,
        model=item.model_name,
        api_key=item.api_key,
        base_url=item.base_url,
        max_tokens=item.max_tokens,
        temperature=item.temperature,
        supports_streaming=item.supports_streaming,
        supports_tools=item.supports_tools,
        supports_thinking=item.supports_reasoning_effort,
        supports_json_mode=item.supports_json_mode,
        supports_json_schema=item.supports_json_schema,
        supports_vision=item.supports_vision,
        supports_reasoning_effort=item.supports_reasoning_effort,
        default_headers={str(key): str(value) for key, value in item.default_headers.items()},
        is_default=item.is_default,
        config_version=item.config_version,
    )

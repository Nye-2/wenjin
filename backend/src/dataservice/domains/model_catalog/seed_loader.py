"""One-time model catalog seed import from environment config."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Any

from src.config.llm_config import resolve_model_seed
from src.dataservice.domains.model_catalog.service import DataServiceModelCatalogService

logger = logging.getLogger(__name__)

class DataServiceModelCatalogSeedLoader:
    """Seed DataService model catalog from LLM env config when empty."""

    def __init__(
        self,
        service: DataServiceModelCatalogService,
        *,
        source: Mapping[str, str] | None = None,
        admin_id: str | None = None,
        default_pricing_policy_id: str | None = None,
    ) -> None:
        self.service = service
        self.source = source if source is not None else os.environ
        self.admin_id = admin_id
        self.default_pricing_policy_id = default_pricing_policy_id

    async def load_seeds_if_empty(self) -> int:
        existing = await self.service.list_models()
        if existing:
            return 0

        seeds = self._read_seed_models()
        loaded = 0
        for seed in seeds:
            await self.service.create_model(seed, admin_id=self.admin_id)
            loaded += 1
        if loaded:
            logger.info("Loaded %d model catalog seed(s) from env config", loaded)
        return loaded

    def _read_seed_models(self) -> list[dict[str, Any]]:
        llm_rows = self._read_env_rows("LLM_MODELS")
        image_rows = self._read_env_rows("LLM_IMAGE_MODELS")
        explicit_default = str(self.source.get("LLM_DEFAULT_MODEL") or "").strip()
        all_ids = [
            *[str(row.get("id") or "").strip() for row in llm_rows],
            *[str(row.get("id") or "").strip() for row in image_rows],
        ]
        default_id = (
            explicit_default
            if explicit_default and explicit_default in all_ids
            else (str(llm_rows[0].get("id")) if llm_rows else str(image_rows[0].get("id")) if image_rows else "")
        )

        seeds: list[dict[str, Any]] = []
        for row in llm_rows:
            seed = self._seed_from_row(row, category="llm", default_id=default_id)
            if seed is not None:
                seeds.append(seed)
        for row in image_rows:
            seed = self._seed_from_row(row, category="image", default_id=default_id)
            if seed is not None:
                seeds.append(seed)
        return seeds

    def _read_env_rows(self, key: str) -> list[dict[str, Any]]:
        raw = str(self.source.get(key) or "").strip()
        if not raw:
            return []
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{key} must contain valid JSON") from exc
        if not isinstance(loaded, list):
            raise ValueError(f"{key} must be a JSON list")
        invalid_indexes = [index for index, item in enumerate(loaded) if not isinstance(item, dict)]
        if invalid_indexes:
            raise ValueError(f"{key} entries must be objects; invalid indexes: {invalid_indexes}")
        return [dict(item) for item in loaded]

    def _seed_from_row(
        self,
        row: dict[str, Any],
        *,
        category: str,
        default_id: str,
    ) -> dict[str, Any]:
        try:
            model = resolve_model_seed(row, secret_source=self.source)
        except (TypeError, ValueError):
            model_id = str(row.get("id") or "<missing>")
            raise ValueError(f"invalid {category} model catalog seed {model_id!r}") from None

        provider_name = str(row.get("provider_name") or row.get("provider") or "Custom").strip()
        enabled = bool(row.get("enabled", True))
        pricing_policy_id = row.get("pricing_policy_id") or row.get("pricing_policy_key")
        if enabled and not str(pricing_policy_id or "").strip():
            pricing_policy_id = self.default_pricing_policy_id
        return {
            "model_id": model.id,
            "display_name": model.name or model.id,
            "generation_api": model.generation_api.value if category == "llm" and model.generation_api else None,
            "provider_name": provider_name or "Custom",
            "category": category,
            "model_name": model.model,
            "base_url": model.base_url,
            "api_key": model.api_key,
            "enabled": enabled,
            "is_default": model.id == default_id,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "timeout_seconds": model.timeout_seconds,
            "max_retries": model.max_retries,
            "trust_level": str(row.get("trust_level") or "custom"),
            "pricing_policy_id": pricing_policy_id,
            "default_headers": dict(model.default_headers or {}),
        }

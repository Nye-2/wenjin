"""One-time model catalog seed import from environment config."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Any

from src.config.llm_config import ModelConfig
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
    ) -> None:
        self.service = service
        self.source = source if source is not None else os.environ
        self.admin_id = admin_id

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
            logger.warning("Failed to parse %s JSON for model catalog seed: %s", key, exc)
            return []
        if not isinstance(loaded, list):
            logger.warning("%s must be a JSON list for model catalog seed", key)
            return []
        return [dict(item) for item in loaded if isinstance(item, dict)]

    def _seed_from_row(
        self,
        row: dict[str, Any],
        *,
        category: str,
        default_id: str,
    ) -> dict[str, Any] | None:
        try:
            model = ModelConfig.model_validate(row)
        except Exception as exc:
            logger.warning("Skipping invalid model catalog seed row: %s", exc)
            return None

        provider_name = str(row.get("provider_name") or row.get("provider") or "Custom").strip()
        supports_reasoning_effort = bool(
            row.get("supports_reasoning_effort", row.get("supports_thinking", False))
        )
        return {
            "model_id": model.id,
            "display_name": model.name or model.id,
            "provider_protocol": str(row.get("provider_protocol") or "openai_compatible"),
            "provider_name": provider_name or "Custom",
            "category": category,
            "model_name": model.model,
            "base_url": model.base_url,
            "api_key": model.api_key,
            "enabled": bool(row.get("enabled", True)),
            "is_default": model.id == default_id,
            "supports_streaming": model.supports_streaming,
            "supports_tools": model.supports_tools,
            "supports_json_mode": model.supports_json_mode,
            "supports_json_schema": model.supports_json_schema,
            "supports_vision": model.supports_vision,
            "supports_reasoning_effort": supports_reasoning_effort,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "timeout_seconds": row.get("timeout_seconds"),
            "max_retries": row.get("max_retries"),
            "trust_level": str(row.get("trust_level") or "custom"),
            "pricing_policy_id": row.get("pricing_policy_id") or row.get("pricing_policy_key"),
            "default_headers": dict(model.default_headers or {}),
        }

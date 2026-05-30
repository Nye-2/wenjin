"""Agent template YAML loader — seeds recruitable team templates through DataService."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import CatalogSeedItemPayload, CatalogSeedLoadPayload
from src.dataservice_client.provider import dataservice_client

logger = logging.getLogger(__name__)

DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "agent_templates"


class AgentTemplateLoader:
    """Loads DataService-owned agent template seeds."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        seed_dir: Path | str | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.session = session
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
        self._dataservice = dataservice

    async def load_seeds_if_empty(self) -> int:
        if self._dataservice is not None:
            has_templates = await self._dataservice.has_agent_templates()
        else:
            async with dataservice_client() as client:
                has_templates = await client.has_agent_templates()
        if has_templates:
            return 0
        return await self._load_all_dataservice(overwrite=False)

    async def load_all(self, overwrite: bool = False) -> list:
        await self._load_all_dataservice(overwrite=overwrite)
        if self._dataservice is not None:
            return await self._dataservice.list_agent_templates()
        async with dataservice_client() as client:
            return await client.list_agent_templates()

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
        if not self.seed_dir.exists():
            logger.warning("Agent template seed dir does not exist: %s", self.seed_dir)
            return 0
        command = CatalogSeedLoadPayload(
            seed_root=str(self.seed_dir),
            overwrite=overwrite,
            items=[
                CatalogSeedItemPayload(
                    data=item["data"],
                    checksum=item["checksum"],
                    source_path=item["source_path"],
                )
                for item in self._read_seed_items()
            ],
        )
        if self._dataservice is not None:
            result = await self._dataservice.load_agent_template_seed_items(command)
        else:
            async with dataservice_client() as client:
                result = await client.load_agent_template_seed_items(command)
        if result.loaded > 0:
            logger.info(
                "Loaded %d DataService agent template seed(s) from %s",
                result.loaded,
                self.seed_dir,
            )
        return result.loaded

    def _read_seed_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for yaml_path in sorted(self.seed_dir.glob("*.yaml")):
            text = yaml_path.read_text(encoding="utf-8")
            items.append(
                {
                    "data": self._validate_yaml_text(yaml_path, text),
                    "checksum": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "source_path": str(yaml_path),
                }
            )
        return items

    def _validate_yaml_text(self, path: Path, text: str) -> dict[str, Any]:
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")
        if raw.get("schema_version") != "agent_template.v1":
            raise ValueError(f"Invalid agent_template.v1 seed in {path}: schema_version is required")
        for key in ("id", "display_role", "category"):
            if not str(raw.get(key) or "").strip():
                raise ValueError(f"Invalid agent_template.v1 seed in {path}: {key} is required")
        for key in ("tool_affinity", "risk_profile"):
            if not isinstance(raw.get(key), dict):
                raise ValueError(f"Invalid agent_template.v1 seed in {path}: {key} must be an object")
        return raw

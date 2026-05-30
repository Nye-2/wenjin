"""Skill YAML loader — seeds capability_skills from YAML files into DB."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import CatalogSeedItemPayload, CatalogSeedLoadPayload
from src.dataservice_client.provider import dataservice_client
from src.services.capability_schema import CapabilitySkillV2YamlModel

logger = logging.getLogger(__name__)

DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "skills"

class SkillLoader:
    """Loads CapabilitySkill seed files through DataService."""

    def __init__(
        self,
        *,
        seed_dir: Path | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
        self._dataservice = dataservice

    async def load_seeds_if_empty(self) -> int:
        if self._dataservice is not None:
            has_skills = await self._dataservice.has_catalog_skills()
        else:
            async with dataservice_client() as client:
                has_skills = await client.has_catalog_skills()
        if has_skills:
            return 0
        return await self._load_all_dataservice(overwrite=False)

    async def load_all(self, overwrite: bool = False) -> list:
        """Load all skill YAML seeds and return catalog rows."""
        await self._load_all_dataservice(overwrite=overwrite)
        if self._dataservice is not None:
            return await self._dataservice.list_catalog_skills()
        async with dataservice_client() as client:
            return await client.list_catalog_skills()

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
        if not self.seed_dir.exists():
            logger.warning("Skill seed dir does not exist: %s", self.seed_dir)
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
            result = await self._dataservice.load_catalog_skill_seed_items(command)
        else:
            async with dataservice_client() as client:
                result = await client.load_catalog_skill_seed_items(command)
        if result.loaded > 0:
            logger.info("Loaded %d DataService skill seed(s) from %s", result.loaded, self.seed_dir)
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

    def _read_and_validate(self, path: Path) -> dict[str, Any]:
        return self._validate_yaml_text(path, path.read_text(encoding="utf-8"))

    def _validate_yaml_text(self, path: Path, text: str) -> dict[str, Any]:
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")
        try:
            return CapabilitySkillV2YamlModel(**raw).to_catalog_data()
        except Exception as exc:
            raise ValueError(f"Invalid capability_skill.v2 seed in {path}: {exc}") from exc

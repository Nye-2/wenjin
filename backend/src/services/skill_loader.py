"""Load bounded worker_skill.v1 resources from YAML."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from src.contracts.mission_policy import WorkerSkill
from src.dataservice.domains.catalog.service import MissionCatalogService
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import CatalogSeedItemPayload, CatalogSeedLoadPayload
from src.dataservice_client.provider import dataservice_client

logger = logging.getLogger(__name__)

DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "skills"


class SkillLoader:
    """Load worker skills without fixed subagent type, DAG, or lifecycle truth."""

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
            has_skills = await self._dataservice.has_worker_skills()
        else:
            async with dataservice_client() as client:
                has_skills = await client.has_worker_skills()
        if has_skills:
            return 0
        return await self._load_all_dataservice(overwrite=False)

    async def load_all(self, overwrite: bool = False) -> list[object]:
        await self._load_all_dataservice(overwrite=overwrite)
        if self._dataservice is not None:
            return await self._dataservice.list_worker_skills()
        async with dataservice_client() as client:
            return await client.list_worker_skills()

    async def sync_seed_updates(self) -> int:
        if self._dataservice is not None:
            return await self._sync_seed_updates(self._dataservice)
        async with dataservice_client() as client:
            return await self._sync_seed_updates(client)

    async def sync_with_service(self, service: MissionCatalogService) -> int:
        """Synchronize seed-owned skills through the caller's database transaction."""
        items = self.select_seed_updates(await service.list_skills())
        if not items:
            return 0
        return await service.load_skills(items, overwrite=False)

    async def _sync_seed_updates(self, client: AsyncDataServiceClient) -> int:
        seed_items = self.select_seed_updates(await client.list_worker_skills())
        if not seed_items:
            return 0
        result = await client.load_worker_skill_seed_items(self._seed_command(seed_items, overwrite=False))
        return result.loaded

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
        if not self.seed_dir.exists():
            raise ValueError(f"Worker skill seed dir does not exist: {self.seed_dir}")
        items = self.read_seed_items()
        command = self._seed_command(items, overwrite=overwrite)
        if self._dataservice is not None:
            result = await self._dataservice.load_worker_skill_seed_items(command)
        else:
            async with dataservice_client() as client:
                result = await client.load_worker_skill_seed_items(command)
        if result.loaded:
            logger.info("Loaded %d worker skill seed(s) from %s", result.loaded, self.seed_dir)
        return result.loaded

    def _seed_command(
        self,
        items: list[dict[str, Any]],
        *,
        overwrite: bool,
    ) -> CatalogSeedLoadPayload:
        return CatalogSeedLoadPayload(
            overwrite=overwrite,
            items=[
                CatalogSeedItemPayload(
                    data=item["data"],
                    source_path=item["source_path"],
                )
                for item in items
            ],
        )

    def select_seed_updates(self, existing_records: list[object]) -> list[dict[str, Any]]:
        existing = {str(getattr(record, "id", "")): record for record in existing_records}
        updates: list[dict[str, Any]] = []
        for item in self.read_seed_items():
            record = existing.get(str(item["data"]["id"]))
            if record is None:
                updates.append(item)
                continue
            source_path = str(getattr(record, "source_path", "") or "")
            content_hash = str(getattr(record, "content_hash", "") or "")
            if source_path == item["source_path"] and content_hash != item["data"]["content_hash"]:
                updates.append(item)
        return updates

    def read_seed_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for yaml_path in sorted(self.seed_dir.glob("*.yaml")):
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"Expected dict in {yaml_path}")
            try:
                skill = WorkerSkill.model_validate(raw)
            except Exception as exc:
                raise ValueError(f"Invalid worker_skill.v1 seed in {yaml_path}: {exc}") from exc
            items.append(
                {
                    "data": skill.to_catalog_data(),
                    "source_path": str(yaml_path),
                }
            )
        if not items:
            raise ValueError(f"No worker_skill.v1 seeds found in {self.seed_dir}")
        return items

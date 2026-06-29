"""Capability YAML loader — seeds capabilities from YAML files into DB."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import yaml

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import CatalogSeedItemPayload, CatalogSeedLoadPayload
from src.dataservice_client.provider import dataservice_client
from src.services.capability_schema import CapabilityV2YamlModel

logger = logging.getLogger(__name__)

# Derive absolute path from this file's location so the loader works regardless
# of where the process is started from. This file lives at:
#   backend/src/services/capability_loader.py
# Three parents up → backend/, then seed/capabilities.
DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "capabilities"

class CapabilityLoader:
    """Loads capability definitions from YAML seed files through DataService.

    Args:
        seed_dir: Path to the directory containing capability YAML seeds.
        dataservice: Optional DataService client override for tests.
    """

    def __init__(
        self,
        seed_dir: Path | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
        self._dataservice = dataservice

    async def load_seeds_if_empty(self) -> int:
        """Load YAML seeds into DB if capabilities table is empty.

        Returns:
            Number of capabilities loaded (0 if table already had data).
        """
        if self._dataservice is not None:
            has_capabilities = await self._dataservice.has_catalog_capabilities()
        else:
            async with dataservice_client() as client:
                has_capabilities = await client.has_catalog_capabilities()
        if has_capabilities:
            return 0
        return await self._load_all_dataservice(overwrite=False)

    async def load_all(self, overwrite: bool = False) -> list:
        """Load all YAML seeds, optionally overwriting existing rows.

        Args:
            overwrite: If True, delete existing capabilities before loading.

        Returns:
            List of loaded ORM instances.
        """
        await self._load_all_dataservice(overwrite=overwrite)
        if self._dataservice is not None:
            return await self._dataservice.list_catalog_capabilities()
        async with dataservice_client() as client:
            return await client.list_catalog_capabilities()

    async def sync_seed_updates(self) -> int:
        """Upsert missing or changed seed-owned capabilities without deleting admin rows."""
        if self._dataservice is not None:
            return await self._sync_seed_updates_dataservice(self._dataservice)
        async with dataservice_client() as client:
            return await self._sync_seed_updates_dataservice(client)

    async def _sync_seed_updates_dataservice(self, client: AsyncDataServiceClient) -> int:
        seed_items = self._select_seed_updates(await client.list_catalog_capabilities())
        if not seed_items:
            return 0
        command = CatalogSeedLoadPayload(
            seed_root=str(self.seed_dir),
            overwrite=False,
            items=[
                CatalogSeedItemPayload(
                    data=item["data"],
                    checksum=item["checksum"],
                    source_path=item["source_path"],
                )
                for item in seed_items
            ],
        )
        result = await client.load_catalog_capability_seed_items(command)
        return result.loaded

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
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
            result = await self._dataservice.load_catalog_capability_seed_items(command)
        else:
            async with dataservice_client() as client:
                result = await client.load_catalog_capability_seed_items(command)
        if result.loaded > 0:
            logger.info("Loaded %d DataService capability seed(s) from %s", result.loaded, self.seed_dir)
        return result.loaded

    def _select_seed_updates(self, existing_records: list[object]) -> list[dict]:
        existing = {
            (str(getattr(record, "workspace_type", "")), str(getattr(record, "id", ""))): record
            for record in existing_records
        }
        updates: list[dict] = []
        for item in self._read_seed_items():
            data = item["data"]
            key = (str(data["workspace_type"]), str(data["id"]))
            record = existing.get(key)
            if record is None:
                updates.append(item)
                continue
            source_path = str(getattr(record, "source_path", "") or "")
            checksum = str(getattr(record, "checksum", "") or "")
            if source_path == item["source_path"] and checksum != item["checksum"]:
                updates.append(item)
        return updates

    def _read_seed_items(self) -> list[dict]:
        items: list[dict] = []
        for yaml_path in sorted(self.seed_dir.glob("*/*.yaml")):
            text = yaml_path.read_text(encoding="utf-8")
            items.append(
                {
                    "data": self._validate_yaml_text(yaml_path, text),
                    "checksum": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "source_path": str(yaml_path),
                }
            )
        return items

    def _read_and_validate(self, path: Path) -> dict:
        """Read and validate a single YAML capability file.

        Returns:
            Validated data dict ready for model constructor.

        Raises:
            ValueError: If required fields are missing.
        """
        return self._validate_yaml_text(path, path.read_text(encoding="utf-8"))

    def _validate_yaml_text(self, path: Path, text: str) -> dict:
        raw = yaml.safe_load(text)

        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")

        try:
            return CapabilityV2YamlModel(**raw).to_catalog_data()
        except Exception as exc:
            raise ValueError(f"Invalid capability.v2 seed in {path}: {exc}") from exc

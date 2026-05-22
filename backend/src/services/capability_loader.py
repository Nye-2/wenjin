"""Capability YAML loader — seeds capabilities from YAML files into DB."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import CatalogSeedItemPayload, CatalogSeedLoadPayload
from src.dataservice_client.provider import dataservice_client

logger = logging.getLogger(__name__)

# Derive absolute path from this file's location so the loader works regardless
# of where the process is started from. This file lives at:
#   backend/src/services/capability_loader.py
# Three parents up → backend/, then seed/capabilities.
DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "capabilities"

REQUIRED_FIELDS = {
    "id",
    "workspace_type",
    "display_name",
    "intent_description",
    "brief_schema",
    "graph_template",
    "ui_meta",
}

OPTIONAL_DEFAULTS = {
    "enabled": True,
    "description": "",
    "trigger_phrases": [],
    "required_decisions": [],
    "runtime": {},
    "dashboard_meta": {},
    "notes": None,
}


class CapabilityLoader:
    """Loads capability definitions from YAML seed files into the database.

    Args:
        session: AsyncSession for database access.
        seed_dir: Path to the directory containing capability YAML seeds.
        dataservice: Optional DataService client override for tests.
    """

    def __init__(
        self,
        session: AsyncSession,
        seed_dir: Path | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.session = session
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

        missing = REQUIRED_FIELDS - set(raw.keys())
        if missing:
            raise ValueError(
                f"Missing required fields in {path}: {', '.join(sorted(missing))}"
            )

        # Apply optional defaults for fields not present in YAML
        for field, default in OPTIONAL_DEFAULTS.items():
            if field not in raw:
                raw[field] = default

        return raw

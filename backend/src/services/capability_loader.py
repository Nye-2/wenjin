"""Capability YAML loader — seeds capabilities from YAML files into DB."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        model: Optional test ORM model. Production writes through DataService catalog.
    """

    def __init__(
        self,
        session: AsyncSession,
        seed_dir: Path | None = None,
        model=None,
    ) -> None:
        self.session = session
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
        self._model = model

    async def load_seeds_if_empty(self) -> int:
        """Load YAML seeds into DB if capabilities table is empty.

        Returns:
            Number of capabilities loaded (0 if table already had data).
        """
        if self._model is None:
            from src.dataservice.catalog_api import CatalogDataService

            catalog = CatalogDataService(self.session)
            if await catalog.has_capabilities():
                return 0
            return await self._load_all_dataservice(overwrite=False)

        existing = (await self.session.execute(select(self._model).limit(1))).first()
        if existing:
            return 0
        return await self._load_all()

    async def load_all(self, overwrite: bool = False) -> list:
        """Load all YAML seeds, optionally overwriting existing rows.

        Args:
            overwrite: If True, delete existing capabilities before loading.

        Returns:
            List of loaded ORM instances.
        """
        if self._model is None:
            await self._load_all_dataservice(overwrite=overwrite)
            from src.dataservice.catalog_api import CatalogDataService

            return await CatalogDataService(self.session).list_capabilities()

        if overwrite:
            from sqlalchemy import delete as sa_delete
            await self.session.execute(sa_delete(self._model))
        await self._load_all()
        result = await self.session.execute(select(self._model))
        return list(result.scalars().all())

    async def _load_all(self) -> int:
        """Scan seed_dir/*/*.yaml, validate, and insert into DB.

        Returns:
            Number of capabilities loaded.

        Raises:
            ValueError: If a YAML file is missing required fields.
        """
        count = 0
        for yaml_path in sorted(self.seed_dir.glob("*/*.yaml")):
            data = self._read_and_validate(yaml_path)
            cap = self._model(**data)
            self.session.add(cap)
            count += 1
        if count > 0:
            await self.session.commit()
            logger.info("Loaded %d capability seed(s) from %s", count, self.seed_dir)
        return count

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
        from src.dataservice.catalog_api import CatalogDataService

        catalog = CatalogDataService(self.session)
        result = await catalog.load_capability_seed_dir(
            self.seed_dir,
            validate_yaml_text=self._validate_yaml_text,
            overwrite=overwrite,
        )
        if result.loaded > 0:
            logger.info("Loaded %d DataService capability seed(s) from %s", result.loaded, self.seed_dir)
        return result.loaded

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

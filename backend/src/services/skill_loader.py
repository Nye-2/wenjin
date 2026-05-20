"""Skill YAML loader — seeds capability_skills from YAML files into DB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "skills"

REQUIRED_FIELDS = {"id", "display_name", "subagent_type"}

OPTIONAL_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "description": "",
    "prompt": "",
    "allowed_tools": [],
    "resources": [],
    "config": {},
}


class SkillLoader:
    """Loads CapabilitySkill rows from YAML files in seed_dir."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        seed_dir: Path | None = None,
        model: Any | None = None,
    ) -> None:
        self.session = session
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
        self._model = model

    async def load_seeds_if_empty(self) -> int:
        if self._model is None:
            from src.dataservice.catalog_api import CatalogDataService

            catalog = CatalogDataService(self.session)
            if await catalog.has_skills():
                return 0
            return await self._load_all_dataservice(overwrite=False)

        existing = (await self.session.execute(select(self._model).limit(1))).first()
        if existing:
            return 0
        return await self._load_all()

    async def load_all(self, overwrite: bool = False) -> list:
        """Load all skill YAML seeds and return catalog rows."""
        if self._model is None:
            await self._load_all_dataservice(overwrite=overwrite)
            from src.dataservice.catalog_api import CatalogDataService

            return await CatalogDataService(self.session).list_skills()

        if overwrite:
            from sqlalchemy import delete as sa_delete

            await self.session.execute(sa_delete(self._model))
        await self._load_all()
        result = await self.session.execute(select(self._model))
        return list(result.scalars().all())

    async def _load_all(self) -> int:
        if self._model is None:
            return await self._load_all_dataservice(overwrite=False)

        count = 0
        if not self.seed_dir.exists():
            logger.warning("Skill seed dir does not exist: %s", self.seed_dir)
            return 0
        for yaml_path in sorted(self.seed_dir.glob("*.yaml")):
            data = self._read_and_validate(yaml_path)
            self.session.add(self._model(**data))
            count += 1
        if count > 0:
            await self.session.commit()
            logger.info("Loaded %d skill seed(s) from %s", count, self.seed_dir)
        return count

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
        from src.dataservice.catalog_api import CatalogDataService

        if not self.seed_dir.exists():
            logger.warning("Skill seed dir does not exist: %s", self.seed_dir)
            return 0
        catalog = CatalogDataService(self.session)
        result = await catalog.load_skill_seed_dir(
            self.seed_dir,
            validate_yaml_text=self._validate_yaml_text,
            overwrite=overwrite,
        )
        if result.loaded > 0:
            logger.info("Loaded %d DataService skill seed(s) from %s", result.loaded, self.seed_dir)
        return result.loaded

    def _read_and_validate(self, path: Path) -> dict[str, Any]:
        return self._validate_yaml_text(path, path.read_text(encoding="utf-8"))

    def _validate_yaml_text(self, path: Path, text: str) -> dict[str, Any]:
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")
        missing = REQUIRED_FIELDS - set(raw.keys())
        if missing:
            raise ValueError(f"Missing required fields in {path}: {', '.join(sorted(missing))}")
        for field, default in OPTIONAL_DEFAULTS.items():
            if field not in raw:
                raw[field] = default
        return raw

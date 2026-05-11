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
        if model is None:
            from src.database.models.capability_skill import CapabilitySkill
            self._model = CapabilitySkill
        else:
            self._model = model

    async def load_seeds_if_empty(self) -> int:
        existing = (await self.session.execute(select(self._model).limit(1))).first()
        if existing:
            return 0
        return await self._load_all()

    async def _load_all(self) -> int:
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

    def _read_and_validate(self, path: Path) -> dict[str, Any]:
        with open(path) as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")
        missing = REQUIRED_FIELDS - set(raw.keys())
        if missing:
            raise ValueError(f"Missing required fields in {path}: {', '.join(sorted(missing))}")
        for field, default in OPTIONAL_DEFAULTS.items():
            if field not in raw:
                raw[field] = default
        return raw

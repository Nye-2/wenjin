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
    "result_card_template",
}

OPTIONAL_DEFAULTS = {
    "enabled": True,
    "trigger_phrases": [],
    "required_decisions": [],
    "notes": None,
}


class CapabilityLoader:
    """Loads capability definitions from YAML seed files into the database.

    Args:
        session: AsyncSession for database access.
        seed_dir: Path to the directory containing capability YAML seeds.
        model: The ORM model class to use (defaults to production Capability).
    """

    def __init__(
        self,
        session: AsyncSession,
        seed_dir: Path | None = None,
        model=None,
    ) -> None:
        self.session = session
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
        if model is None:
            from ..database.models.capability import Capability
            self._model = Capability
        else:
            self._model = model

    async def load_seeds_if_empty(self) -> int:
        """Load YAML seeds into DB if capabilities table is empty.

        Returns:
            Number of capabilities loaded (0 if table already had data).
        """
        existing = (
            await self.session.execute(select(self._model).limit(1))
        ).first()
        if existing:
            return 0
        return await self._load_all()

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

    def _read_and_validate(self, path: Path) -> dict:
        """Read and validate a single YAML capability file.

        Returns:
            Validated data dict ready for model constructor.

        Raises:
            ValueError: If required fields are missing.
        """
        with open(path) as f:
            raw = yaml.safe_load(f)

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

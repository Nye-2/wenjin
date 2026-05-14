"""Read capabilities.runtime + dashboard_meta from DB and write into seed YAMLs.

Runs after the registry backfill (Task 6.3) so seed files are kept in sync
with the DB. After 6.10, the registry-driven backfill script no longer works;
the seed YAMLs become the authoritative source.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seed" / "capabilities"

sys.path.insert(0, str(ROOT / "src"))
from database import get_db_session  # noqa: E402
from database.models import Capability  # noqa: E402


async def main() -> int:
    updated = 0
    async with get_db_session() as db:
        result = await db.execute(select(Capability))
        for cap in result.scalars().all():
            seed_path = SEED_DIR / cap.workspace_type / f"{cap.id}.yaml"
            if not seed_path.exists():
                print(f"SKIP: {cap.workspace_type}/{cap.id} (no seed)")
                continue
            with seed_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            data["runtime"] = cap.runtime
            data["dashboard_meta"] = cap.dashboard_meta
            with seed_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
            print(f"OK: {cap.workspace_type}/{cap.id}")
            updated += 1
    print(f"\nUpdated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""One-off backfill: read workspace_features.registry + runtime_profiles
to populate capabilities.runtime and capabilities.dashboard_meta.

Runs once during P6 Task 6.3. After P6 Task 6.10 deletes workspace_features/,
this script can no longer run.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from database import get_db_session  # noqa: E402
from database.models import Capability  # noqa: E402
from workspace_features.registry import iter_workspace_features  # noqa: E402
from workspace_features.runtime_profiles import get_feature_runtime_profile  # noqa: E402


def _profile_mode(profile) -> str:
    """Extract mode string from a FeatureRuntimeProfile (v1) or default to chat_only."""
    if profile is None:
        return "chat_only"
    mode = getattr(profile, "runtime_mode", None) or getattr(profile, "mode", None)
    if mode is None:
        return "chat_only"
    return mode.value if hasattr(mode, "value") else str(mode)


def _profile_review_gate(profile) -> dict:
    """Coerce v1 review_gate (str|None) to v2 dict."""
    if profile is None:
        return {}
    gate = getattr(profile, "review_gate", None)
    if gate is None:
        return {}
    if isinstance(gate, dict):
        return gate
    # v1 review_gate is a string like "artifact_preview" -> wrap as {"kind": ...}
    return {"kind": str(gate)}


async def main() -> int:
    updated = 0
    missing = 0
    async with get_db_session() as db:
        for feature in iter_workspace_features():
            stmt = select(Capability).where(
                Capability.id == feature.id,
                Capability.workspace_type == feature.workspace_type,
            )
            result = await db.execute(stmt)
            cap = result.scalars().first()
            if cap is None:
                print(f"MISS: {feature.workspace_type}/{feature.id}")
                missing += 1
                continue
            profile = get_feature_runtime_profile(feature.workspace_type, feature.id)
            cap.runtime = {
                "mode": _profile_mode(profile),
                "requires_sandbox": getattr(profile, "requires_sandbox", False) if profile else False,
                "review_gate": _profile_review_gate(profile),
                "allowed_paths": list(getattr(profile, "allowed_paths", []) or []) if profile else [],
            }
            cap.dashboard_meta = {
                "status_kind": feature.id,
                "panel": feature.panel,
            }
            updated += 1
            print(f"OK: {feature.workspace_type}/{feature.id}")
        await db.commit()
    print(f"\nUpdated: {updated}  Missing: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

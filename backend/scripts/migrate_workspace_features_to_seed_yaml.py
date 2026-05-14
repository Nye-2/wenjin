"""One-off ETL: pull icon/color/stages/follow_up_prompt from WorkspaceFeatureDefinition
and merge into corresponding capability seed YAMLs (matched by id).

Run once during Phase 1 of admin dashboard rebuild. Idempotent.

NOTE: This script ran once during P1.1 (commit ee4fa7f). The `order` field
computation here was buggy (used a global index instead of per-workspace).
The actual order values were later corrected per-workspace in a follow-up commit.
Do NOT re-run this script — the YAML files are now the source of truth for ui_meta.
This script remains only as historical record and will be deleted alongside
registry.py in P1.6.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seed" / "capabilities"

sys.path.insert(0, str(ROOT / "src"))
from workspace_features.registry import (
    THESIS_FEATURES,
    SCI_FEATURES,
    PROPOSAL_FEATURES,
    SOFTWARE_COPYRIGHT_FEATURES,
    PATENT_FEATURES,
)

ALL = (
    *THESIS_FEATURES,
    *SCI_FEATURES,
    *PROPOSAL_FEATURES,
    *SOFTWARE_COPYRIGHT_FEATURES,
    *PATENT_FEATURES,
)


def build_ui_meta(feature) -> dict:
    return {
        "icon": feature.icon,
        "color": feature.color or "purple",
        "order": 0,
        "stages": [{"id": s.id, "label": s.label} for s in feature.stages],
        "follow_up_prompt": feature.follow_up_prompt,
    }


def main() -> int:
    updated = 0
    skipped = 0
    for feature in ALL:
        seed_path = SEED_DIR / feature.workspace_type / f"{feature.id}.yaml"
        if not seed_path.exists():
            print(f"SKIP (no seed): {feature.workspace_type}/{feature.id}")
            skipped += 1
            continue
        with seed_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data.get("id") != feature.id:
            print(f"WARN id mismatch in {seed_path}: yaml.id={data.get('id')} feature.id={feature.id}")
        data["ui_meta"] = build_ui_meta(feature)
        for i, f in enumerate(ALL):
            if f.workspace_type == feature.workspace_type:
                if f.id == feature.id:
                    data["ui_meta"]["order"] = i
                    break
        with seed_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        print(f"OK: {feature.workspace_type}/{feature.id}")
        updated += 1
    print(f"\nUpdated: {updated}  Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

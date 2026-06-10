"""Dataset manifest synchronization for sandbox Python jobs."""

from __future__ import annotations

import json
from typing import Any

from src.sandbox.workspace_layout import (
    WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
    build_dataset_provenance_manifest,
    merge_dataset_provenance_manifest,
)


async def sync_dataset_manifest(
    *,
    sandbox: Any,
    dataset_provenance: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge bounded workspace dataset provenance into the sandbox manifest."""

    if not dataset_provenance:
        return []
    accepted_manifest = merge_dataset_provenance_manifest(
        build_dataset_provenance_manifest(),
        dataset_provenance,
    )
    accepted_entries = [
        dict(item)
        for item in accepted_manifest.get("datasets") or []
        if isinstance(item, dict)
    ]
    if not accepted_entries:
        return []
    try:
        existing_text = await sandbox.read_file(WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH)
        existing = json.loads(existing_text)
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        existing = build_dataset_provenance_manifest()
    merged = merge_dataset_provenance_manifest(existing, dataset_provenance)
    if merged != existing:
        await sandbox.write_file(
            WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH,
            json.dumps(merged, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        )
    return accepted_entries

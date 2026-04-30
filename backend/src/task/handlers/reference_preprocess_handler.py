"""Reference-library preprocessing task handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.database import get_db_session
from src.services.references import ReferencePreprocessService


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"Reference preprocess payload missing {key}")
    return value


async def execute_reference_preprocess(payload: dict[str, Any], progress) -> dict[str, Any]:
    """Execute asynchronous preprocessing for one reference asset."""
    workspace_id = _required_text(payload, "workspace_id")
    reference_id = _required_text(payload, "reference_id")
    asset_id = _required_text(payload, "asset_id")
    source_path = Path(_required_text(payload, "source_path"))
    output_dir = Path(_required_text(payload, "output_dir"))
    output_virtual_root = _required_text(payload, "output_virtual_root")
    filename = _required_text(payload, "filename")
    content_type = str(payload.get("content_type") or "").strip() or None
    task_id = str(payload.get("task_id") or "").strip() or None

    if not source_path.is_file():
        raise ValueError(f"Reference source file not found: {source_path}")

    await progress.update(
        10,
        "Loading reference asset",
        current_step="load",
        metadata={
            "reference_preprocess": {
                "status": "running",
                "reference_id": reference_id,
                "asset_id": asset_id,
            }
        },
    )

    async with get_db_session() as db:
        service = ReferencePreprocessService(db)
        await progress.update(35, "Parsing reference full text", current_step="preprocess")
        preprocess = await service.process_asset(
            workspace_id=workspace_id,
            reference_id=reference_id,
            asset_id=asset_id,
            filename=filename,
            content_type=content_type,
            source_path=source_path,
            output_dir=output_dir,
            output_virtual_root=output_virtual_root,
            task_id=task_id,
            commit=True,
        )

    await progress.update(
        95,
        "Finalizing reference index",
        current_step="finalize",
        metadata={"reference_preprocess": preprocess},
    )
    return {
        "success": True,
        "workspace_id": workspace_id,
        "thread_id": str(payload.get("thread_id") or "").strip() or None,
        "reference_id": reference_id,
        "asset_id": asset_id,
        "preprocess": preprocess,
        "message": "Reference preprocessing completed",
        "refresh_targets": ["dashboard", "references"],
    }

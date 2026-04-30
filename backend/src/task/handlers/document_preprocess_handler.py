"""Document preprocessing task handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.services.upload_preprocessor import get_upload_preprocessor_service
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    workspace_upload_public_url,
)


def _read_required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"Document preprocess payload missing {key}")
    return value


def _attach_workspace_preprocess_urls(
    *,
    workspace_id: str | None,
    metadata: dict[str, object],
    workspace_upload_root: Path,
) -> None:
    if not workspace_id:
        return

    for key in ("markdown_paths", "markdown_image_paths", "output_image_paths"):
        values = metadata.get(key)
        if not isinstance(values, list):
            continue
        urls: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            try:
                url = workspace_upload_public_url(
                    workspace_id,
                    value,
                    root=workspace_upload_root,
                )
            except ValueError:
                continue
            if url:
                urls.append(url)
        if urls:
            metadata[f"{key.removesuffix('_paths')}_urls"] = urls

    manifest_path = metadata.get("manifest_path")
    if isinstance(manifest_path, str) and manifest_path.strip():
        try:
            manifest_url = workspace_upload_public_url(
                workspace_id,
                manifest_path,
                root=workspace_upload_root,
            )
        except ValueError:
            manifest_url = None
        if manifest_url:
            metadata["manifest_url"] = manifest_url


async def execute_document_preprocess(payload: dict[str, Any], progress) -> dict[str, Any]:
    """Execute asynchronous preprocessing for one uploaded document."""
    source_path = Path(_read_required_text(payload, "source_path"))
    output_dir = Path(_read_required_text(payload, "output_dir"))
    filename = _read_required_text(payload, "filename")
    content_type = str(payload.get("content_type") or "").strip() or None
    output_virtual_root = str(payload.get("output_virtual_root") or "").strip() or None
    workspace_id = str(payload.get("workspace_id") or "").strip() or None
    workspace_upload_root = Path(str(payload.get("workspace_upload_root") or DEFAULT_WORKSPACE_UPLOAD_ROOT))

    if not source_path.is_file():
        raise ValueError(f"Uploaded source file not found: {source_path}")

    await progress.update(
        10,
        "Loading uploaded document",
        current_step="load",
        metadata={
            "preprocess": {
                "status": "pending",
                "provider": str(payload.get("provider") or "layout_parsing"),
                "file_type": str(payload.get("file_type") or "pdf"),
            }
        },
    )

    preprocessor = get_upload_preprocessor_service()
    await progress.update(
        30,
        "Preprocessing uploaded document",
        current_step="preprocess",
    )
    result = await preprocessor.preprocess_file(
        filename=filename,
        content_type=content_type,
        source_path=source_path,
        output_dir=output_dir,
        output_virtual_root=output_virtual_root,
    )
    preprocess_metadata = result.to_metadata()
    task_id = str(payload.get("task_id") or "").strip()
    if task_id:
        preprocess_metadata["task_id"] = task_id
    _attach_workspace_preprocess_urls(
        workspace_id=workspace_id,
        metadata=preprocess_metadata,
        workspace_upload_root=workspace_upload_root,
    )

    if result.markdown_paths:
        preprocess_metadata["preprocessed_markdown_paths"] = list(result.markdown_paths)

    await progress.update(
        95,
        "Finalizing document preprocess",
        current_step="finalize",
        metadata={"preprocess": preprocess_metadata},
    )

    if result.status == "failed":
        raise ValueError(result.error or "Document preprocess failed")

    refresh_targets = ["dashboard"]
    attachment = payload.get("attachment") if isinstance(payload.get("attachment"), dict) else {}
    if attachment.get("reference_id"):
        refresh_targets.append("references")
    if attachment.get("artifact_id"):
        refresh_targets.append("artifacts")

    return {
        "success": True,
        "workspace_id": workspace_id,
        "thread_id": str(payload.get("thread_id") or "").strip() or None,
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "output_virtual_root": output_virtual_root,
        "attachment": attachment,
        "preprocess": preprocess_metadata,
        "message": "Document preprocessing completed",
        "refresh_targets": refresh_targets,
    }

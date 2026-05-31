"""Document layout preprocessing orchestration for uploads."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.gateway.routers.thread_contracts import ThreadUploadKind
from src.services.upload_preflight_policy import UploadPreflightPolicy
from src.services.upload_preprocessor import UploadPreprocessor
from src.services.workspace_uploads import DEFAULT_WORKSPACE_UPLOAD_ROOT, workspace_upload_public_url
from src.task.registry import DOCUMENT_PREPROCESS_TASK

_PERSISTED_UPLOAD_ROOT = DEFAULT_WORKSPACE_UPLOAD_ROOT
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutPreprocessDispatch:
    """Upload preprocess metadata plus whether workspace persistence should schedule it."""

    metadata: dict[str, object]
    deferred_workspace_context_preprocess: bool = False


class LayoutPreprocessOrchestrator:
    """Choose immediate parsing, async parsing, or skip for uploaded documents."""

    def __init__(
        self,
        *,
        preflight_policy: UploadPreflightPolicy | None = None,
        persisted_upload_root: Path | None = None,
    ) -> None:
        self.preflight_policy = preflight_policy or UploadPreflightPolicy()
        self.persisted_upload_root = persisted_upload_root or _PERSISTED_UPLOAD_ROOT

    async def preprocess_or_schedule(
        self,
        *,
        task_service: Any,
        upload_preprocessor: UploadPreprocessor,
        user_id: str,
        workspace_id: str | None,
        thread_id: str,
        filename: str,
        kind: ThreadUploadKind,
        content_type: str | None,
        content: bytes,
        source_path: Path,
        output_dir: Path,
        output_virtual_root: str,
        is_parseable: bool,
    ) -> LayoutPreprocessDispatch:
        metadata: dict[str, object] = {}
        if not is_parseable:
            metadata["preprocess"] = {
                "status": "skipped",
                "provider": "unknown",
                "file_type": "unsupported",
            }
            return LayoutPreprocessDispatch(metadata=metadata)

        if self.preflight_policy.should_async_preprocess(
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
        ):
            metadata["preprocess"] = self.pending_pdf_metadata()
            if kind == "workspace_context" and workspace_id:
                return LayoutPreprocessDispatch(
                    metadata=metadata,
                    deferred_workspace_context_preprocess=True,
                )
            metadata["preprocess"] = await self.schedule_document_preprocess(
                task_service=task_service,
                user_id=user_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                filename=filename,
                kind=kind,
                content_type=content_type,
                size_bytes=len(content),
                source_path=source_path,
                output_dir=output_dir,
                output_virtual_root=output_virtual_root,
            )
            return LayoutPreprocessDispatch(metadata=metadata)

        preprocess_result = await upload_preprocessor.preprocess_file(
            filename=filename,
            content_type=content_type,
            content=content,
            output_dir=output_dir,
            output_virtual_root=output_virtual_root,
        )
        metadata["preprocess"] = preprocess_result.to_metadata()
        preprocess_metadata = metadata["preprocess"]
        markdown_paths = preprocess_metadata.get("markdown_paths") if isinstance(preprocess_metadata, dict) else None
        if isinstance(markdown_paths, list) and markdown_paths:
            metadata["preprocessed_markdown_paths"] = markdown_paths
        return LayoutPreprocessDispatch(metadata=metadata)

    async def schedule_document_preprocess(
        self,
        *,
        task_service: Any,
        user_id: str,
        workspace_id: str | None,
        thread_id: str,
        filename: str,
        kind: ThreadUploadKind,
        content_type: str | None,
        size_bytes: int,
        source_path: Path,
        output_dir: Path,
        output_virtual_root: str,
        reference_id: str | None = None,
        artifact_id: str | None = None,
    ) -> dict[str, object]:
        """Schedule async preprocessing and return attachment-safe pending metadata."""
        pending = self.pending_pdf_metadata()
        payload = {
            "workspace_id": workspace_id,
            "thread_id": thread_id,
            "filename": filename,
            "content_type": content_type,
            "file_type": "pdf",
            "provider": "layout_parsing",
            "source_path": str(source_path),
            "output_dir": str(output_dir),
            "output_virtual_root": output_virtual_root,
            "workspace_upload_root": str(self.persisted_upload_root),
            "attachment": {
                "name": filename,
                "path": f"/mnt/user-data/uploads/{filename}",
                "kind": kind,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "reference_id": reference_id,
                "artifact_id": artifact_id,
            },
        }
        try:
            task_id = await task_service.submit_task(
                user_id=user_id,
                task_type=DOCUMENT_PREPROCESS_TASK,
                payload=payload,
            )
        except Exception as exc:
            logger.warning(
                "Failed to schedule document preprocess for thread=%s file=%s",
                thread_id,
                filename,
                exc_info=True,
            )
            pending.update(
                {
                    "status": "failed",
                    "error": f"后台解析任务提交失败: {exc}",
                    "message": "后台解析任务提交失败，请稍后重试上传。",
                }
            )
            return pending

        pending["task_id"] = task_id
        return pending

    def attach_workspace_preprocess_urls(
        self,
        *,
        workspace_id: str,
        metadata: dict[str, object],
    ) -> None:
        preprocess = metadata.get("preprocess")
        if not isinstance(preprocess, dict):
            return

        for key in ("markdown_paths", "markdown_image_paths", "output_image_paths"):
            values = preprocess.get(key)
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
                        root=self.persisted_upload_root,
                    )
                except ValueError:
                    continue
                if url:
                    urls.append(url)
            if urls:
                preprocess[f"{key.removesuffix('_paths')}_urls"] = urls

        manifest_path = preprocess.get("manifest_path")
        if isinstance(manifest_path, str) and manifest_path.strip():
            try:
                manifest_url = workspace_upload_public_url(
                    workspace_id,
                    manifest_path,
                    root=self.persisted_upload_root,
                )
            except ValueError:
                manifest_url = None
            if manifest_url:
                preprocess["manifest_url"] = manifest_url

    @staticmethod
    def pending_pdf_metadata() -> dict[str, object]:
        return {
            "status": "pending",
            "provider": "layout_parsing",
            "file_type": "pdf",
            "message": "文件较大，已进入后台解析队列；解析完成前不要引用全文内容。",
            "progress": 0,
        }

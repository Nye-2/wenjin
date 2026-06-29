"""Workspace-context upload persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.artifacts import ArtifactType
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.workspace_memory import (
    WorkspaceMemoryItemPayload,
    WorkspaceMemoryMergePayload,
)
from src.services.layout_preprocess_orchestrator import LayoutPreprocessOrchestrator
from src.services.thread_upload_service import ThreadUploadService
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    extract_document_preview,
    persist_workspace_upload,
    workspace_upload_public_url,
)

_PERSISTED_UPLOAD_ROOT = DEFAULT_WORKSPACE_UPLOAD_ROOT
_MEMORY_PREVIEW_MAX_CHARS = 280
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceUploadResult:
    """Result of persisting an upload into workspace-scoped rooms."""

    artifact_id: str
    persistent_path: Path


class WorkspaceUploadService:
    """Persist workspace-context uploads and mirror them into hidden workspace memory."""

    def __init__(
        self,
        *,
        thread_uploads: ThreadUploadService | None = None,
        persisted_upload_root: Path | None = None,
    ) -> None:
        self.thread_uploads = thread_uploads or ThreadUploadService()
        self.persisted_upload_root = persisted_upload_root or _PERSISTED_UPLOAD_ROOT

    async def persist_context_upload(
        self,
        *,
        user_id: str,
        workspace_id: str,
        thread_id: str,
        upload_filename: str | None,
        saved_name: str,
        content_type: str | None,
        content: bytes,
        thread_path: Path,
        metadata: dict[str, object],
        artifact_service: Any,
        dataservice: AsyncDataServiceClient,
        task_service: Any,
        preprocess_orchestrator: LayoutPreprocessOrchestrator,
        deferred_preprocess: bool,
    ) -> WorkspaceUploadResult:
        persistent_path = persist_workspace_upload(
            workspace_id=workspace_id,
            bucket="context",
            filename=saved_name,
            source_path=thread_path,
            root=self.persisted_upload_root,
        )
        document_preview = extract_document_preview(
            upload_filename,
            content_type,
            content=content,
        )
        if deferred_preprocess:
            metadata["preprocess"] = await preprocess_orchestrator.schedule_document_preprocess(
                task_service=task_service,
                user_id=user_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                filename=saved_name,
                kind="workspace_context",
                content_type=content_type,
                size_bytes=len(content),
                source_path=persistent_path,
                output_dir=persistent_path.parent / "_preprocessed" / persistent_path.stem,
                output_virtual_root=f"context/_preprocessed/{persistent_path.stem}",
            )

        markdown_preview = self._markdown_preview(metadata)
        text_preview = markdown_preview or (str(document_preview.get("text_preview") or "").strip() or None)
        stored_url = workspace_upload_public_url(
            workspace_id,
            persistent_path,
            root=self.persisted_upload_root,
        )
        artifact = await artifact_service.create(
            workspace_id=workspace_id,
            type=ArtifactType.NOTE.value,
            title=f"上传上下文 - {persistent_path.name}",
            content={
                "source": "thread_upload",
                "kind": "workspace_context",
                "file_name": persistent_path.name,
                "content_type": content_type,
                "size_bytes": len(content),
                "stored_path": str(persistent_path),
                "stored_url": stored_url,
                "thread_path": f"/mnt/user-data/uploads/{saved_name}",
                "thread_url": self.thread_uploads.attachment_url(thread_id, saved_name),
                "text_preview": text_preview,
                "document_title": document_preview.get("title"),
                "document_authors": document_preview.get("authors") or [],
                "page_count": document_preview.get("page_count"),
                "preprocess_status": self._preprocess_value(metadata, "status"),
                "preprocess_manifest_path": self._preprocess_value(metadata, "manifest_path"),
                "preprocessed_markdown_paths": self._preprocess_value(metadata, "markdown_paths"),
            },
        )

        await self._merge_workspace_memory(
            dataservice=dataservice,
            workspace_id=workspace_id,
            thread_id=thread_id,
            persistent_path=persistent_path,
            document_preview=document_preview,
            text_preview=text_preview,
        )
        metadata["stored_path"] = str(persistent_path)
        metadata["stored_url"] = stored_url
        return WorkspaceUploadResult(
            artifact_id=str(artifact.id),
            persistent_path=persistent_path,
        )

    @staticmethod
    def _preprocess_value(metadata: dict[str, object], key: str) -> object | None:
        preprocess = metadata.get("preprocess")
        return preprocess.get(key) if isinstance(preprocess, dict) else None

    @staticmethod
    def _markdown_preview(metadata: dict[str, object]) -> str | None:
        preprocess = metadata.get("preprocess")
        markdown_preview = None
        if isinstance(preprocess, dict) and preprocess.get("status") == "succeeded":
            md_paths = preprocess.get("markdown_paths")
            if isinstance(md_paths, list) and md_paths:
                try:
                    md_path = Path(str(md_paths[0]))
                    if md_path.exists():
                        markdown_preview = md_path.read_text(encoding="utf-8")[:_MEMORY_PREVIEW_MAX_CHARS]
                except Exception:
                    return None
        return markdown_preview

    async def _merge_workspace_memory(
        self,
        *,
        dataservice: AsyncDataServiceClient,
        workspace_id: str,
        thread_id: str,
        persistent_path: Path,
        document_preview: dict[str, object],
        text_preview: str | None,
    ) -> None:
        memory_text = f"用户上传了工作区上下文文件《{persistent_path.name}》作为当前研究参考材料。"
        if document_preview.get("title"):
            memory_text += f" 文档标题：{document_preview['title']}。"
        if text_preview:
            memory_text += f" 内容摘要：{text_preview[:_MEMORY_PREVIEW_MAX_CHARS]}"
        try:
            await dataservice.merge_workspace_memory(
                workspace_id,
                WorkspaceMemoryMergePayload(
                    workspace_id=workspace_id,
                    items=[
                        WorkspaceMemoryItemPayload(
                            category="context",
                            content=memory_text,
                            confidence=0.85,
                        )
                    ],
                    update_reason="thread_upload.workspace_context",
                    updated_by="thread_upload",
                    source_thread_id=thread_id,
                    metadata_json={"stored_path": str(persistent_path)},
                ),
            )
        except Exception:
            logger.warning(
                "Failed to persist workspace-context upload memory for workspace %s",
                workspace_id,
                exc_info=True,
            )

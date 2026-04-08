"""Thread-scoped upload router for chat attachments."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.middlewares.thread_data import get_thread_data_root
from src.application.handlers.papers_handler import PapersHandler
from src.artifacts import ArtifactType
from src.database import KnowledgeCategory, User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import (
    get_artifact_service,
    get_chat_thread_service,
    get_db,
    get_paper_service,
    get_task_service,
    get_upload_preprocessor,
    get_workspace_service,
)
from src.gateway.routers.chat_contracts import ChatAttachment, ChatUploadKind
from src.services import ChatThreadService
from src.services.knowledge_service import KnowledgeService
from src.services.upload_preprocessor import UploadPreprocessor
from src.services.workspace_uploads import (
    DEFAULT_WORKSPACE_UPLOAD_ROOT,
    extract_document_preview,
    is_pdf_upload,
    next_available_path,
    persist_workspace_upload,
    sanitize_upload_filename,
    workspace_upload_public_url,
)
from src.workspace_events import publish_workspace_event

router = APIRouter(prefix="/threads/{thread_id}/uploads", tags=["uploads"])

_PERSISTED_UPLOAD_ROOT = DEFAULT_WORKSPACE_UPLOAD_ROOT
_MEMORY_PREVIEW_MAX_CHARS = 280
logger = logging.getLogger(__name__)


class ThreadUploadResponse(BaseModel):
    """Response for thread-scoped uploads."""

    success: bool
    files: list[ChatAttachment]
    message: str


def _thread_upload_dir(thread_id: str) -> Path:
    uploads_dir = get_thread_data_root(thread_id) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir


def _attachment_url(thread_id: str, filename: str) -> str:
    return f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{filename}"


def _build_attachment(
    *,
    thread_id: str,
    filename: str,
    kind: ChatUploadKind,
    content_type: str | None,
    size_bytes: int,
    paper_id: str | None = None,
    artifact_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ChatAttachment:
    return ChatAttachment(
        name=filename,
        path=f"/mnt/user-data/uploads/{filename}",
        kind=kind,
        url=_attachment_url(thread_id, filename),
        content_type=content_type,
        size_bytes=size_bytes,
        paper_id=paper_id,
        artifact_id=artifact_id,
        metadata=metadata or {},
    )


def _ordered_refresh_targets(targets: set[str]) -> list[str]:
    preferred_order = ("dashboard", "papers", "artifacts")
    return [target for target in preferred_order if target in targets]


def _attach_workspace_preprocess_urls(
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
                    root=_PERSISTED_UPLOAD_ROOT,
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
                root=_PERSISTED_UPLOAD_ROOT,
            )
        except ValueError:
            manifest_url = None
        if manifest_url:
            preprocess["manifest_url"] = manifest_url


async def _require_owned_thread(
    *,
    thread_id: str,
    user_id: str,
    chat_thread_service: ChatThreadService,
) -> Any:
    thread = await chat_thread_service.get_thread(thread_id, user_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return thread


async def _require_owned_workspace(
    *,
    workspace_id: str,
    user_id: str,
    workspace_service: Any,
) -> Any:
    workspace = await workspace_service.get(workspace_id)
    if workspace is None or str(workspace.user_id) != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.post("", response_model=ThreadUploadResponse)
async def upload_thread_files(
    thread_id: str,
    files: list[UploadFile] = File(...),
    kind: ChatUploadKind = Form(...),
    workspace_id: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
    workspace_service: Any = Depends(get_workspace_service),
    paper_service: Any = Depends(get_paper_service),
    artifact_service: Any = Depends(get_artifact_service),
    task_service: Any = Depends(get_task_service),
    upload_preprocessor: UploadPreprocessor = Depends(get_upload_preprocessor),
    db: AsyncSession = Depends(get_db),
) -> ThreadUploadResponse:
    """Upload one or more files into a thread-scoped sandbox uploads directory."""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    thread = await _require_owned_thread(
        thread_id=thread_id,
        user_id=str(current_user.id),
        chat_thread_service=chat_thread_service,
    )

    resolved_workspace_id = workspace_id or thread.workspace_id
    if (
        workspace_id
        and thread.workspace_id
        and workspace_id != thread.workspace_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload workspace does not match the thread workspace",
        )

    if kind != "transient":
        if not resolved_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id is required for persisted uploads",
            )
        await _require_owned_workspace(
            workspace_id=resolved_workspace_id,
            user_id=str(current_user.id),
            workspace_service=workspace_service,
        )

    uploads_dir = _thread_upload_dir(thread_id)
    knowledge_service = KnowledgeService(db)
    stored_files: list[ChatAttachment] = []
    refresh_targets: set[str] = set()

    for upload in files:
        try:
            filename = sanitize_upload_filename(upload.filename)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        content = await upload.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file is empty: {filename}",
            )

        if kind == "literature" and not is_pdf_upload(upload.filename, upload.content_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Literature uploads must be PDF files: {filename}",
            )

        thread_path = next_available_path(uploads_dir, filename)
        thread_path.write_bytes(content)
        saved_name = thread_path.name

        paper_id: str | None = None
        artifact_id: str | None = None
        metadata: dict[str, object] = {}

        if kind == "literature" and resolved_workspace_id:
            document_preview = extract_document_preview(
                upload.filename,
                upload.content_type,
                content=content,
            )
            persistent_path = persist_workspace_upload(
                workspace_id=resolved_workspace_id,
                bucket="papers",
                filename=saved_name,
                source_path=thread_path,
                root=_PERSISTED_UPLOAD_ROOT,
            )
            preprocess_result = await upload_preprocessor.preprocess_file(
                filename=saved_name,
                content_type=upload.content_type,
                source_path=persistent_path,
                output_dir=(
                    persistent_path.parent
                    / "_preprocessed"
                    / persistent_path.stem
                ),
            )
            metadata["preprocess"] = preprocess_result.to_metadata()
            _attach_workspace_preprocess_urls(
                workspace_id=resolved_workspace_id,
                metadata=metadata,
            )
            preprocess_metadata = metadata.get("preprocess")
            if isinstance(preprocess_metadata, dict):
                markdown_paths = preprocess_metadata.get("markdown_paths")
                if isinstance(markdown_paths, list) and markdown_paths:
                    metadata["preprocessed_markdown_paths"] = markdown_paths
            paper_title = (
                str(document_preview.get("title") or "").strip()
                or persistent_path.stem
            )
            authors_value = document_preview.get("authors")
            author_names = authors_value if isinstance(authors_value, list) else []
            paper_authors = [
                {"name": name}
                for name in author_names
                if isinstance(name, str) and name.strip()
            ]
            paper = await paper_service.create_in_workspace(
                workspace_id=resolved_workspace_id,
                title=paper_title,
                authors=paper_authors,
                file_path=str(persistent_path),
                source="chat_upload",
            )
            paper_id = str(paper.id)
            extraction = await PapersHandler(
                paper_service=paper_service,
                workspace_service=workspace_service,
                task_service=task_service,
            ).schedule_uploaded_paper_extraction(
                paper_id=paper_id,
                workspace_id=resolved_workspace_id,
                user_id=str(current_user.id),
                tier=1,
                thread_id=thread_id,
            )
            metadata["stored_path"] = str(persistent_path)
            metadata["stored_url"] = workspace_upload_public_url(
                resolved_workspace_id,
                persistent_path,
                root=_PERSISTED_UPLOAD_ROOT,
            )
            metadata["extraction"] = extraction
            if document_preview.get("title"):
                metadata["document_title"] = document_preview["title"]
            if document_preview.get("authors"):
                metadata["document_authors"] = document_preview["authors"]
            if document_preview.get("page_count"):
                metadata["page_count"] = document_preview["page_count"]
            if document_preview.get("text_preview"):
                metadata["text_preview"] = document_preview["text_preview"]
            refresh_targets.update({"dashboard", "papers"})
        else:
            preprocess_result = await upload_preprocessor.preprocess_file(
                filename=filename,
                content_type=upload.content_type,
                content=content,
                output_dir=uploads_dir / "_preprocessed" / Path(saved_name).stem,
                output_virtual_root=f"/mnt/user-data/uploads/_preprocessed/{Path(saved_name).stem}",
            )
            preprocess_metadata = preprocess_result.to_metadata()
            metadata["preprocess"] = preprocess_metadata
            markdown_paths = preprocess_metadata.get("markdown_paths")
            if isinstance(markdown_paths, list) and markdown_paths:
                metadata["preprocessed_markdown_paths"] = markdown_paths

        if kind == "workspace_context" and resolved_workspace_id:
            persistent_path = persist_workspace_upload(
                workspace_id=resolved_workspace_id,
                bucket="context",
                filename=saved_name,
                source_path=thread_path,
                root=_PERSISTED_UPLOAD_ROOT,
            )
            document_preview = extract_document_preview(
                upload.filename,
                upload.content_type,
                content=content,
            )
            text_preview = (
                str(document_preview.get("text_preview") or "").strip() or None
            )
            artifact = await artifact_service.create(
                workspace_id=resolved_workspace_id,
                type=ArtifactType.NOTE.value,
                title=f"上传上下文 - {persistent_path.name}",
                created_by_skill="chat_upload",
                content={
                    "source": "chat_upload",
                    "kind": "workspace_context",
                    "file_name": persistent_path.name,
                    "content_type": upload.content_type,
                    "size_bytes": len(content),
                    "stored_path": str(persistent_path),
                    "stored_url": workspace_upload_public_url(
                        resolved_workspace_id,
                        persistent_path,
                        root=_PERSISTED_UPLOAD_ROOT,
                    ),
                    "thread_path": f"/mnt/user-data/uploads/{saved_name}",
                    "thread_url": _attachment_url(thread_id, saved_name),
                    "text_preview": text_preview,
                    "document_title": document_preview.get("title"),
                    "document_authors": document_preview.get("authors") or [],
                    "page_count": document_preview.get("page_count"),
                },
            )
            artifact_id = str(artifact.id)
            knowledge_text = (
                f"用户上传了工作区上下文文件《{persistent_path.name}》作为当前研究参考材料。"
            )
            if document_preview.get("title"):
                knowledge_text += f" 文档标题：{document_preview['title']}。"
            if text_preview:
                knowledge_text += f" 内容摘要：{text_preview[:_MEMORY_PREVIEW_MAX_CHARS]}"
            try:
                await knowledge_service.upsert(
                    str(current_user.id),
                    KnowledgeCategory.CONTEXT,
                    knowledge_text,
                    confidence=0.85,
                    source="chat_upload.workspace_context",
                    workspace_context=resolved_workspace_id,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                logger.warning(
                    "Failed to persist workspace-context upload memory for workspace %s",
                    resolved_workspace_id,
                    exc_info=True,
                )
            metadata["stored_path"] = str(persistent_path)
            metadata["stored_url"] = workspace_upload_public_url(
                resolved_workspace_id,
                persistent_path,
                root=_PERSISTED_UPLOAD_ROOT,
            )
            refresh_targets.update({"dashboard", "artifacts"})

        stored_files.append(
            _build_attachment(
                thread_id=thread_id,
                filename=saved_name,
                kind=kind,
                content_type=upload.content_type,
                size_bytes=len(content),
                paper_id=paper_id,
                artifact_id=artifact_id,
                metadata=metadata,
            )
        )

    if resolved_workspace_id and refresh_targets:
        await publish_workspace_event(
            resolved_workspace_id,
            "workspace.refresh",
            {"refresh_targets": _ordered_refresh_targets(refresh_targets)},
        )

    return ThreadUploadResponse(
        success=True,
        files=stored_files,
        message=f"Successfully uploaded {len(stored_files)} file(s)",
    )

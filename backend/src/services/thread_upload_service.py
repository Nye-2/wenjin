"""Thread-local upload storage and attachment mapping."""

from __future__ import annotations

from pathlib import Path

from src.agents.middlewares.thread_data import get_thread_data_root
from src.gateway.routers.thread_contracts import ThreadAttachment, ThreadUploadKind
from src.services.workspace_uploads import next_available_path


class ThreadUploadService:
    """Persist thread upload files and build attachment contracts."""

    def upload_dir(self, thread_id: str) -> Path:
        uploads_dir = get_thread_data_root(thread_id) / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        return uploads_dir

    def attachment_url(self, thread_id: str, filename: str) -> str:
        return f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{filename}"

    def build_attachment(
        self,
        *,
        thread_id: str,
        filename: str,
        kind: ThreadUploadKind,
        content_type: str | None,
        size_bytes: int,
        path: str | None = None,
        url: str | None = None,
        reference_id: str | None = None,
        artifact_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThreadAttachment:
        return ThreadAttachment(
            name=filename,
            path=path or f"/mnt/user-data/uploads/{filename}",
            kind=kind,
            url=url if url is not None else self.attachment_url(thread_id, filename),
            content_type=content_type,
            size_bytes=size_bytes,
            reference_id=reference_id,
            artifact_id=artifact_id,
            metadata=metadata or {},
        )

    def persist_transient_file(
        self,
        *,
        thread_id: str,
        filename: str,
        content: bytes,
    ) -> Path:
        thread_path = next_available_path(self.upload_dir(thread_id), filename)
        thread_path.write_bytes(content)
        return thread_path

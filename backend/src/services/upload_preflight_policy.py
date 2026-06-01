"""Preflight policy for thread-scoped uploads."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException, UploadFile, status

from src.services.upload_preprocessor import _is_image_upload
from src.services.workspace_uploads import is_pdf_upload, sanitize_upload_filename

MAX_UPLOAD_FILES = 20
MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024
UPLOAD_READ_CHUNK_SIZE = 64 * 1024
ASYNC_PREPROCESS_THRESHOLD_BYTES = 5 * 1024 * 1024


class UploadPreflightPolicy:
    """Validate upload request shape and per-file content constraints."""

    def __init__(
        self,
        *,
        max_files: int | None = None,
        max_size_bytes: int | None = None,
        read_chunk_size: int | None = None,
        async_preprocess_threshold_bytes: int | None = None,
    ) -> None:
        self.max_files = int(MAX_UPLOAD_FILES if max_files is None else max_files)
        self.max_size_bytes = int(MAX_UPLOAD_SIZE_BYTES if max_size_bytes is None else max_size_bytes)
        self.read_chunk_size = int(UPLOAD_READ_CHUNK_SIZE if read_chunk_size is None else read_chunk_size)
        self.async_preprocess_threshold_bytes = int(
            ASYNC_PREPROCESS_THRESHOLD_BYTES
            if async_preprocess_threshold_bytes is None
            else async_preprocess_threshold_bytes
        )

    def validate_file_count(self, files: Sequence[UploadFile]) -> None:
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")
        if len(files) > self.max_files:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Too many files in one request (max {self.max_files})",
            )

    async def read_content(self, upload: UploadFile) -> tuple[str, bytes]:
        filename = self.sanitize_filename(upload.filename)
        chunks: list[bytes] = []
        total_size = 0
        while True:
            chunk = await upload.read(self.read_chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > self.max_size_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        f"Uploaded file is too large (max {self.max_size_bytes // (1024 * 1024)}MB): "
                        f"{str(upload.filename or 'uploaded-file')}"
                    ),
                )
            chunks.append(chunk)
        content = b"".join(chunks)
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file is empty: {filename}",
            )
        return filename, content

    def sanitize_filename(self, filename: str | None) -> str:
        try:
            return sanitize_upload_filename(filename)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    def require_literature_pdf(self, *, filename: str, upload: UploadFile) -> None:
        if is_pdf_upload(upload.filename, upload.content_type):
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Literature uploads must be PDF files: {filename}",
        )

    def is_parseable(self, *, filename: str | None, content_type: str | None) -> bool:
        return is_pdf_upload(filename, content_type) or _is_image_upload(filename, content_type)

    def should_async_preprocess(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        size_bytes: int,
    ) -> bool:
        return is_pdf_upload(filename, content_type) and int(size_bytes) > self.async_preprocess_threshold_bytes

"""Shared helpers for LaTeX project upload routes."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from src.services.latex.paths import is_reserved_project_path, normalize_relative_path

_MAX_UPLOAD_ARCHIVE_FILES = 5000
_MAX_UPLOAD_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_UPLOAD_READ_CHUNK_SIZE = 64 * 1024


def _normalize_upload_relative_path(filename: str | None, base_path: str | None) -> str:
    """Normalize an upload filename against its optional destination folder."""
    normalized_name = str(filename or "").replace("\\", "/").strip().lstrip("/")
    if not normalized_name:
        return ""
    normalized_base = str(base_path or "").replace("\\", "/").strip().strip("/")
    if not normalized_base:
        return normalize_relative_path(normalized_name)
    if normalized_name == normalized_base or normalized_name.startswith(f"{normalized_base}/"):
        merged = normalized_name
    else:
        merged = f"{normalized_base}/{normalized_name}"
    return normalize_relative_path(merged)


def _is_reserved_upload_path(relative_path: str) -> bool:
    return is_reserved_project_path(relative_path)


def _sorted_folder_paths(paths: set[str]) -> list[str]:
    return sorted(paths, key=lambda item: (item.count("/"), item))


async def _read_upload_bytes_with_limit(
    upload: UploadFile,
    *,
    max_size_bytes: int,
    chunk_size: int = _UPLOAD_READ_CHUNK_SIZE,
    error_label: str = "Archive file",
) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"{error_label} too large. Maximum size is {max_size_bytes // (1024 * 1024)}MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _common_upload_root_prefix(paths: list[str]) -> str | None:
    cleaned = [path for path in paths if path]
    if not cleaned:
        return None
    first_parts = cleaned[0].split("/")
    if len(first_parts) < 2:
        return None
    root = first_parts[0]
    for current in cleaned:
        parts = current.split("/")
        if not parts or parts[0] != root:
            return None
    return root


def _collect_archive_upload_payload(
    archive_bytes: bytes,
    *,
    base_path: str | None,
    strip_root: bool = True,
) -> tuple[list[tuple[str, bytes]], list[str], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid ZIP archive") from exc

    parsed_entries: list[tuple[str, bool, bytes | None]] = []
    with archive:
        entries = archive.infolist()
        if len(entries) > _MAX_UPLOAD_ARCHIVE_FILES:
            raise ValueError("Archive contains too many files")

        total_uncompressed_bytes = 0
        for entry in entries:
            total_uncompressed_bytes += max(0, int(entry.file_size or 0))
            if total_uncompressed_bytes > _MAX_UPLOAD_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ValueError("Archive is too large after extraction")
            try:
                normalized = _normalize_upload_relative_path(entry.filename, None)
            except ValueError as exc:
                raise ValueError(f"Invalid archive path: {entry.filename}") from exc
            if normalized:
                parsed_entries.append(
                    (normalized, entry.is_dir(), None if entry.is_dir() else archive.read(entry))
                )

    if strip_root:
        root_prefix = _common_upload_root_prefix([path for path, _, _ in parsed_entries])
        if root_prefix:
            prefix = f"{root_prefix}/"
            parsed_entries = [
                (path[len(prefix) :] if path.startswith(prefix) else path, is_dir, payload)
                for path, is_dir, payload in parsed_entries
                if path != root_prefix
            ]

    files: dict[str, bytes] = {}
    folders: set[str] = set()
    skipped: list[str] = []
    for path, is_dir, payload in parsed_entries:
        try:
            final_path = _normalize_upload_relative_path(path, base_path)
        except ValueError as exc:
            raise ValueError(f"Invalid archive path: {path}") from exc
        if _is_reserved_upload_path(final_path):
            skipped.append(final_path)
            continue
        if is_dir:
            folders.add(final_path)
            continue
        files[final_path] = payload or b""
        parent = Path(final_path).parent.as_posix()
        if parent not in {"", "."}:
            folders.add(parent)

    return list(files.items()), _sorted_folder_paths(folders), list(dict.fromkeys(skipped))


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

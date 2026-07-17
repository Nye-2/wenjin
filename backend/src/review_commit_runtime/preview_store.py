"""Private, workspace-scoped TTL storage for Mission preview binaries."""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from src.services.path_safety import normalize_path_component

from .contracts import PreviewObject, PreviewObjectDescriptor

_ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_REF_RE = re.compile(r"^mpv1_[A-Za-z0-9_-]{32}$")
_SVG_BLOCKED_TAGS = {"script", "style", "foreignObject", "iframe", "object", "embed"}
_SVG_LINK_ATTRIBUTES = {"href", "{http://www.w3.org/1999/xlink}href"}
_PDF_ACTIVE_MARKERS = (
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/OpenAction",
    b"/AA",
    b"/URI",
    b"/SubmitForm",
    b"/ImportData",
    b"/GoToR",
    b"/EmbeddedFile",
    b"/RichMedia",
    b"/AcroForm",
    b"/XFA",
)


class MissionPreviewStore:
    """Filesystem object store with content-addressed payloads and expiring refs."""

    def __init__(self, root: Path, *, default_ttl_seconds: int, max_bytes: int) -> None:
        self._root = Path(root)
        self._default_ttl = timedelta(seconds=default_ttl_seconds)
        self._max_bytes = max_bytes

    async def put(
        self,
        *,
        workspace_id: str,
        content: bytes,
        mime_type: str,
        filename: str,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PreviewObjectDescriptor:
        return await asyncio.to_thread(
            self._put,
            workspace_id=workspace_id,
            content=content,
            mime_type=mime_type,
            filename=filename,
            expires_at=expires_at,
            metadata=metadata,
        )

    async def read(self, ref: str, *, workspace_id: str) -> PreviewObject:
        return await asyncio.to_thread(self._read, ref=ref, workspace_id=workspace_id)

    async def delete(self, ref: str, *, workspace_id: str) -> None:
        await asyncio.to_thread(self._delete, ref=ref, workspace_id=workspace_id)

    async def cleanup_expired(
        self,
        *,
        now: datetime | None = None,
        limit: int = 500,
    ) -> list[str]:
        return await asyncio.to_thread(self._cleanup_expired, now=now or datetime.now(UTC), limit=limit)

    def _put(
        self,
        *,
        workspace_id: str,
        content: bytes,
        mime_type: str,
        filename: str,
        expires_at: datetime | None,
        metadata: dict[str, Any] | None,
    ) -> PreviewObjectDescriptor:
        normalized_mime = _normalize_mime(mime_type)
        sanitized = _sanitize_content(content, normalized_mime, maximum=self._max_bytes)
        bounded_metadata = dict(metadata or {})
        if len(json.dumps(bounded_metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")) > 32_768:
            raise ValueError("preview_metadata_too_large")
        now = datetime.now(UTC)
        expiry = _aware(expires_at) if expires_at is not None else now + self._default_ttl
        if expiry <= now:
            raise ValueError("preview_expiry_must_be_future")
        content_hash = hashlib.sha256(sanitized).hexdigest()
        workspace = normalize_path_component(workspace_id)
        object_path = self._object_path(workspace, content_hash)
        _ensure_private_directory(self._root, object_path.parent)
        if object_path.exists():
            if not secrets.compare_digest(_hash_file(object_path), content_hash):
                raise ValueError("preview_object_integrity_failed")
        else:
            _atomic_write(object_path, sanitized)

        ref = f"mpv1_{secrets.token_urlsafe(24)}"
        descriptor = PreviewObjectDescriptor(
            ref=ref,
            workspace_id=workspace_id,
            content_hash=content_hash,
            mime_type=normalized_mime,
            filename=_safe_filename(filename, suffix=_ALLOWED_MIME_TYPES[normalized_mime]),
            size_bytes=len(sanitized),
            created_at=now,
            expires_at=expiry,
            metadata=bounded_metadata,
        )
        ref_path = self._ref_path(workspace, ref)
        _ensure_private_directory(self._root, ref_path.parent)
        _atomic_write(ref_path, descriptor.model_dump_json().encode("utf-8"))
        return descriptor

    def _read(self, *, ref: str, workspace_id: str) -> PreviewObject:
        descriptor = self._read_descriptor(ref=ref, workspace_id=workspace_id)
        if descriptor.expires_at <= datetime.now(UTC):
            raise ValueError("review_preview_expired")
        workspace = normalize_path_component(workspace_id)
        object_path = self._object_path(workspace, descriptor.content_hash)
        try:
            content = object_path.read_bytes()
        except FileNotFoundError as exc:
            raise LookupError("review_preview_not_found") from exc
        if len(content) != descriptor.size_bytes:
            raise ValueError("review_preview_integrity_failed")
        actual_hash = hashlib.sha256(content).hexdigest()
        if not secrets.compare_digest(actual_hash, descriptor.content_hash):
            raise ValueError("review_preview_integrity_failed")
        _validate_content_signature(content, descriptor.mime_type)
        return PreviewObject(descriptor=descriptor, content=content)

    def _read_descriptor(self, *, ref: str, workspace_id: str) -> PreviewObjectDescriptor:
        _validate_ref(ref)
        workspace = normalize_path_component(workspace_id)
        try:
            raw = self._ref_path(workspace, ref).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise LookupError("review_preview_not_found") from exc
        descriptor = PreviewObjectDescriptor.model_validate_json(raw)
        if descriptor.ref != ref or descriptor.workspace_id != workspace_id:
            raise PermissionError("review_preview_workspace_mismatch")
        return descriptor

    def _delete(self, *, ref: str, workspace_id: str) -> None:
        try:
            descriptor = self._read_descriptor(ref=ref, workspace_id=workspace_id)
        except LookupError:
            return
        ref_path = self._ref_path(normalize_path_component(workspace_id), ref)
        ref_path.unlink(missing_ok=True)
        self._delete_unreferenced_object(descriptor)

    def _cleanup_expired(self, *, now: datetime, limit: int) -> list[str]:
        if not 1 <= limit <= 1000:
            raise ValueError("mission_preview_cleanup_limit_invalid")
        cutoff = _aware(now)
        deleted: list[str] = []
        referenced_objects: set[tuple[str, str]] = set()
        refs_root = self._root / "refs"
        if not refs_root.exists():
            refs_root.mkdir(parents=True, exist_ok=True)
        else:
            for ref_path in sorted(refs_root.glob("*/*.json")):
                try:
                    descriptor = PreviewObjectDescriptor.model_validate_json(ref_path.read_text(encoding="utf-8"))
                    workspace = normalize_path_component(descriptor.workspace_id)
                    _validate_ref(descriptor.ref)
                    if workspace != ref_path.parent.name or descriptor.ref != ref_path.stem:
                        raise ValueError("preview_ref_descriptor_mismatch")
                except FileNotFoundError:
                    continue
                except ValueError:
                    ref_path.unlink(missing_ok=True)
                    continue
                if descriptor.expires_at <= cutoff and len(deleted) < limit:
                    ref_path.unlink(missing_ok=True)
                    deleted.append(descriptor.ref)
                    continue
                referenced_objects.add(
                    (workspace, descriptor.content_hash)
                )
        objects_root = self._root / "objects"
        if objects_root.exists():
            deleted_objects = 0
            for object_path in objects_root.glob("*/*/*/payload"):
                if deleted_objects >= limit:
                    break
                workspace = object_path.parents[2].name
                content_hash = object_path.parent.name
                if (workspace, content_hash) in referenced_objects:
                    continue
                try:
                    modified_at = datetime.fromtimestamp(object_path.stat().st_mtime, tz=UTC)
                except FileNotFoundError:
                    continue
                if modified_at <= cutoff:
                    object_path.unlink(missing_ok=True)
                    deleted_objects += 1
                    try:
                        object_path.parent.rmdir()
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                            raise
        return deleted

    def _delete_unreferenced_object(self, descriptor: PreviewObjectDescriptor) -> None:
        workspace = normalize_path_component(descriptor.workspace_id)
        refs_root = self._root / "refs" / workspace
        for other_ref in refs_root.glob("*.json"):
            try:
                other = PreviewObjectDescriptor.model_validate_json(other_ref.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if other.content_hash == descriptor.content_hash:
                return
        object_path = self._object_path(workspace, descriptor.content_hash)
        object_path.unlink(missing_ok=True)
        try:
            object_path.parent.rmdir()
        except OSError:
            pass

    def _object_path(self, workspace: str, content_hash: str) -> Path:
        return self._root / "objects" / workspace / content_hash[:2] / content_hash / "payload"

    def _ref_path(self, workspace: str, ref: str) -> Path:
        _validate_ref(ref)
        return self._root / "refs" / workspace / f"{ref}.json"


def _sanitize_content(content: bytes, mime_type: str, *, maximum: int) -> bytes:
    if not content or len(content) > maximum:
        raise ValueError("preview_object_size_invalid")
    if mime_type == "image/svg+xml":
        return _sanitize_svg(content)
    _validate_content_signature(content, mime_type)
    if mime_type == "image/png":
        return _sanitize_png(content)
    if mime_type == "image/webp":
        return _sanitize_webp(content)
    if mime_type == "application/pdf" and any(marker in content for marker in _PDF_ACTIVE_MARKERS):
        raise ValueError("preview_pdf_active_content_denied")
    return bytes(content)


def _sanitize_png(content: bytes) -> bytes:
    position = 8
    chunks: list[bytes] = [content[:8]]
    saw_header = False
    saw_end = False
    while position + 12 <= len(content):
        length = struct.unpack(">I", content[position : position + 4])[0]
        end = position + 12 + length
        if end > len(content):
            raise ValueError("preview_png_invalid")
        chunk_type = content[position + 4 : position + 8]
        chunk_data = content[position + 8 : position + 8 + length]
        expected_crc = struct.unpack(">I", content[position + 8 + length : end])[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            raise ValueError("preview_png_invalid")
        if chunk_type == b"IHDR":
            saw_header = True
        if chunk_type == b"IEND":
            saw_end = True
        if chunk_type not in {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}:
            chunks.append(content[position:end])
        position = end
        if chunk_type == b"IEND":
            break
    if not saw_header or not saw_end or position != len(content):
        raise ValueError("preview_png_invalid")
    return b"".join(chunks)


def _sanitize_webp(content: bytes) -> bytes:
    declared_size = struct.unpack("<I", content[4:8])[0] + 8
    if declared_size != len(content):
        raise ValueError("preview_webp_invalid")
    position = 12
    chunks: list[bytes] = []
    while position + 8 <= len(content):
        chunk_type = content[position : position + 4]
        length = struct.unpack("<I", content[position + 4 : position + 8])[0]
        padded_length = length + (length % 2)
        end = position + 8 + padded_length
        if end > len(content):
            raise ValueError("preview_webp_invalid")
        if chunk_type not in {b"EXIF", b"XMP "}:
            chunks.append(content[position:end])
        position = end
    if position != len(content) or not chunks:
        raise ValueError("preview_webp_invalid")
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _sanitize_svg(content: bytes) -> bytes:
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("preview_svg_unsafe")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("preview_svg_invalid") from exc
    if _local_name(root.tag).lower() != "svg":
        raise ValueError("preview_content_type_mismatch")
    for parent in root.iter():
        for child in list(parent):
            if _local_name(child.tag) in _SVG_BLOCKED_TAGS:
                parent.remove(child)
        for key in list(parent.attrib):
            local_key = _local_name(key).lower()
            value = parent.attrib[key].strip().lower()
            if local_key.startswith("on") or (key in _SVG_LINK_ATTRIBUTES and not value.startswith("#")):
                del parent.attrib[key]
            elif "url(" in value and not value.replace(" ", "").startswith("url(#"):
                del parent.attrib[key]
    sanitized = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    return sanitized


def _validate_content_signature(content: bytes, mime_type: str) -> None:
    if mime_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("preview_content_type_mismatch")
    if mime_type == "image/webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
        raise ValueError("preview_content_type_mismatch")
    if mime_type == "application/pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("preview_content_type_mismatch")
    if mime_type == "image/svg+xml":
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise ValueError("preview_content_type_mismatch") from exc
        if _local_name(root.tag).lower() != "svg":
            raise ValueError("preview_content_type_mismatch")


def _normalize_mime(value: str) -> str:
    normalized = value.split(";", 1)[0].strip().lower()
    if normalized not in _ALLOWED_MIME_TYPES:
        raise ValueError("preview_content_type_unsupported")
    return normalized


def _validate_ref(ref: str) -> None:
    if not _REF_RE.fullmatch(ref):
        raise ValueError("invalid_preview_ref")


def _safe_filename(filename: str, *, suffix: str) -> str:
    name = Path(str(filename or "")).name.strip()
    if not name or name in {".", ".."}:
        name = f"academic-visual{suffix}"
    if Path(name).suffix.lower() != suffix:
        name = f"{Path(name).stem or 'academic-visual'}{suffix}"
    return name[:255]


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def copy_preview_to_asset(content: bytes, destination: Path, *, expected_hash: str) -> None:
    """Atomically materialize verified bytes into a content-addressed asset path."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not secrets.compare_digest(_hash_file(destination), expected_hash):
            raise ValueError("workspace_asset_integrity_failed")
        return
    temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as target:
            shutil.copyfileobj(_BytesReader(content), target)
            target.flush()
            os.fsync(target.fileno())
        temporary.chmod(0o600)
        if not secrets.compare_digest(_hash_file(temporary), expected_hash):
            raise ValueError("workspace_asset_integrity_failed")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


class _BytesReader:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._content) - self._position
        result = self._content[self._position : self._position + size]
        self._position += len(result)
        return result


def _ensure_private_directory(root: Path, target: Path) -> None:
    root = root.absolute()
    target = target.absolute()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError("preview_store_path_escape") from exc
    current = root
    current.mkdir(parents=True, exist_ok=True, mode=0o700)
    if current.is_symlink():
        raise ValueError("preview_store_symlink_denied")
    current.chmod(0o700)
    for component in relative.parts:
        current = current / component
        current.mkdir(exist_ok=True, mode=0o700)
        if current.is_symlink():
            raise ValueError("preview_store_symlink_denied")
        current.chmod(0o700)


__all__ = ["MissionPreviewStore", "copy_preview_to_asset"]

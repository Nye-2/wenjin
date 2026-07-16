"""Seal uploaded text as immutable Mission inputs and project it into chat context."""

from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.results import ThreadTurnAttachment
from src.config import get_settings
from src.contracts.mission_input import (
    MAX_MISSION_INPUTS,
    MissionInputContext,
    MissionInputManifest,
)
from src.services.path_safety import normalize_path_component
from src.services.workspace_uploads import is_pdf_upload

_THREAD_VIRTUAL_ROOT = "/mnt/user-data"
_MAX_SOURCE_BYTES = 100 * 1024 * 1024
_MAX_TEXT_BYTES = 8 * 1024 * 1024
_MAX_PROMPT_INPUTS = 8
_MAX_EXCERPT_CHARS = 12_000
_TEXT_SUFFIXES = frozenset(
    {
        ".bib",
        ".csv",
        ".json",
        ".md",
        ".markdown",
        ".py",
        ".r",
        ".tex",
        ".tsv",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)


@dataclass(frozen=True, slots=True)
class MissionInputPreparation:
    manifests: tuple[MissionInputManifest, ...]
    contexts: tuple[MissionInputContext, ...]


class MissionInputStore:
    """Private workspace-scoped object store for immutable extracted text."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or get_settings().thread_data_root)

    def put_text(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        filename: str,
        mime_type: str | None,
        extractor: str,
        text: str,
        source_content_hash: str,
        source_size_bytes: int,
    ) -> MissionInputManifest:
        normalized = _normalize_text(text)
        payload = normalized.encode("utf-8")
        if not payload or len(payload) > _MAX_TEXT_BYTES:
            raise ValueError("mission input extracted text is empty or exceeds the hard limit")
        digest = hashlib.sha256(payload).hexdigest()
        manifest = MissionInputManifest(
            input_ref=f"mission-input:{digest}",
            workspace_id=workspace_id,
            thread_id=thread_id,
            filename=Path(filename).name,
            mime_type=mime_type,
            extractor=extractor,
            content_hash=f"sha256:{digest}",
            source_content_hash=source_content_hash,
            source_size_bytes=source_size_bytes,
            text_size_bytes=len(payload),
            text_chars=len(normalized),
        )
        target = self._object_path(manifest)
        _ensure_private_directory(target.parent)
        if target.exists():
            self._verify_file(target, manifest)
        else:
            _atomic_write_once(target, payload)
            self._verify_file(target, manifest)
        return manifest

    def read_text(
        self,
        manifest: MissionInputManifest,
        *,
        workspace_id: str,
        thread_id: str | None = None,
        offset: int = 0,
        max_chars: int = 65_536,
    ) -> tuple[str, bool]:
        if manifest.workspace_id != workspace_id:
            raise PermissionError("mission input workspace mismatch")
        if thread_id is not None and manifest.thread_id != thread_id:
            raise PermissionError("mission input thread mismatch")
        target = self._object_path(manifest)
        payload = self._verify_file(target, manifest)
        text = payload.decode("utf-8")
        if offset > len(text):
            return "", False
        end = min(len(text), offset + max_chars)
        return text[offset:end], end < len(text)

    def _object_path(self, manifest: MissionInputManifest) -> Path:
        digest = manifest.input_ref.removeprefix("mission-input:")
        thread = normalize_path_component(manifest.thread_id)
        return self.root / thread / "mission-inputs" / digest[:2] / digest / "content.txt"

    @staticmethod
    def _verify_file(path: Path, manifest: MissionInputManifest) -> bytes:
        if path.is_symlink():
            raise PermissionError("mission input object cannot be a symlink")
        try:
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise LookupError("mission input object was not found") from exc
        digest = hashlib.sha256(payload).hexdigest()
        if f"sha256:{digest}" != manifest.content_hash or len(payload) != manifest.text_size_bytes or len(payload.decode("utf-8")) != manifest.text_chars:
            raise ValueError("mission input object integrity check failed")
        return payload


class MissionInputService:
    """Convert thread uploads into durable, typed inputs without trusting client paths."""

    def __init__(
        self,
        *,
        store: MissionInputStore | None = None,
        thread_data_root: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.store = store or MissionInputStore(settings.thread_data_root)
        self.thread_data_root = Path(thread_data_root or settings.thread_data_root)

    def prepare(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        attachments: tuple[ThreadTurnAttachment, ...],
    ) -> MissionInputPreparation:
        manifests: list[MissionInputManifest] = []
        contexts: list[MissionInputContext] = []
        for attachment in attachments:
            manifest, context = self._prepare_one(
                workspace_id=workspace_id,
                thread_id=thread_id,
                attachment=attachment,
            )
            contexts.append(context)
            if manifest is not None and all(item.input_ref != manifest.input_ref for item in manifests):
                manifests.append(manifest)
        if len(manifests) > MAX_MISSION_INPUTS:
            raise ValueError(f"one turn may prepare at most {MAX_MISSION_INPUTS} Mission inputs")
        return MissionInputPreparation(manifests=tuple(manifests), contexts=tuple(contexts))

    def collect_from_messages(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        workspace_id: str,
        thread_id: str,
    ) -> MissionInputPreparation:
        user_messages = [item for item in messages if str(item.get("role") or "") == "user"]
        manifests: list[MissionInputManifest] = []
        contexts: list[MissionInputContext] = []
        seen_refs: set[str] = set()
        for reverse_index, message in enumerate(reversed(user_messages)):
            metadata = message.get("metadata")
            if not isinstance(metadata, dict):
                continue
            raw_manifests = metadata.get("mission_inputs")
            parsed: dict[str, MissionInputManifest] = {}
            if isinstance(raw_manifests, list):
                for raw in raw_manifests:
                    if not isinstance(raw, dict):
                        continue
                    try:
                        manifest = MissionInputManifest.model_validate(raw)
                    except ValueError:
                        continue
                    if manifest.workspace_id == workspace_id and manifest.thread_id == thread_id:
                        parsed[manifest.input_ref] = manifest
            raw_contexts = metadata.get("attachment_contexts")
            if not isinstance(raw_contexts, list):
                raw_contexts = []
            raw_contexts = self._recover_unavailable_contexts(
                workspace_id=workspace_id,
                thread_id=thread_id,
                metadata=metadata,
                raw_contexts=raw_contexts,
                parsed=parsed,
            )
            for raw_context in raw_contexts:
                if not isinstance(raw_context, dict):
                    continue
                try:
                    stored_context = MissionInputContext.model_validate(raw_context)
                except ValueError:
                    continue
                current = reverse_index == 0
                if stored_context.input_ref:
                    if stored_context.input_ref in seen_refs:
                        continue
                    manifest = parsed.get(stored_context.input_ref)
                    if manifest is None:
                        continue
                    try:
                        excerpt, _ = self.store.read_text(
                            manifest,
                            workspace_id=workspace_id,
                            max_chars=_MAX_EXCERPT_CHARS,
                        )
                    except (LookupError, PermissionError, ValueError):
                        contexts.append(
                            MissionInputContext(
                                name=stored_context.name,
                                content_type=stored_context.content_type,
                                size_bytes=stored_context.size_bytes,
                                status="unreadable",
                                detail="文件内容校验失败，请重新上传。",
                                current_message=current,
                            )
                        )
                        continue
                    seen_refs.add(manifest.input_ref)
                    manifests.append(manifest)
                    contexts.append(stored_context.model_copy(update={"excerpt": excerpt, "current_message": current}))
                elif current:
                    contexts.append(stored_context.model_copy(update={"current_message": True}))
                if len(manifests) >= _MAX_PROMPT_INPUTS:
                    break
            if len(manifests) >= _MAX_PROMPT_INPUTS:
                break
        return MissionInputPreparation(manifests=tuple(manifests), contexts=tuple(contexts))

    def _recover_unavailable_contexts(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        metadata: dict[str, Any],
        raw_contexts: list[Any],
        parsed: dict[str, MissionInputManifest],
    ) -> list[Any]:
        raw_attachments = metadata.get("attachments")
        if not isinstance(raw_attachments, list):
            return raw_contexts
        attachments = [_attachment_from_metadata(item) for item in raw_attachments]
        contexts = list(raw_contexts)
        if len(contexts) < len(attachments):
            contexts.extend({} for _ in range(len(attachments) - len(contexts)))
        for index, attachment in enumerate(attachments):
            if attachment is None or index >= len(contexts):
                continue
            raw_context = contexts[index]
            stored_context: MissionInputContext | None = None
            if isinstance(raw_context, dict):
                try:
                    stored_context = MissionInputContext.model_validate(raw_context)
                except ValueError:
                    pass
            if stored_context is not None and stored_context.status == "ready" and stored_context.input_ref in parsed:
                continue
            recovered = self.prepare(
                workspace_id=workspace_id,
                thread_id=thread_id,
                attachments=(attachment,),
            )
            if recovered.manifests:
                manifest = recovered.manifests[0]
                parsed[manifest.input_ref] = manifest
            contexts[index] = recovered.contexts[0].model_dump(
                mode="json",
                exclude={"excerpt", "current_message"},
                exclude_none=True,
            )
        return contexts

    def _prepare_one(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        attachment: ThreadTurnAttachment,
    ) -> tuple[MissionInputManifest | None, MissionInputContext]:
        base = {
            "name": attachment.name,
            "content_type": attachment.content_type,
            "size_bytes": attachment.size_bytes,
        }
        try:
            source_path = self._resolve_thread_path(thread_id, attachment.path)
            source = source_path.read_bytes()
        except (OSError, ValueError, PermissionError):
            return None, MissionInputContext(
                **base,
                status="unreadable",
                detail="文件不可读取，请重新上传。",
            )
        if not source or len(source) > _MAX_SOURCE_BYTES:
            return None, MissionInputContext(
                **base,
                status="unreadable",
                detail="文件为空或超过可处理大小。",
            )

        try:
            text, extractor = self._extract_text(
                thread_id=thread_id,
                attachment=attachment,
                source=source,
            )
        except ValueError:
            return None, MissionInputContext(
                **base,
                status="unreadable",
                detail="提取文本超过可处理大小，请拆分文件后重试。",
            )
        if not text or extractor is None:
            preprocess = (attachment.metadata or {}).get("preprocess")
            pending = isinstance(preprocess, dict) and preprocess.get("status") == "pending"
            return None, MissionInputContext(
                **base,
                status="pending" if pending else "unreadable",
                detail=("文件正在解析，完成后即可继续。" if pending else "未提取到可读文本，请上传可检索 PDF 或文本版本。"),
            )

        source_hash = f"sha256:{hashlib.sha256(source).hexdigest()}"
        try:
            manifest = self.store.put_text(
                workspace_id=workspace_id,
                thread_id=thread_id,
                filename=attachment.name,
                mime_type=attachment.content_type,
                extractor=extractor,
                text=text,
                source_content_hash=source_hash,
                source_size_bytes=len(source),
            )
        except ValueError:
            return None, MissionInputContext(
                **base,
                status="unreadable",
                detail="提取文本超过可处理大小，请拆分文件后重试。",
            )
        return manifest, MissionInputContext(
            **base,
            status="ready",
            input_ref=manifest.input_ref,
            detail="已读取并校验，可用于当前对话和研究任务。",
        )

    def _extract_text(
        self,
        *,
        thread_id: str,
        attachment: ThreadTurnAttachment,
        source: bytes,
    ) -> tuple[str | None, str | None]:
        preprocessed = self._preprocessed_markdown(thread_id, attachment.metadata or {})
        if preprocessed:
            return preprocessed, "preprocessed_markdown"
        if is_pdf_upload(attachment.name, attachment.content_type):
            return _extract_pdf_text(source), "pdf_text"
        if _is_text_upload(attachment.name, attachment.content_type):
            return source.decode("utf-8", errors="replace"), "plain_text"
        return None, None

    def _preprocessed_markdown(self, thread_id: str, metadata: dict[str, Any]) -> str | None:
        preprocess = metadata.get("preprocess")
        if not isinstance(preprocess, dict) or preprocess.get("status") != "succeeded":
            return None
        paths = preprocess.get("markdown_paths")
        if not isinstance(paths, list):
            return None
        pages: list[str] = []
        size = 0
        for index, raw in enumerate(paths):
            if not isinstance(raw, str):
                continue
            try:
                path = self._resolve_thread_path(thread_id, raw)
                text = path.read_text(encoding="utf-8")
            except (OSError, ValueError, PermissionError, UnicodeError):
                continue
            block = f"[Parsed section {index + 1}]\n{text.strip()}"
            size += len(block.encode("utf-8"))
            if size > _MAX_TEXT_BYTES:
                raise ValueError("preprocessed text exceeds the hard limit")
            pages.append(block)
        return "\n\n".join(pages).strip() or None

    def _resolve_thread_path(self, thread_id: str, virtual_path: str) -> Path:
        normalized = str(virtual_path or "").strip()
        if not normalized.startswith(f"{_THREAD_VIRTUAL_ROOT}/"):
            raise ValueError("thread attachment path must use the canonical virtual root")
        relative = normalized.removeprefix(_THREAD_VIRTUAL_ROOT).lstrip("/")
        root = (self.thread_data_root / normalize_path_component(thread_id) / "user-data").resolve()
        unresolved = root / relative
        cursor = unresolved
        while cursor != root:
            if cursor.is_symlink():
                raise PermissionError("thread attachment paths cannot contain symlinks")
            if cursor.parent == cursor:
                break
            cursor = cursor.parent
        candidate = unresolved.resolve(strict=True)
        if candidate != root and root not in candidate.parents:
            raise PermissionError("thread attachment path escapes its thread root")
        if not candidate.is_file():
            raise ValueError("thread attachment path is not a file")
        return candidate


def _extract_pdf_text(source: bytes) -> str | None:
    try:
        import fitz

        sections: list[str] = []
        size = 0
        with fitz.open(stream=source, filetype="pdf") as document:
            for page_index in range(document.page_count):
                text = document.load_page(page_index).get_text().strip()
                if not text:
                    continue
                block = f"[Page {page_index + 1}]\n{text}"
                size += len(block.encode("utf-8"))
                if size > _MAX_TEXT_BYTES:
                    raise ValueError("PDF text exceeds the hard limit")
                sections.append(block)
        return "\n\n".join(sections).strip() or None
    except Exception:  # noqa: BLE001 - malformed PDFs must not escape the untrusted parser boundary
        return None


def _attachment_from_metadata(raw: Any) -> ThreadTurnAttachment | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    path = str(raw.get("path") or "").strip()
    if not name or not path:
        return None
    size_bytes = raw.get("size_bytes")
    return ThreadTurnAttachment(
        name=name,
        path=path,
        kind=str(raw.get("kind") or "transient"),
        url=str(raw["url"]) if raw.get("url") is not None else None,
        content_type=(str(raw["content_type"]) if raw.get("content_type") is not None else None),
        size_bytes=(int(size_bytes) if isinstance(size_bytes, int) and not isinstance(size_bytes, bool) else None),
        reference_id=(str(raw["reference_id"]) if raw.get("reference_id") is not None else None),
        artifact_id=(str(raw["artifact_id"]) if raw.get("artifact_id") is not None else None),
        metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
    )


def _is_text_upload(filename: str, content_type: str | None) -> bool:
    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    return mime.startswith("text/") or Path(filename).suffix.lower() in _TEXT_SUFFIXES


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _atomic_write_once(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink(missing_ok=True)
    try:
        path.chmod(0o400)
    except OSError:
        pass


__all__ = [
    "MissionInputPreparation",
    "MissionInputService",
    "MissionInputStore",
]

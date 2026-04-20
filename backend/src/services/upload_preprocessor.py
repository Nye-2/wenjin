"""File upload preprocessing service backed by layout-parsing API."""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx

from src.config import LayoutParsingSettings, get_layout_parsing_settings
from src.services.workspace_uploads import is_pdf_upload

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_REMOTE_BINARY_BYTES = 25 * 1024 * 1024
_REMOTE_DOWNLOAD_CHUNK_SIZE = 64 * 1024
_ALLOWED_REMOTE_DOWNLOAD_SCHEMES = {"http", "https"}
_MAX_LAYOUT_RESULTS = 200


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


def _sanitize_component(name: str, *, fallback: str) -> str:
    normalized = _SAFE_NAME_RE.sub("_", str(name or "").strip())
    normalized = normalized.strip("._")
    if not normalized:
        return fallback
    return normalized


def _guess_output_suffix(url: str, *, fallback: str = ".jpg") -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix:
        return suffix
    return fallback


def _is_image_upload(filename: str | None, content_type: str | None) -> bool:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type.startswith("image/"):
        return True
    return Path(str(filename or "")).suffix.lower() in _IMAGE_SUFFIXES


def _is_forbidden_remote_host(hostname: str | None) -> bool:
    normalized = str(hostname or "").strip().rstrip(".").lower()
    if not normalized:
        return True
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    if normalized.endswith(".local"):
        return True
    try:
        parsed_ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
    )


def _safe_relative_target(
    *,
    output_dir: Path,
    relative_name: str,
) -> Path | None:
    normalized = str(relative_name or "").strip().lstrip("/")
    if not normalized:
        return None
    base = output_dir.resolve()
    candidate = (base / normalized).resolve()
    if not _is_within_root(candidate, base):
        return None
    return candidate


def _to_reference_path(
    *,
    output_path: Path,
    output_dir: Path,
    output_virtual_root: str | None,
) -> str:
    if not output_virtual_root:
        return str(output_path)
    normalized_root = f"/{str(output_virtual_root).strip('/')}"
    relative = output_path.relative_to(output_dir).as_posix()
    if relative:
        return f"{normalized_root}/{relative}"
    return normalized_root


@dataclass(frozen=True, slots=True)
class UploadPreprocessResult:
    """Structured result for one file preprocessing attempt."""

    status: Literal["disabled", "skipped", "succeeded", "failed"]
    provider: str = "layout_parsing"
    file_type: Literal["pdf", "image", "unsupported"] = "unsupported"
    markdown_paths: tuple[str, ...] = ()
    markdown_image_paths: tuple[str, ...] = ()
    output_image_paths: tuple[str, ...] = ()
    manifest_path: str | None = None
    error: str | None = None

    def to_metadata(self) -> dict[str, object]:
        """Convert result to attachment-safe metadata payload."""
        payload: dict[str, object] = {
            "status": self.status,
            "provider": self.provider,
            "file_type": self.file_type,
        }
        if self.markdown_paths:
            payload["markdown_paths"] = list(self.markdown_paths)
        if self.markdown_image_paths:
            payload["markdown_image_paths"] = list(self.markdown_image_paths)
        if self.output_image_paths:
            payload["output_image_paths"] = list(self.output_image_paths)
        if self.manifest_path:
            payload["manifest_path"] = self.manifest_path
        if self.error:
            payload["error"] = self.error
        return payload


class UploadPreprocessor:
    """Preprocess uploaded PDFs/images into markdown and assets."""

    def __init__(self, settings: LayoutParsingSettings | None = None) -> None:
        self._settings = settings or get_layout_parsing_settings()

    def _resolve_file_type(
        self,
        *,
        filename: str | None,
        content_type: str | None,
    ) -> Literal["pdf", "image", "unsupported"]:
        if is_pdf_upload(filename, content_type):
            return "pdf"
        if _is_image_upload(filename, content_type):
            return "image"
        return "unsupported"

    async def _call_layout_parsing(
        self,
        *,
        client: httpx.AsyncClient,
        file_bytes: bytes,
        file_type: Literal["pdf", "image"],
    ) -> list[dict[str, object]]:
        payload = {
            "file": base64.b64encode(file_bytes).decode("ascii"),
            "fileType": 0 if file_type == "pdf" else 1,
            "useDocOrientationClassify": self._settings.use_doc_orientation_classify,
            "useDocUnwarping": self._settings.use_doc_unwarping,
            "useChartRecognition": self._settings.use_chart_recognition,
        }
        headers = {
            "Authorization": f"token {self._settings.token}",
            "Content-Type": "application/json",
        }
        response = await client.post(
            self._settings.api_url,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
        result = body.get("result")
        if not isinstance(result, dict):
            raise ValueError("layout-parsing response missing result object")
        layout_results = result.get("layoutParsingResults")
        if not isinstance(layout_results, list):
            raise ValueError("layout-parsing response missing layoutParsingResults")
        return [item for item in layout_results if isinstance(item, dict)]

    async def _download_binary(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
    ) -> bytes:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in _ALLOWED_REMOTE_DOWNLOAD_SCHEMES or not parsed.netloc:
            raise ValueError(f"Unsupported remote binary URL: {url}")
        if _is_forbidden_remote_host(parsed.hostname):
            raise ValueError(f"Unsupported remote binary URL: {url}")

        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > _MAX_REMOTE_BINARY_BYTES:
                        raise ValueError(
                            "Remote binary is too large "
                            f"(max {_MAX_REMOTE_BINARY_BYTES // (1024 * 1024)}MB)"
                        )
                except ValueError:
                    if not content_length.isdigit():
                        pass
                    else:
                        raise

            chunks: list[bytes] = []
            total_size = 0
            async for chunk in response.aiter_bytes(_REMOTE_DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                total_size += len(chunk)
                if total_size > _MAX_REMOTE_BINARY_BYTES:
                    raise ValueError(
                        "Remote binary is too large "
                        f"(max {_MAX_REMOTE_BINARY_BYTES // (1024 * 1024)}MB)"
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    async def preprocess_file(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        output_dir: Path,
        output_virtual_root: str | None = None,
        content: bytes | None = None,
        source_path: Path | None = None,
    ) -> UploadPreprocessResult:
        """Preprocess one uploaded file and save structured outputs to disk."""
        file_type = self._resolve_file_type(filename=filename, content_type=content_type)
        if file_type == "unsupported":
            return UploadPreprocessResult(status="skipped", file_type=file_type)

        if not self._settings.enabled:
            return UploadPreprocessResult(status="disabled", file_type=file_type)
        if not self._settings.api_url or not self._settings.token:
            return UploadPreprocessResult(
                status="disabled",
                file_type=file_type,
                error="Layout parsing API is not configured",
            )

        if content is None:
            if source_path is None:
                return UploadPreprocessResult(
                    status="failed",
                    file_type=file_type,
                    error="Missing source file content",
                )
            try:
                content = source_path.read_bytes()
            except OSError as exc:
                return UploadPreprocessResult(
                    status="failed",
                    file_type=file_type,
                    error=f"Failed to read source file: {exc}",
                )

        if not content:
            return UploadPreprocessResult(
                status="failed",
                file_type=file_type,
                error="Source file is empty",
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_output_dir = output_dir.resolve()
        markdown_paths: list[str] = []
        markdown_image_paths: list[str] = []
        output_image_paths: list[str] = []
        manifest_path_ref: str | None = None

        try:
            timeout = httpx.Timeout(self._settings.timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                layout_results = await self._call_layout_parsing(
                    client=client,
                    file_bytes=content,
                    file_type=file_type,
                )
                if len(layout_results) > _MAX_LAYOUT_RESULTS:
                    raise ValueError(
                        "Layout parsing returned too many result segments "
                        f"(max {_MAX_LAYOUT_RESULTS})"
                    )

                for index, layout_result in enumerate(layout_results):
                    markdown = layout_result.get("markdown")
                    markdown_map = markdown if isinstance(markdown, dict) else {}
                    markdown_text = str(markdown_map.get("text") or "")
                    markdown_path = base_output_dir / f"doc_{index}.md"
                    markdown_path.write_text(markdown_text, encoding="utf-8")
                    markdown_paths.append(
                        _to_reference_path(
                            output_path=markdown_path,
                            output_dir=base_output_dir,
                            output_virtual_root=output_virtual_root,
                        )
                    )

                    markdown_images = markdown_map.get("images")
                    if isinstance(markdown_images, dict):
                        for img_index, (img_path, img_url) in enumerate(
                            markdown_images.items()
                        ):
                            if not isinstance(img_url, str) or not img_url.strip():
                                continue
                            target = _safe_relative_target(
                                output_dir=base_output_dir,
                                relative_name=str(img_path),
                            )
                            if target is None:
                                fallback_suffix = _guess_output_suffix(
                                    img_url,
                                    fallback=".jpg",
                                )
                                target = (
                                    base_output_dir
                                    / f"doc_{index}_img_{img_index}{fallback_suffix}"
                                )
                            target.parent.mkdir(parents=True, exist_ok=True)
                            image_data = await self._download_binary(
                                client=client,
                                url=img_url,
                            )
                            target.write_bytes(image_data)
                            markdown_image_paths.append(
                                _to_reference_path(
                                    output_path=target,
                                    output_dir=base_output_dir,
                                    output_virtual_root=output_virtual_root,
                                )
                            )

                    output_images = layout_result.get("outputImages")
                    if isinstance(output_images, dict):
                        for image_name, image_url in output_images.items():
                            if not isinstance(image_url, str) or not image_url.strip():
                                continue
                            safe_image_name = _sanitize_component(
                                str(image_name),
                                fallback=f"output_{index}",
                            )
                            suffix = _guess_output_suffix(image_url, fallback=".jpg")
                            target = (
                                base_output_dir
                                / f"{safe_image_name}_{index}{suffix}"
                            )
                            target.parent.mkdir(parents=True, exist_ok=True)
                            image_data = await self._download_binary(
                                client=client,
                                url=image_url,
                            )
                            target.write_bytes(image_data)
                            output_image_paths.append(
                                _to_reference_path(
                                    output_path=target,
                                    output_dir=base_output_dir,
                                    output_virtual_root=output_virtual_root,
                                )
                            )

            manifest_path = base_output_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "provider": "layout_parsing",
                        "status": "succeeded",
                        "file_type": file_type,
                        "markdown_paths": markdown_paths,
                        "markdown_image_paths": markdown_image_paths,
                        "output_image_paths": output_image_paths,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            manifest_path_ref = _to_reference_path(
                output_path=manifest_path,
                output_dir=base_output_dir,
                output_virtual_root=output_virtual_root,
            )
        except Exception as exc:
            logger.warning(
                "Upload preprocessing failed for filename=%s content_type=%s",
                filename,
                content_type,
                exc_info=True,
            )
            return UploadPreprocessResult(
                status="failed",
                file_type=file_type,
                error=str(exc),
            )

        return UploadPreprocessResult(
            status="succeeded",
            file_type=file_type,
            markdown_paths=tuple(markdown_paths),
            markdown_image_paths=tuple(markdown_image_paths),
            output_image_paths=tuple(output_image_paths),
            manifest_path=manifest_path_ref,
        )


@lru_cache
def get_upload_preprocessor_service() -> UploadPreprocessor:
    """Return singleton upload preprocessor service."""
    return UploadPreprocessor()

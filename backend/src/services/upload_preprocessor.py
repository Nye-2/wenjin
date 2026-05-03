"""File upload preprocessing service with OCR and VLM providers."""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from src.config import (
    ImageVLMSettings,
    LayoutParsingSettings,
    get_image_vlm_settings,
    get_layout_parsing_settings,
)
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


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_layout_page_number(
    layout_result: dict[str, Any],
    *,
    fallback: int,
) -> tuple[int, str]:
    for key in ("page_no", "pageNo", "page_number", "pageNumber", "page"):
        value = _coerce_positive_int(layout_result.get(key))
        if value is not None:
            return value, key
    for key in ("page_index", "pageIndex"):
        try:
            parsed = int(layout_result.get(key) or "")
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed + 1, key
    return fallback, "layout_result_index"


def _guess_extension_from_mime(mime: str) -> str:
    mime_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }
    return mime_map.get(mime.lower(), ".jpg")


def _decode_image_data(img_data: str) -> tuple[bytes | None, str]:
    """Decode image from data URL, plain base64, or return None for remote URL.

    Returns:
        (decoded_bytes, extension_or_url): If decoded_bytes is not None,
        the second value is a file extension. Otherwise it's a URL string.
    """
    img_data = str(img_data or "").strip()
    if not img_data:
        raise ValueError("Empty image data")

    # Data URL: data:image/jpeg;base64,...
    if img_data.startswith("data:"):
        match = re.match(r"data:([a-zA-Z0-9+/._-]+);base64,(.+)", img_data, re.IGNORECASE)
        if match:
            try:
                decoded = base64.b64decode(match.group(2))
                return decoded, _guess_extension_from_mime(match.group(1))
            except Exception as exc:
                raise ValueError(f"Invalid data URL: {exc}") from exc
        # Try data URL without explicit base64 marker (some providers omit ;base64)
        match2 = re.match(r"data:([a-zA-Z0-9+/._-]+),(.+)", img_data, re.IGNORECASE)
        if match2:
            try:
                decoded = base64.b64decode(match2.group(2))
                return decoded, _guess_extension_from_mime(match2.group(1))
            except Exception as exc:
                raise ValueError(f"Invalid data URL: {exc}") from exc
        raise ValueError("Invalid data URL format")

    # Plain base64 string (heuristic: long enough and only base64 chars)
    stripped = img_data.replace(" ", "").replace("\n", "").replace("\r", "")
    if len(stripped) > 100 and re.match(r"^[A-Za-z0-9+/=]+$", stripped):
        try:
            decoded = base64.b64decode(stripped)
            return decoded, ".jpg"
        except Exception:
            pass

    # Treat as remote URL
    return None, img_data


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Result from a single provider processing attempt."""

    status: Literal["succeeded", "failed"]
    provider: str
    markdown_paths: tuple[str, ...] = ()
    markdown_image_paths: tuple[str, ...] = ()
    output_image_paths: tuple[str, ...] = ()
    manifest_extras: dict[str, Any] | None = None
    error: str | None = None


class BaseProvider(ABC):
    """Abstract base for upload preprocess providers."""

    @abstractmethod
    async def process(
        self,
        *,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        output_dir: Path,
        output_virtual_root: str | None,
    ) -> ProviderResult:
        """Process file and return structured result."""
        ...

    async def _download_binary(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> bytes:
        """Download remote binary with SSRF protection."""
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


class OCRProvider(BaseProvider):
    """PaddleOCR layout-parsing provider for PDFs and structured images."""

    def __init__(self, settings: LayoutParsingSettings | None = None) -> None:
        self._settings = settings or get_layout_parsing_settings()

    async def process(
        self,
        *,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        output_dir: Path,
        output_virtual_root: str | None,
    ) -> ProviderResult:
        file_type: Literal["pdf", "image"] = "pdf" if is_pdf_upload(filename, content_type) else "image"

        timeout = httpx.Timeout(self._settings.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            layout_results, log_id = await self._call_layout_parsing(
                client=client,
                file_bytes=file_bytes,
                file_type=file_type,
            )
            if len(layout_results) > _MAX_LAYOUT_RESULTS:
                raise ValueError(
                    "Layout parsing returned too many result segments "
                    f"(max {_MAX_LAYOUT_RESULTS})"
                )

            markdown_paths: list[str] = []
            markdown_image_paths: list[str] = []
            output_image_paths: list[str] = []
            page_entries: list[dict[str, Any]] = []

            for index, layout_result in enumerate(layout_results):
                markdown = layout_result.get("markdown")
                markdown_map = markdown if isinstance(markdown, dict) else {}
                markdown_text = str(markdown_map.get("text") or "")
                markdown_path = output_dir / f"doc_{index}.md"
                markdown_path.write_text(markdown_text, encoding="utf-8")
                markdown_path_ref = _to_reference_path(
                    output_path=markdown_path,
                    output_dir=output_dir,
                    output_virtual_root=output_virtual_root,
                )
                markdown_paths.append(markdown_path_ref)
                page_number, page_source = _extract_layout_page_number(
                    layout_result,
                    fallback=index + 1,
                )
                page_entries.append(
                    {
                        "doc_index": index,
                        "markdown_path": markdown_path_ref,
                        "page_start": page_number,
                        "page_end": page_number,
                        "page_source": page_source,
                    }
                )

                # Handle markdown images (URL, data URL, or base64)
                markdown_images = markdown_map.get("images")
                if isinstance(markdown_images, dict):
                    for img_index, (img_path, img_data) in enumerate(
                        markdown_images.items()
                    ):
                        if not isinstance(img_data, str) or not img_data.strip():
                            continue
                        target = _safe_relative_target(
                            output_dir=output_dir,
                            relative_name=str(img_path),
                        )
                        img_bytes: bytes | None = None
                        fallback_suffix = ".jpg"
                        try:
                            decoded, ext_or_url = _decode_image_data(img_data)
                            if decoded is not None:
                                img_bytes = decoded
                                fallback_suffix = ext_or_url
                            else:
                                fallback_suffix = _guess_output_suffix(ext_or_url)
                                img_bytes = await self._download_binary(
                                    client=client, url=ext_or_url
                                )
                        except ValueError:
                            # Fallback: treat as plain URL
                            fallback_suffix = _guess_output_suffix(img_data)
                            img_bytes = await self._download_binary(
                                client=client, url=img_data
                            )

                        if target is None:
                            target = (
                                output_dir
                                / f"doc_{index}_img_{img_index}{fallback_suffix}"
                            )
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if img_bytes is not None:
                            target.write_bytes(img_bytes)
                        markdown_image_paths.append(
                            _to_reference_path(
                                output_path=target,
                                output_dir=output_dir,
                                output_virtual_root=output_virtual_root,
                            )
                        )

                # Handle outputImages
                output_images = layout_result.get("outputImages")
                if isinstance(output_images, dict):
                    for image_name, image_data in output_images.items():
                        if not isinstance(image_data, str) or not image_data.strip():
                            continue
                        safe_image_name = _sanitize_component(
                            str(image_name), fallback=f"output_{index}"
                        )
                        img_bytes = None
                        suffix = ".jpg"
                        try:
                            decoded, ext_or_url = _decode_image_data(image_data)
                            if decoded is not None:
                                img_bytes = decoded
                                if decoded:
                                    suffix = ext_or_url
                            else:
                                suffix = _guess_output_suffix(ext_or_url)
                                img_bytes = await self._download_binary(
                                    client=client, url=ext_or_url
                                )
                        except ValueError:
                            suffix = _guess_output_suffix(image_data)
                            img_bytes = await self._download_binary(
                                client=client, url=image_data
                            )

                        target = output_dir / f"{safe_image_name}_{index}{suffix}"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if img_bytes is not None:
                            target.write_bytes(img_bytes)
                        output_image_paths.append(
                            _to_reference_path(
                                output_path=target,
                                output_dir=output_dir,
                                output_virtual_root=output_virtual_root,
                            )
                        )

        manifest_extras: dict[str, Any] = {
            "log_id": log_id,
            "page_count": len(layout_results),
            "result_count": len(layout_results),
            "page_index_kind": (
                "pdf_page"
                if any(item.get("page_source") != "layout_result_index" for item in page_entries)
                else "layout_result_index"
            ),
            "pages": page_entries,
            "provider_options": self._build_provider_options(),
        }

        return ProviderResult(
            status="succeeded",
            provider="layout_parsing",
            markdown_paths=tuple(markdown_paths),
            markdown_image_paths=tuple(markdown_image_paths),
            output_image_paths=tuple(output_image_paths),
            manifest_extras=manifest_extras,
        )

    def _build_provider_options(self) -> dict[str, Any]:
        return {
            "use_doc_orientation_classify": self._settings.use_doc_orientation_classify,
            "use_doc_unwarping": self._settings.use_doc_unwarping,
            "use_chart_recognition": self._settings.use_chart_recognition,
            "use_layout_detection": self._settings.use_layout_detection,
            "layout_threshold": self._settings.layout_threshold,
            "layout_nms": self._settings.layout_nms,
            "restructure_pages": self._settings.restructure_pages,
            "merge_tables": self._settings.merge_tables,
            "relevel_titles": self._settings.relevel_titles,
            "prettify_markdown": self._settings.prettify_markdown,
            "visualize": self._settings.visualize,
        }

    async def _call_layout_parsing(
        self,
        *,
        client: httpx.AsyncClient,
        file_bytes: bytes,
        file_type: Literal["pdf", "image"],
    ) -> tuple[list[dict[str, Any]], str | None]:
        payload: dict[str, Any] = {
            "file": base64.b64encode(file_bytes).decode("ascii"),
            "fileType": 0 if file_type == "pdf" else 1,
            "useDocOrientationClassify": self._settings.use_doc_orientation_classify,
            "useDocUnwarping": self._settings.use_doc_unwarping,
            "useChartRecognition": self._settings.use_chart_recognition,
            "useLayoutDetection": self._settings.use_layout_detection,
            "layoutThreshold": self._settings.layout_threshold,
            "layoutNms": self._settings.layout_nms,
            "restructurePages": self._settings.restructure_pages,
            "mergeTables": self._settings.merge_tables,
            "relevelTitles": self._settings.relevel_titles,
            "prettifyMarkdown": self._settings.prettify_markdown,
        }
        if self._settings.visualize is not None:
            payload["visualize"] = self._settings.visualize

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

        log_id = body.get("logId") if isinstance(body, dict) else None

        result = body.get("result") if isinstance(body, dict) else None
        if not isinstance(result, dict):
            raise ValueError("layout-parsing response missing result object")
        layout_results = result.get("layoutParsingResults")
        if not isinstance(layout_results, list):
            raise ValueError("layout-parsing response missing layoutParsingResults")
        return [item for item in layout_results if isinstance(item, dict)], log_id


class VLMProvider(BaseProvider):
    """Lightweight VLM provider for image understanding."""

    def __init__(self, settings: ImageVLMSettings | None = None) -> None:
        self._settings = settings or get_image_vlm_settings()

    async def process(
        self,
        *,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        output_dir: Path,
        output_virtual_root: str | None,
    ) -> ProviderResult:
        mime = self._guess_mime(filename, content_type)
        data_url = f"data:{mime};base64,{base64.b64encode(file_bytes).decode('ascii')}"

        payload = {
            "model": self._settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._settings.prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": self._settings.max_tokens,
            "temperature": self._settings.temperature,
        }

        headers = {
            "Authorization": f"Bearer {self._settings.token}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(self._settings.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._settings.api_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()

            if not isinstance(body, dict):
                raise ValueError("VLM response is not a JSON object")

            choices = body.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("VLM response missing choices")

            message = choices[0].get("message", {})
            description = str(message.get("content") or "").strip()
            if not description:
                raise ValueError("VLM returned empty description")

        # Write description as Markdown
        md_path = output_dir / "description.md"
        md_path.write_text(description, encoding="utf-8")
        md_path_ref = _to_reference_path(
            output_path=md_path,
            output_dir=output_dir,
            output_virtual_root=output_virtual_root,
        )

        usage = body.get("usage") if isinstance(body, dict) else None
        manifest_extras: dict[str, Any] = {
            "model": self._settings.model,
            "prompt": self._settings.prompt,
            "usage": usage if isinstance(usage, dict) else {},
        }

        return ProviderResult(
            status="succeeded",
            provider="image_vlm",
            markdown_paths=(md_path_ref,),
            manifest_extras=manifest_extras,
        )

    def _guess_mime(self, filename: str | None, content_type: str | None) -> str:
        if content_type:
            return content_type.split(";", 1)[0].strip()
        suffix = Path(str(filename or "")).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mime_map.get(suffix, "image/jpeg")


@dataclass(frozen=True, slots=True)
class UploadPreprocessResult:
    """Structured result for one file preprocessing attempt."""

    status: Literal["disabled", "skipped", "succeeded", "failed", "pending"]
    provider: str = "unknown"
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
    """Preprocess uploaded files using OCR for PDFs and VLM for images."""

    def __init__(
        self,
        ocr_settings: LayoutParsingSettings | None = None,
        vlm_settings: ImageVLMSettings | None = None,
    ) -> None:
        self._ocr_provider = OCRProvider(settings=ocr_settings)
        self._vlm_provider = VLMProvider(settings=vlm_settings)

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

    def _resolve_provider(
        self,
        file_type: Literal["pdf", "image", "unsupported"],
    ) -> BaseProvider | None:
        if file_type == "pdf":
            return self._ocr_provider
        if file_type == "image":
            return self._vlm_provider
        return None

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
        file_type = self._resolve_file_type(
            filename=filename, content_type=content_type
        )
        if file_type == "unsupported":
            return UploadPreprocessResult(status="skipped", file_type=file_type)

        provider = self._resolve_provider(file_type)
        if provider is None:
            return UploadPreprocessResult(
                status="failed", file_type=file_type, error="No provider available"
            )

        # Check provider-specific configuration
        if file_type == "pdf":
            settings = self._ocr_provider._settings
            if not settings.enabled:
                return UploadPreprocessResult(status="disabled", file_type=file_type)
            if not settings.api_url or not settings.token:
                return UploadPreprocessResult(
                    status="disabled",
                    file_type=file_type,
                    error="OCR service is not configured",
                )
        elif file_type == "image":
            vlm_settings = self._vlm_provider._settings
            if not vlm_settings.enabled:
                return UploadPreprocessResult(status="disabled", file_type=file_type)
            if not vlm_settings.api_url or not vlm_settings.token:
                return UploadPreprocessResult(
                    status="disabled",
                    file_type=file_type,
                    error="VLM service is not configured",
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

        try:
            result = await provider.process(
                file_bytes=content,
                filename=filename,
                content_type=content_type,
                output_dir=base_output_dir,
                output_virtual_root=output_virtual_root,
            )

            manifest_path = self._write_manifest(
                output_dir=base_output_dir,
                output_virtual_root=output_virtual_root,
                file_type=file_type,
                provider=result.provider,
                status=result.status,
                markdown_paths=result.markdown_paths,
                markdown_image_paths=result.markdown_image_paths,
                output_image_paths=result.output_image_paths,
                extras=result.manifest_extras,
            )

            return UploadPreprocessResult(
                status=result.status,
                provider=result.provider,
                file_type=file_type,
                markdown_paths=result.markdown_paths,
                markdown_image_paths=result.markdown_image_paths,
                output_image_paths=result.output_image_paths,
                manifest_path=manifest_path,
                error=result.error,
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

    def _write_manifest(
        self,
        *,
        output_dir: Path,
        output_virtual_root: str | None,
        file_type: str,
        provider: str,
        status: str,
        markdown_paths: tuple[str, ...],
        markdown_image_paths: tuple[str, ...],
        output_image_paths: tuple[str, ...],
        extras: dict[str, Any] | None = None,
    ) -> str:
        manifest: dict[str, Any] = {
            "version": 2,
            "provider": provider,
            "status": status,
            "file_type": file_type,
            "created_at": datetime.now(UTC).isoformat(),
            "markdown_paths": list(markdown_paths),
            "markdown_image_paths": list(markdown_image_paths),
            "output_image_paths": list(output_image_paths),
        }
        if extras:
            manifest.update(extras)

        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return _to_reference_path(
            output_path=manifest_path,
            output_dir=output_dir,
            output_virtual_root=output_virtual_root,
        )


@lru_cache
def get_upload_preprocessor_service() -> UploadPreprocessor:
    """Return singleton upload preprocessor service."""
    return UploadPreprocessor()

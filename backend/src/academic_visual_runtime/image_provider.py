"""Narrow gpt-image-2 provider protocol and OpenAI-compatible adapter."""

from __future__ import annotations

import base64
import binascii
import json
import struct
import zlib
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.config import get_model_config

IMAGE_MODEL_ID = "gpt-image-2"
_MAX_PROVIDER_RESPONSE_BYTES = 36 * 1024 * 1024
_MAX_IMAGE_BYTES = 25 * 1024 * 1024


class ImageProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class ImageGenerationRequest:
    prompt: str
    size: str
    quality: str


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
    content: bytes
    mime_type: str
    width: int
    height: int
    provider_model: str
    provider_request_id: str | None = None


class AcademicImageProvider(Protocol):
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...


class OpenAIImagesProvider:
    """Calls only the configured gpt-image-2 Images generation endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        default_headers: dict[str, str] | None = None,
        timeout_seconds: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ImageProviderError("provider_auth_or_config", "gpt-image-2 API key is unavailable")
        self.api_key = api_key
        self.endpoint = _images_endpoint(base_url)
        self.default_headers = dict(default_headers or {})
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        headers = {
            **self.default_headers,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": IMAGE_MODEL_ID,
            "prompt": request.prompt,
            "size": request.size,
            "quality": request.quality,
            "n": 1,
            "response_format": "b64_json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                async with client.stream("POST", self.endpoint, headers=headers, json=body) as response:
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > _MAX_PROVIDER_RESPONSE_BYTES:
                            raise ImageProviderError("provider_invalid_payload", "image provider response exceeded its byte boundary")
                    if response.status_code == 429:
                        retry_after = _retry_after(response.headers.get("Retry-After"))
                        raise ImageProviderError("provider_rate_limited", "image provider is rate limited", retry_after_seconds=retry_after)
                    if response.status_code in {401, 403}:
                        raise ImageProviderError("provider_auth_or_config", "image provider rejected its credentials")
                    if response.status_code >= 500:
                        raise ImageProviderError("provider_unavailable", "image provider is temporarily unavailable")
                    if response.status_code >= 400:
                        raise ImageProviderError("provider_invalid_payload", "image provider rejected the generation request")
                    request_id = response.headers.get("x-request-id")
        except ImageProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ImageProviderError("provider_timeout", "image provider timed out") from exc
        except httpx.HTTPError as exc:
            raise ImageProviderError("provider_unavailable", "image provider transport failed") from exc

        try:
            payload = json.loads(raw)
            encoded = payload["data"][0]["b64_json"]
            content = base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, binascii.Error) as exc:
            raise ImageProviderError("provider_invalid_payload", "image provider returned no valid image payload") from exc
        if not content or len(content) > _MAX_IMAGE_BYTES:
            raise ImageProviderError("image_decode_failed", "generated image exceeds its byte boundary")
        content, width, height = _normalize_png(content)
        return ImageGenerationResult(
            content=content,
            mime_type="image/png",
            width=width,
            height=height,
            provider_model=IMAGE_MODEL_ID,
            provider_request_id=request_id,
        )


class ConfiguredGptImage2Provider:
    """Resolves current server-side model configuration at execution time."""

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        model = get_model_config(IMAGE_MODEL_ID)
        if model is None or model.model != IMAGE_MODEL_ID:
            raise ImageProviderError("provider_auth_or_config", "gpt-image-2 is not configured")
        provider = OpenAIImagesProvider(
            api_key=model.api_key,
            base_url=model.base_url,
            default_headers=model.default_headers,
            timeout_seconds=model.timeout_seconds or 180.0,
        )
        return await provider.generate(request)


def _images_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ImageProviderError("provider_auth_or_config", "image provider base URL is invalid")
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/images/generations", "", ""))


def _normalize_png(content: bytes) -> tuple[bytes, int, int]:
    signature = b"\x89PNG\r\n\x1a\n"
    if len(content) < 45 or content[:8] != signature:
        raise ImageProviderError("image_decode_failed", "gpt-image-2 did not return a valid PNG")
    offset = 8
    critical: list[tuple[bytes, bytes]] = []
    idat = bytearray()
    width = height = 0
    bit_depth = color_type = interlace = -1
    seen_iend = False
    while offset + 12 <= len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        end = offset + 12 + length
        if length > _MAX_IMAGE_BYTES or end > len(content):
            raise ImageProviderError("image_decode_failed", "generated PNG chunks are invalid")
        data = content[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", content[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            raise ImageProviderError("image_decode_failed", "generated PNG checksum is invalid")
        if chunk_type == b"IHDR":
            if critical or length != 13:
                raise ImageProviderError("image_decode_failed", "generated PNG header is invalid")
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", data)
            critical.append((chunk_type, data))
        elif chunk_type == b"IDAT":
            idat.extend(data)
            critical.append((chunk_type, data))
        elif chunk_type == b"IEND":
            critical.append((chunk_type, data))
            seen_iend = True
            offset = end
            break
        offset = end
    if not seen_iend or offset != len(content) or not idat:
        raise ImageProviderError("image_decode_failed", "generated PNG is incomplete")
    if not (1 <= width <= 16_384 and 1 <= height <= 16_384):
        raise ImageProviderError("image_decode_failed", "generated PNG dimensions are invalid")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None or bit_depth != 8 or interlace != 0:
        raise ImageProviderError("image_decode_failed", "generated PNG uses an unsupported pixel format")
    try:
        pixels = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise ImageProviderError("image_decode_failed", "generated PNG pixel data is invalid") from exc
    if len(pixels) != height * (1 + width * channels):
        raise ImageProviderError("image_decode_failed", "generated PNG pixel length is invalid")
    normalized = bytearray(signature)
    for chunk_type, data in critical:
        normalized.extend(struct.pack(">I", len(data)))
        normalized.extend(chunk_type)
        normalized.extend(data)
        normalized.extend(struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF))
    return bytes(normalized), width, height


def _retry_after(value: str | None) -> float | None:
    try:
        return max(0.0, min(float(value), 86_400.0)) if value is not None else None
    except ValueError:
        return None


__all__ = [
    "AcademicImageProvider",
    "ConfiguredGptImage2Provider",
    "IMAGE_MODEL_ID",
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "ImageProviderError",
    "OpenAIImagesProvider",
]

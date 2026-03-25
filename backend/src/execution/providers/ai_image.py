"""AI image generation execution provider."""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from src.config.llm_config import get_model_full_config
from src.models.router import route_image_model

from ..base import ExecutionProvider
from ..types import ProviderResult

logger = logging.getLogger(__name__)


def _sanitize_filename(value: str, default: str = "image") -> str:
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()
    return text or default


def _extract_image_data(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract image data from OpenAI-compatible response payload."""
    if not isinstance(payload, dict):
        return None, None

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None, None
    first = data[0]
    if not isinstance(first, dict):
        return None, None

    b64_value = first.get("b64_json")
    if isinstance(b64_value, str) and b64_value.strip():
        return b64_value.strip(), None

    url_value = first.get("url")
    if isinstance(url_value, str) and url_value.strip():
        return None, url_value.strip()

    return None, None


class AIImageProvider(ExecutionProvider):
    """AI image provider using configured OpenAI-compatible image endpoint."""

    _execution_type = "ai_image"
    _docker_image = None

    @property
    def execution_type(self) -> str:
        return self._execution_type

    @property
    def docker_image(self) -> str | None:
        return self._docker_image

    def _resolve_model(self, requested_model: str | None) -> tuple[str, dict[str, Any]]:
        model_id = route_image_model(requested_model=requested_model)
        model_config = get_model_full_config(model_id)
        return model_id, model_config

    async def _download_image(self, *, url: str, api_key: str) -> bytes:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
        }
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.content

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client: object | None = None,
    ) -> ProviderResult:
        """Generate image via model API and write it to output file."""
        _ = docker_client

        prompt = str(options.get("prompt") or content or "").strip()
        if not prompt:
            return ProviderResult(success=False, error_message="AI image prompt is empty")

        requested_model = str(options.get("model_id") or "").strip() or None
        output_stem = _sanitize_filename(
            str(options.get("figure_id") or options.get("output_filename") or "image")
        )
        size = str(options.get("size") or "1024x1024").strip() or "1024x1024"
        quality = str(options.get("quality") or "").strip()
        response_format = str(options.get("response_format") or "b64_json").strip().lower()
        if response_format not in {"b64_json", "url"}:
            response_format = "b64_json"

        try:
            model_id, model_config = self._resolve_model(requested_model)
        except Exception as exc:
            logger.warning("AI image model resolution failed: %s", exc)
            return ProviderResult(
                success=False,
                error_message=f"AI image model unavailable: {exc}",
            )

        base_url = str(model_config.get("base_url") or "").rstrip("/")
        api_key = str(model_config.get("api_key") or "")
        model_name = str(model_config.get("model") or "")
        if not base_url or not api_key or not model_name:
            return ProviderResult(
                success=False,
                error_message="AI image model config is incomplete (base_url/api_key/model)",
            )

        request_payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "response_format": response_format,
        }
        if quality:
            request_payload["quality"] = quality

        endpoint = f"{base_url}/images/generations"
        try:
            async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
            if response.status_code >= 400:
                body = response.text[:500]
                return ProviderResult(
                    success=False,
                    error_message=f"AI image request failed ({response.status_code}): {body}",
                )
            response_payload = response.json()
        except Exception as exc:
            logger.exception("AI image request failed")
            return ProviderResult(
                success=False,
                error_message=f"AI image request error: {exc}",
            )

        if not isinstance(response_payload, dict):
            return ProviderResult(
                success=False,
                error_message="AI image response is not a JSON object",
            )

        image_b64, image_url = _extract_image_data(response_payload)
        output_dir = Path(work_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{output_stem}.png"

        try:
            if image_b64:
                output_file.write_bytes(base64.b64decode(image_b64))
            elif image_url:
                image_bytes = await self._download_image(url=image_url, api_key=api_key)
                output_file.write_bytes(image_bytes)
            else:
                return ProviderResult(
                    success=False,
                    error_message="AI image response missing b64_json/url data",
                )
        except Exception as exc:
            logger.exception("Failed to persist AI image output")
            return ProviderResult(
                success=False,
                error_message=f"AI image output write failed: {exc}",
            )

        return ProviderResult(
            success=True,
            output_files=[f"output/{output_file.name}"],
            metadata={
                "format": "png",
                "provider": "ai_image",
                "model_id": model_id,
                "model": model_name,
                "size": size,
            },
            logs=f"model={model_id}",
        )


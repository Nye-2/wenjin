"""Tests for AIImageProvider."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.execution.providers.ai_image import AIImageProvider, _extract_image_data


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        _ = args, kwargs
        return self._response


class TestExtractImageData:
    def test_extracts_b64(self):
        b64, url = _extract_image_data({"data": [{"b64_json": "YWJj"}]})
        assert b64 == "YWJj"
        assert url is None

    def test_extracts_url(self):
        b64, url = _extract_image_data({"data": [{"url": "https://example.com/a.png"}]})
        assert b64 is None
        assert url == "https://example.com/a.png"


class TestAIImageProvider:
    @pytest.mark.asyncio
    async def test_execute_fails_on_empty_prompt(self, tmp_path: Path):
        provider = AIImageProvider()
        result = await provider.execute(content="", work_dir=str(tmp_path), options={})
        assert result.success is False
        assert "prompt" in str(result.error_message).lower()

    @pytest.mark.asyncio
    async def test_execute_fails_when_model_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        provider = AIImageProvider()

        def _raise(requested_model):
            _ = requested_model
            raise ValueError("no image model")

        monkeypatch.setattr(provider, "_resolve_model", _raise)

        result = await provider.execute(content="draw a chart", work_dir=str(tmp_path), options={})
        assert result.success is False
        assert "unavailable" in str(result.error_message).lower()

    @pytest.mark.asyncio
    async def test_execute_success_with_b64_response(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        provider = AIImageProvider()
        monkeypatch.setattr(
            provider,
            "_resolve_model",
            lambda requested_model: (
                "image-model",
                {
                    "base_url": "https://example.com/v1",
                    "api_key": "sk-test",
                    "model": "image-model-v1",
                },
            ),
        )

        b64 = base64.b64encode(b"png-bytes").decode("ascii")
        response = _FakeResponse(status_code=200, payload={"data": [{"b64_json": b64}]})
        monkeypatch.setattr(
            "src.execution.providers.ai_image.httpx.AsyncClient",
            lambda *args, **kwargs: _FakeClient(response),
        )

        result = await provider.execute(
            content="draw architecture",
            work_dir=str(tmp_path),
            options={"figure_id": "figure-1"},
        )
        assert result.success is True
        assert result.output_files == ["output/figure-1.png"]
        assert (tmp_path / "output" / "figure-1.png").read_bytes() == b"png-bytes"

    @pytest.mark.asyncio
    async def test_execute_success_with_url_response(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        provider = AIImageProvider()
        monkeypatch.setattr(
            provider,
            "_resolve_model",
            lambda requested_model: (
                "image-model",
                {
                    "base_url": "https://example.com/v1",
                    "api_key": "sk-test",
                    "model": "image-model-v1",
                },
            ),
        )

        async def _fake_download(**kwargs):
            _ = kwargs
            return b"from-url"

        monkeypatch.setattr(provider, "_download_image", _fake_download)

        response = _FakeResponse(
            status_code=200,
            payload={"data": [{"url": "https://example.com/generated.png"}]},
        )
        monkeypatch.setattr(
            "src.execution.providers.ai_image.httpx.AsyncClient",
            lambda *args, **kwargs: _FakeClient(response),
        )

        result = await provider.execute(
            content="draw concept map",
            work_dir=str(tmp_path),
            options={"output_filename": "concept-map"},
        )
        assert result.success is True
        assert result.output_files == ["output/concept-map.png"]
        assert (tmp_path / "output" / "concept-map.png").read_bytes() == b"from-url"

"""Tests for upload preprocessor service."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from src.config import ImageVLMSettings, LayoutParsingSettings
from src.services import upload_preprocessor as upload_preprocessor_module
from src.services.upload_preprocessor import OCRProvider, UploadPreprocessor, VLMProvider


@pytest.mark.asyncio
async def test_preprocess_skips_unsupported_file(tmp_path):
    preprocessor = UploadPreprocessor(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )

    result = await preprocessor.preprocess_file(
        filename="notes.txt",
        content_type="text/plain",
        content=b"plain text",
        output_dir=tmp_path / "out",
    )

    assert result.status == "skipped"
    assert result.file_type == "unsupported"


@pytest.mark.asyncio
async def test_preprocess_pdf_with_ocr_provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    preprocessor = UploadPreprocessor(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    call_mock = AsyncMock(
        return_value=(
            [
                {
                    "markdown": {
                        "text": "# Parsed\n\ncontent",
                        "images": {
                            "figures/fig-1.png": "https://example.test/fig-1.png",
                        },
                    },
                    "outputImages": {
                        "layout_view": "https://example.test/layout.jpg",
                    },
                }
            ],
            "test-log-id",
        )
    )
    download_mock = AsyncMock(side_effect=[b"figure-bytes", b"layout-bytes"])
    monkeypatch.setattr(preprocessor._ocr_provider, "_call_layout_parsing", call_mock)
    monkeypatch.setattr(preprocessor._ocr_provider, "_download_binary", download_mock)

    output_dir = tmp_path / "out"
    result = await preprocessor.preprocess_file(
        filename="paper.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 test",
        output_dir=output_dir,
        output_virtual_root="/mnt/user-data/uploads/_preprocessed/paper",
    )

    assert result.status == "succeeded"
    assert result.provider == "layout_parsing"
    assert result.file_type == "pdf"
    assert result.markdown_paths == (
        "/mnt/user-data/uploads/_preprocessed/paper/doc_0.md",
    )
    assert result.markdown_image_paths == (
        "/mnt/user-data/uploads/_preprocessed/paper/figures/fig-1.png",
    )
    assert result.output_image_paths == (
        "/mnt/user-data/uploads/_preprocessed/paper/layout_view_0.jpg",
    )
    assert result.manifest_path == "/mnt/user-data/uploads/_preprocessed/paper/manifest.json"
    assert (output_dir / "doc_0.md").read_text(encoding="utf-8") == "# Parsed\n\ncontent"
    assert (output_dir / "figures" / "fig-1.png").read_bytes() == b"figure-bytes"
    assert (output_dir / "layout_view_0.jpg").read_bytes() == b"layout-bytes"
    assert (output_dir / "manifest.json").is_file()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["page_index_kind"] == "layout_result_index"
    assert manifest["pages"][0]["markdown_path"] == "/mnt/user-data/uploads/_preprocessed/paper/doc_0.md"


@pytest.mark.asyncio
async def test_preprocess_image_with_vlm_provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    preprocessor = UploadPreprocessor(
        vlm_settings=ImageVLMSettings(
            enabled=True,
            api_url="https://example.test/v1/chat/completions",
            token="token",
            model="test-vlm",
        )
    )

    async def _mock_post(*, url, json, headers):
        class MockResponse:
            def raise_for_status(self): ...
            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "这是一张包含文字截图的图片，主要内容是测试数据。"
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                }
        return MockResponse()

    monkeypatch.setattr(
        "httpx.AsyncClient.post",
        lambda self, url, json, headers: _mock_post(url=url, json=json, headers=headers),
    )
    async def _mock_aenter(self):
        return self
    async def _mock_aexit(self, *args):
        pass
    monkeypatch.setattr("httpx.AsyncClient.__aenter__", _mock_aenter)
    monkeypatch.setattr("httpx.AsyncClient.__aexit__", _mock_aexit)

    output_dir = tmp_path / "out"
    result = await preprocessor.preprocess_file(
        filename="screenshot.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\nfake-png-data",
        output_dir=output_dir,
        output_virtual_root="/mnt/user-data/uploads/_preprocessed/screenshot",
    )

    assert result.status == "succeeded"
    assert result.provider == "image_vlm"
    assert result.file_type == "image"
    assert result.markdown_paths == (
        "/mnt/user-data/uploads/_preprocessed/screenshot/description.md",
    )
    assert (output_dir / "description.md").read_text(encoding="utf-8") == "这是一张包含文字截图的图片，主要内容是测试数据。"
    assert (output_dir / "manifest.json").is_file()


@pytest.mark.asyncio
async def test_preprocess_returns_failed_when_remote_call_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    preprocessor = UploadPreprocessor(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    call_mock = AsyncMock(side_effect=RuntimeError("remote failed"))
    monkeypatch.setattr(preprocessor._ocr_provider, "_call_layout_parsing", call_mock)

    result = await preprocessor.preprocess_file(
        filename="paper.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 test",
        output_dir=tmp_path / "out",
    )

    assert result.status == "failed"
    assert result.file_type == "pdf"
    assert "remote failed" in str(result.error)


@pytest.mark.asyncio
async def test_download_binary_rejects_non_http_scheme():
    provider = OCRProvider(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="Unsupported remote binary URL"):
            await provider._download_binary(client=client, url="file:///tmp/example.png")


@pytest.mark.asyncio
async def test_download_binary_rejects_oversized_content_length():
    provider = OCRProvider(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-length": str(upload_preprocessor_module._MAX_REMOTE_BINARY_BYTES + 1)
            },
            content=b"tiny",
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="too large"):
            await provider._download_binary(
                client=client,
                url="https://example.test/oversized.png",
            )


@pytest.mark.asyncio
async def test_download_binary_rejects_private_ip_host():
    provider = OCRProvider(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="Unsupported remote binary URL"):
            await provider._download_binary(client=client, url="http://127.0.0.1/internal.png")


@pytest.mark.asyncio
async def test_preprocess_rejects_too_many_layout_results(tmp_path, monkeypatch: pytest.MonkeyPatch):
    preprocessor = UploadPreprocessor(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    monkeypatch.setattr(
        preprocessor._ocr_provider,
        "_call_layout_parsing",
        AsyncMock(return_value=([{}] * (upload_preprocessor_module._MAX_LAYOUT_RESULTS + 1), None)),
    )

    result = await preprocessor.preprocess_file(
        filename="paper.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 test",
        output_dir=tmp_path / "out",
    )

    assert result.status == "failed"
    assert result.file_type == "pdf"
    assert "too many result segments" in str(result.error)


@pytest.mark.asyncio
async def test_ocr_provider_decodes_data_url_image(tmp_path, monkeypatch: pytest.MonkeyPatch):
    provider = OCRProvider(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    img_bytes = b"decoded-image-bytes"
    b64_img = base64.b64encode(img_bytes).decode("ascii")
    call_mock = AsyncMock(
        return_value=(
            [
                {
                    "markdown": {
                        "text": "# Doc",
                        "images": {
                            "fig1.jpg": f"data:image/jpeg;base64,{b64_img}",
                        },
                    },
                }
            ],
            None,
        )
    )
    monkeypatch.setattr(provider, "_call_layout_parsing", call_mock)

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = await provider.process(
        file_bytes=b"%PDF-1.4",
        filename="paper.pdf",
        content_type="application/pdf",
        output_dir=out_dir,
        output_virtual_root="/mnt/test",
    )

    assert result.status == "succeeded"
    assert result.markdown_image_paths
    assert (tmp_path / "out" / "fig1.jpg").read_bytes() == img_bytes


@pytest.mark.asyncio
async def test_vlm_provider_returns_failed_on_empty_response(tmp_path, monkeypatch: pytest.MonkeyPatch):
    provider = VLMProvider(
        ImageVLMSettings(
            enabled=True,
            api_url="https://example.test/v1/chat/completions",
            token="token",
        )
    )

    async def _mock_post(*, url, json, headers):
        class MockResponse:
            def raise_for_status(self): ...
            def json(self):
                return {
                    "choices": [{"message": {"content": ""}}],
                }
        return MockResponse()

    monkeypatch.setattr(
        "httpx.AsyncClient.post",
        lambda self, url, json, headers: _mock_post(url=url, json=json, headers=headers),
    )
    async def _mock_aenter(self):
        return self
    async def _mock_aexit(self, *args):
        pass
    monkeypatch.setattr("httpx.AsyncClient.__aenter__", _mock_aenter)
    monkeypatch.setattr("httpx.AsyncClient.__aexit__", _mock_aexit)

    with pytest.raises(ValueError, match="empty description"):
        await provider.process(
            file_bytes=b"\x89PNG\r\n\x1a\n",
            filename="test.png",
            content_type="image/png",
            output_dir=tmp_path / "out",
            output_virtual_root=None,
        )

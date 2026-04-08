"""Tests for upload preprocessor service."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.config import LayoutParsingSettings
from src.services.upload_preprocessor import UploadPreprocessor


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
async def test_preprocess_writes_markdown_and_images(tmp_path, monkeypatch: pytest.MonkeyPatch):
    preprocessor = UploadPreprocessor(
        LayoutParsingSettings(
            enabled=True,
            api_url="https://example.test/layout-parsing",
            token="token",
        )
    )
    call_mock = AsyncMock(
        return_value=[
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
        ]
    )
    download_mock = AsyncMock(side_effect=[b"figure-bytes", b"layout-bytes"])
    monkeypatch.setattr(preprocessor, "_call_layout_parsing", call_mock)
    monkeypatch.setattr(preprocessor, "_download_binary", download_mock)

    output_dir = tmp_path / "out"
    result = await preprocessor.preprocess_file(
        filename="paper.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 test",
        output_dir=output_dir,
        output_virtual_root="/mnt/user-data/uploads/_preprocessed/paper",
    )

    assert result.status == "succeeded"
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
    monkeypatch.setattr(preprocessor, "_call_layout_parsing", call_mock)

    result = await preprocessor.preprocess_file(
        filename="paper.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 test",
        output_dir=tmp_path / "out",
    )

    assert result.status == "failed"
    assert result.file_type == "pdf"
    assert "remote failed" in str(result.error)

"""Tests for document preprocess task handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.upload_preprocessor import UploadPreprocessResult
from src.task.handlers import document_preprocess_handler as handler


@pytest.mark.asyncio
async def test_execute_document_preprocess_runs_preprocessor_and_adds_urls(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "workspace_uploads" / "ws-1" / "context" / "background.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 large")
    output_dir = source.parent / "_preprocessed" / "background"
    preprocessor = SimpleNamespace(
        preprocess_file=AsyncMock(
            return_value=UploadPreprocessResult(
                status="succeeded",
                provider="layout_parsing",
                file_type="pdf",
                markdown_paths=("/context/_preprocessed/background/doc_0.md",),
                manifest_path="/context/_preprocessed/background/manifest.json",
            )
        )
    )
    progress = SimpleNamespace(update=AsyncMock())

    monkeypatch.setattr(
        handler,
        "get_upload_preprocessor_service",
        lambda: preprocessor,
    )

    result = await handler.execute_document_preprocess(
        {
            "workspace_id": "ws-1",
            "thread_id": "thread-1",
            "filename": "background.pdf",
            "content_type": "application/pdf",
            "source_path": str(source),
            "output_dir": str(output_dir),
            "output_virtual_root": "context/_preprocessed/background",
            "workspace_upload_root": str(tmp_path / "workspace_uploads"),
            "attachment": {
                "name": "background.pdf",
                "reference_id": "reference-1",
            },
        },
        progress,
    )

    assert result["success"] is True
    preprocess = result["preprocess"]
    assert preprocess["status"] == "succeeded"
    assert preprocess["markdown_urls"] == ["/api/workspaces/ws-1/files/context/_preprocessed/background/doc_0.md"]
    assert preprocess["manifest_url"] == ("/api/workspaces/ws-1/files/context/_preprocessed/background/manifest.json")
    preprocessor.preprocess_file.assert_awaited_once()
    call_kwargs = preprocessor.preprocess_file.await_args.kwargs
    assert call_kwargs["source_path"] == source
    assert call_kwargs["output_dir"] == output_dir
    assert call_kwargs["output_virtual_root"] == "context/_preprocessed/background"
    assert progress.update.await_count == 3
    assert result["refresh_targets"] == ["dashboard", "references"]


@pytest.mark.asyncio
async def test_execute_document_preprocess_refreshes_artifacts_for_workspace_context(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "workspace_uploads" / "ws-1" / "context" / "notes.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 large")
    output_dir = source.parent / "_preprocessed" / "notes"
    preprocessor = SimpleNamespace(
        preprocess_file=AsyncMock(
            return_value=UploadPreprocessResult(
                status="succeeded",
                provider="layout_parsing",
                file_type="pdf",
                markdown_paths=("context/_preprocessed/notes/doc_0.md",),
            )
        )
    )
    progress = SimpleNamespace(update=AsyncMock())
    monkeypatch.setattr(
        handler,
        "get_upload_preprocessor_service",
        lambda: preprocessor,
    )

    result = await handler.execute_document_preprocess(
        {
            "workspace_id": "ws-1",
            "thread_id": "thread-1",
            "filename": "notes.pdf",
            "content_type": "application/pdf",
            "source_path": str(source),
            "output_dir": str(output_dir),
            "output_virtual_root": "context/_preprocessed/notes",
            "workspace_upload_root": str(tmp_path / "workspace_uploads"),
            "attachment": {
                "name": "notes.pdf",
                "artifact_id": "artifact-1",
            },
        },
        progress,
    )

    assert result["refresh_targets"] == ["dashboard", "artifacts"]


@pytest.mark.asyncio
async def test_execute_document_preprocess_raises_when_provider_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4 large")
    preprocessor = SimpleNamespace(
        preprocess_file=AsyncMock(
            return_value=UploadPreprocessResult(
                status="failed",
                provider="layout_parsing",
                file_type="pdf",
                error="layout timeout",
            )
        )
    )
    progress = SimpleNamespace(update=AsyncMock())

    monkeypatch.setattr(
        handler,
        "get_upload_preprocessor_service",
        lambda: preprocessor,
    )

    with pytest.raises(ValueError, match="layout timeout"):
        await handler.execute_document_preprocess(
            {
                "filename": "paper.pdf",
                "source_path": str(source),
                "output_dir": str(tmp_path / "out"),
            },
            progress,
        )

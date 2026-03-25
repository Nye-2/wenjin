"""Tests for PapersHandler upload orchestration."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import Headers, UploadFile

from src.application.handlers.papers_handler import PapersHandler


def _make_upload_file(
    filename: str,
    content: bytes,
    content_type: str | None,
) -> UploadFile:
    headers = Headers({"content-type": content_type}) if content_type else Headers()
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=headers,
    )


@pytest.fixture
def handler():
    paper_service = MagicMock()
    paper_service.create_in_workspace = AsyncMock(
        return_value=SimpleNamespace(id="paper-1")
    )
    workspace_service = MagicMock()
    workspace_service.get = AsyncMock(
        return_value=SimpleNamespace(id="ws-1", user_id="user-1")
    )
    task_service = MagicMock()
    return (
        PapersHandler(
            paper_service=paper_service,
            workspace_service=workspace_service,
            task_service=task_service,
        ),
        paper_service,
    )


@pytest.mark.asyncio
async def test_upload_paper_persists_pdf_and_records_file_path(tmp_path, handler):
    papers_handler, paper_service = handler
    upload = _make_upload_file("paper.pdf", b"%PDF-1.4 body", "application/pdf")

    with patch(
        "src.application.handlers.papers_handler._PERSISTED_UPLOAD_ROOT",
        tmp_path / "workspace_uploads",
    ), patch(
        "src.application.handlers.papers_handler.extract_document_preview",
        return_value={
            "title": "Detected Title",
            "authors": ["Ada Lovelace", "Alan Turing"],
            "page_count": 12,
            "text_preview": "Detected preview",
        },
    ):
        response = await papers_handler.upload_paper(
            workspace_id="ws-1",
            user_id="user-1",
            file=upload,
        )

    stored_path = tmp_path / "workspace_uploads" / "ws-1" / "papers" / "paper.pdf"
    assert stored_path.read_bytes() == b"%PDF-1.4 body"
    kwargs = paper_service.create_in_workspace.await_args.kwargs
    assert kwargs["workspace_id"] == "ws-1"
    assert kwargs["source"] == "manual_upload"
    assert kwargs["title"] == "Detected Title"
    assert kwargs["authors"] == [
        {"name": "Ada Lovelace"},
        {"name": "Alan Turing"},
    ]
    assert kwargs["file_path"] == str(stored_path)
    assert response["paper_id"] == "paper-1"
    assert response["filename"] == "paper.pdf"
    assert response["original_filename"] == "paper.pdf"
    assert response["file_path"] == str(stored_path)
    assert response["file_url"] == "/api/workspaces/ws-1/files/papers/paper.pdf"
    assert response["source"] == "manual_upload"


@pytest.mark.asyncio
async def test_upload_paper_accepts_pdf_by_extension_without_content_type(tmp_path, handler):
    papers_handler, paper_service = handler
    upload = _make_upload_file("extension-only.pdf", b"%PDF-1.4 body", None)

    with patch(
        "src.application.handlers.papers_handler._PERSISTED_UPLOAD_ROOT",
        tmp_path / "workspace_uploads",
    ), patch(
        "src.application.handlers.papers_handler.extract_document_preview",
        return_value={
            "title": None,
            "authors": [],
            "page_count": None,
            "text_preview": None,
        },
    ):
        response = await papers_handler.upload_paper(
            workspace_id="ws-1",
            user_id="user-1",
            file=upload,
        )

    kwargs = paper_service.create_in_workspace.await_args.kwargs
    assert kwargs["file_path"].endswith("workspace_uploads/ws-1/papers/extension-only.pdf")
    assert response["filename"] == "extension-only.pdf"
    assert response["file_url"] == "/api/workspaces/ws-1/files/papers/extension-only.pdf"


@pytest.mark.asyncio
async def test_upload_paper_renames_duplicates_before_persisting(tmp_path, handler):
    papers_handler, paper_service = handler
    target_dir = tmp_path / "workspace_uploads" / "ws-1" / "papers"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "paper.pdf").write_bytes(b"old")
    upload = _make_upload_file("paper.pdf", b"%PDF-1.4 new body", "application/pdf")

    with patch(
        "src.application.handlers.papers_handler._PERSISTED_UPLOAD_ROOT",
        tmp_path / "workspace_uploads",
    ), patch(
        "src.application.handlers.papers_handler.extract_document_preview",
        return_value={
            "title": None,
            "authors": [],
            "page_count": None,
            "text_preview": None,
        },
    ):
        response = await papers_handler.upload_paper(
            workspace_id="ws-1",
            user_id="user-1",
            file=upload,
        )

    stored_path = target_dir / "paper-2.pdf"
    kwargs = paper_service.create_in_workspace.await_args.kwargs
    assert stored_path.read_bytes() == b"%PDF-1.4 new body"
    assert kwargs["file_path"] == str(stored_path)
    assert response["filename"] == "paper-2.pdf"
    assert response["file_url"] == "/api/workspaces/ws-1/files/papers/paper-2.pdf"

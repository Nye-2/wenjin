"""Tests for PapersHandler upload orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.handlers.papers_handler import PapersHandler, UploadedPaperPayload


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
    task_service.find_active_task_by_payload = AsyncMock(return_value=None)
    task_service.submit_task = AsyncMock(return_value="task-paper-extract-1")
    return (
        PapersHandler(
            paper_service=paper_service,
            workspace_service=workspace_service,
            task_service=task_service,
        ),
        paper_service,
        task_service,
    )


@pytest.mark.asyncio
async def test_upload_paper_persists_pdf_and_records_file_path(tmp_path, handler):
    papers_handler, paper_service, task_service = handler
    upload = UploadedPaperPayload(
        filename="paper.pdf",
        content=b"%PDF-1.4 body",
        content_type="application/pdf",
    )

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
            upload=upload,
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
    assert response["extraction"]["task_id"] == "task-paper-extract-1"
    assert response["extraction"]["status"] == "scheduled"
    task_service.submit_task.assert_awaited_once_with(
        user_id="user-1",
        task_type="paper_extraction",
        payload={
            "workspace_id": "ws-1",
            "paper_id": "paper-1",
            "tier": 1,
        },
    )


@pytest.mark.asyncio
async def test_upload_paper_accepts_pdf_by_extension_without_content_type(tmp_path, handler):
    papers_handler, paper_service, _task_service = handler
    upload = UploadedPaperPayload(
        filename="extension-only.pdf",
        content=b"%PDF-1.4 body",
        content_type=None,
    )

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
            upload=upload,
        )

    kwargs = paper_service.create_in_workspace.await_args.kwargs
    assert kwargs["file_path"].endswith("workspace_uploads/ws-1/papers/extension-only.pdf")
    assert response["filename"] == "extension-only.pdf"
    assert response["file_url"] == "/api/workspaces/ws-1/files/papers/extension-only.pdf"


@pytest.mark.asyncio
async def test_upload_paper_renames_duplicates_before_persisting(tmp_path, handler):
    papers_handler, paper_service, _task_service = handler
    target_dir = tmp_path / "workspace_uploads" / "ws-1" / "papers"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "paper.pdf").write_bytes(b"old")
    upload = UploadedPaperPayload(
        filename="paper.pdf",
        content=b"%PDF-1.4 new body",
        content_type="application/pdf",
    )

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
            upload=upload,
        )

    stored_path = target_dir / "paper-2.pdf"
    kwargs = paper_service.create_in_workspace.await_args.kwargs
    assert stored_path.read_bytes() == b"%PDF-1.4 new body"
    assert kwargs["file_path"] == str(stored_path)
    assert response["filename"] == "paper-2.pdf"
    assert response["file_url"] == "/api/workspaces/ws-1/files/papers/paper-2.pdf"


@pytest.mark.asyncio
async def test_upload_paper_keeps_success_when_extraction_scheduling_fails(tmp_path, handler):
    papers_handler, _paper_service, task_service = handler
    task_service.submit_task = AsyncMock(side_effect=RuntimeError("queue offline"))
    upload = UploadedPaperPayload(
        filename="paper.pdf",
        content=b"%PDF-1.4 body",
        content_type="application/pdf",
    )

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
            upload=upload,
        )

    assert response["success"] is True
    assert response["extraction"]["status"] == "failed"
    assert "queue offline" in response["extraction"]["message"]

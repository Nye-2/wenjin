"""Tests for canonical /papers/upload endpoint."""

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.errors import BadRequestError
from src.application.handlers.papers_handler import UploadedPaperPayload
from src.gateway.routers.papers import get_papers_handler, router
from src.gateway.routers.auth import get_current_user


def _create_mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = "test-user-001"
    user.email = "test@test.com"
    user.is_active = True
    return user


@pytest.fixture
def app():
    """Create FastAPI app with academic router."""
    app = FastAPI()
    app.include_router(router, prefix="/api")

    mock_handler = AsyncMock()

    async def upload_paper(*, workspace_id: str, user_id: str, upload: UploadedPaperPayload):
        if upload.content_type not in ("application/pdf", "application/x-pdf"):
            raise BadRequestError("Only PDF files are accepted")
        content = upload.content
        if not content:
            raise BadRequestError("Uploaded file is empty")
        return {
            "success": True,
            "paper_id": "p-123",
            "filename": upload.filename,
            "content_type": upload.content_type,
            "size_bytes": len(content),
            "workspace_id": workspace_id,
            "file_url": f"/api/workspaces/{workspace_id}/files/papers/{upload.filename}",
            "extraction": {
                "task_id": "task-paper-extract-1",
                "status": "scheduled",
                "paper_id": "p-123",
                "workspace_id": workspace_id,
                "tier": 1,
                "message": "论文提取任务已提交",
                "reused_existing_task": False,
            },
        }

    mock_handler.upload_paper = AsyncMock(side_effect=upload_paper)

    async def mock_get_current_user():
        return _create_mock_user()

    async def mock_handler_dep():
        return mock_handler

    app.state.mock_handler = mock_handler
    app.dependency_overrides[get_papers_handler] = mock_handler_dep
    app.dependency_overrides[get_current_user] = mock_get_current_user
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestUploadPaperEndpoint:
    def test_upload_returns_structured_response(self, client):
        """Upload should return structured response with paper_id and metadata."""
        pdf_bytes = b"%PDF-1.4 fake content"
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"workspace_id": "ws-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["filename"] == "test.pdf"
        assert "paper_id" in body
        assert "size_bytes" in body
        assert body["file_url"] == "/api/workspaces/ws-1/files/papers/test.pdf"
        assert body["extraction"]["status"] == "scheduled"
        client.app.state.mock_handler.upload_paper.assert_awaited_once()

    def test_upload_rejects_non_pdf(self, client):
        """Upload should reject non-PDF files."""
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("image.png", io.BytesIO(b"\x89PNG"), "image/png")},
            data={"workspace_id": "ws-1"},
        )
        assert resp.status_code == 400

    def test_upload_rejects_empty_file(self, client):
        """Upload should reject empty files."""
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            data={"workspace_id": "ws-1"},
        )
        assert resp.status_code == 400

    def test_upload_without_workspace_id_fails(self, client):
        """Upload should require a workspace target."""
        pdf_bytes = b"%PDF-1.4 fake content"
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("paper.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert resp.status_code == 422

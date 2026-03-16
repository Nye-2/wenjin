"""Tests for /papers/upload endpoint in academic router."""

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.gateway.routers.academic import router, get_paper_service, get_db


@pytest.fixture
def app():
    """Create FastAPI app with academic router."""
    app = FastAPI()
    app.include_router(router, prefix="/api")

    # Override deps
    async def mock_db():
        yield object()

    mock_svc = AsyncMock()
    mock_svc.create = AsyncMock(return_value=type(
        "Paper",
        (),
        {
            "__table__": type("T", (), {"columns": []})(),
            "id": "p-123",
            "doi": None,
            "title": "test.pdf",
            "authors": [],
            "year": None,
            "venue": None,
            "abstract": None,
            "source": "upload",
            "citation_count": None,
            "reference_count": None,
        },
    )())

    async def mock_paper_service(db=None):
        return mock_svc

    app.dependency_overrides[get_db] = mock_db
    app.dependency_overrides[get_paper_service] = mock_paper_service
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

    def test_upload_rejects_non_pdf(self, client):
        """Upload should reject non-PDF files."""
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("image.png", io.BytesIO(b"\x89PNG"), "image/png")},
        )
        assert resp.status_code == 400

    def test_upload_rejects_empty_file(self, client):
        """Upload should reject empty files."""
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_upload_without_workspace_id_still_succeeds(self, client):
        """Upload without workspace_id should still save the paper."""
        pdf_bytes = b"%PDF-1.4 fake content"
        resp = client.post(
            "/api/papers/upload",
            files={"file": ("paper.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

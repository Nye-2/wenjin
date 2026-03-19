"""Tests for /papers/upload endpoint in academic router."""

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers.academic import (
    get_paper_service,
    get_workspace_service,
    router,
)
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

    mock_svc = AsyncMock()
    mock_svc.create_in_workspace = AsyncMock(return_value=type(
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

    mock_workspace_service = AsyncMock()
    mock_workspace_service.get = AsyncMock(return_value=type(
        "Workspace",
        (),
        {
            "id": "ws-1",
            "user_id": "test-user-001",
        },
    )())

    async def mock_paper_service(db=None):
        return mock_svc

    async def mock_workspace_service_dep():
        return mock_workspace_service

    async def mock_get_current_user():
        return _create_mock_user()

    app.state.mock_paper_service = mock_svc
    app.state.mock_workspace_service = mock_workspace_service
    app.dependency_overrides[get_paper_service] = mock_paper_service
    app.dependency_overrides[get_workspace_service] = mock_workspace_service_dep
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
        client.app.state.mock_paper_service.create_in_workspace.assert_awaited_once_with(
            workspace_id="ws-1",
            title="test",
            authors=[],
            source="upload",
        )

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

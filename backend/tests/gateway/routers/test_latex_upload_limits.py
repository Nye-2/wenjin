"""Upload size-limit tests for LaTeX project router."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.latex import router


class _FakeLatexProjectService:
    save_uploads_calls = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def get_owned(self, project_id: str, user_id: str):
        if project_id == "missing" or user_id != "user-1":
            return None
        return SimpleNamespace(id=project_id)

    async def save_uploads(self, project, *, files, folders=None):
        type(self).save_uploads_calls += 1
        return [path for path, _ in files], list(folders or [])


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def _get_current_user():
        return SimpleNamespace(id="user-1")

    async def _get_dataservice_client():
        return AsyncMock()

    app.dependency_overrides[get_current_user] = _get_current_user
    app.dependency_overrides[get_dataservice_client] = _get_dataservice_client
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_latex_upload_rejects_too_many_files(client):
    _FakeLatexProjectService.save_uploads_calls = 0
    with (
        patch("src.gateway.routers.latex_upload.LatexProjectService", _FakeLatexProjectService),
        patch(
            "src.gateway.routers.latex_upload._MAX_UPLOAD_FILES",
            2,
        ),
    ):
        response = client.post(
            "/api/prism/latex-adapter/projects/proj-1/upload",
            files=[
                ("files", ("a.tex", io.BytesIO(b"a"), "text/plain")),
                ("files", ("b.tex", io.BytesIO(b"b"), "text/plain")),
                ("files", ("c.tex", io.BytesIO(b"c"), "text/plain")),
            ],
        )

    assert response.status_code == 413
    assert "Too many files" in response.json()["detail"]
    assert _FakeLatexProjectService.save_uploads_calls == 0


def test_latex_upload_rejects_oversized_total_batch(client):
    _FakeLatexProjectService.save_uploads_calls = 0
    with (
        patch("src.gateway.routers.latex_upload.LatexProjectService", _FakeLatexProjectService),
        patch(
            "src.gateway.routers.latex_upload._MAX_UPLOAD_FILE_BYTES",
            16,
        ),
        patch(
            "src.gateway.routers.latex_upload._MAX_UPLOAD_TOTAL_BYTES",
            8,
        ),
    ):
        response = client.post(
            "/api/prism/latex-adapter/projects/proj-1/upload",
            files=[
                ("files", ("a.tex", io.BytesIO(b"12345"), "text/plain")),
                ("files", ("b.tex", io.BytesIO(b"6789"), "text/plain")),
            ],
        )

    assert response.status_code == 413
    assert "Upload batch too large" in response.json()["detail"]
    assert _FakeLatexProjectService.save_uploads_calls == 0


def test_latex_upload_rejects_single_file_over_limit(client):
    _FakeLatexProjectService.save_uploads_calls = 0
    with (
        patch("src.gateway.routers.latex_upload.LatexProjectService", _FakeLatexProjectService),
        patch(
            "src.gateway.routers.latex_upload._MAX_UPLOAD_FILE_BYTES",
            4,
        ),
    ):
        response = client.post(
            "/api/prism/latex-adapter/projects/proj-1/upload",
            files=[
                ("files", ("a.tex", io.BytesIO(b"12345"), "text/plain")),
            ],
        )

    assert response.status_code == 413
    assert "Uploaded file too large" in response.json()["detail"]
    assert _FakeLatexProjectService.save_uploads_calls == 0

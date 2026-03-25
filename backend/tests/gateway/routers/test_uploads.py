"""Tests for thread-scoped chat uploads."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import (
    get_artifact_service,
    get_chat_thread_service,
    get_db,
    get_paper_service,
    get_workspace_service,
)
from src.gateway.routers.uploads import router


def _mock_user():
    user = MagicMock()
    user.id = "user-1"
    return user


@pytest.fixture
def app(tmp_path):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    thread = SimpleNamespace(id="thread-1", user_id="user-1", workspace_id="ws-1")
    workspace = SimpleNamespace(id="ws-1", user_id="user-1")
    chat_thread_service = MagicMock()
    chat_thread_service.get_thread = AsyncMock(return_value=thread)
    workspace_service = MagicMock()
    workspace_service.get = AsyncMock(return_value=workspace)
    paper_service = MagicMock()
    paper_service.create_in_workspace = AsyncMock(
        return_value=SimpleNamespace(id="paper-1")
    )
    artifact_service = MagicMock()
    artifact_service.create = AsyncMock(return_value=SimpleNamespace(id="artifact-1"))
    db = AsyncMock()

    async def _get_current_user():
        return _mock_user()

    async def _get_chat_thread_service():
        return chat_thread_service

    async def _get_workspace_service():
        return workspace_service

    async def _get_paper_service():
        return paper_service

    async def _get_artifact_service():
        return artifact_service

    async def _get_db():
        yield db

    app.dependency_overrides[get_current_user] = _get_current_user
    app.dependency_overrides[get_chat_thread_service] = _get_chat_thread_service
    app.dependency_overrides[get_workspace_service] = _get_workspace_service
    app.dependency_overrides[get_paper_service] = _get_paper_service
    app.dependency_overrides[get_artifact_service] = _get_artifact_service
    app.dependency_overrides[get_db] = _get_db

    app.state.chat_thread_service = chat_thread_service
    app.state.workspace_service = workspace_service
    app.state.paper_service = paper_service
    app.state.artifact_service = artifact_service
    app.state.db = db
    app.state.temp_root = tmp_path
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _patch_storage_roots(app):
    temp_root = app.state.temp_root
    return patch.multiple(
        "src.gateway.routers.uploads",
        _PERSISTED_UPLOAD_ROOT=temp_root / "workspace_uploads",
        get_thread_data_root=lambda thread_id: temp_root / "threads" / thread_id / "user-data",
    )


def test_transient_upload_returns_attachment_metadata(client):
    with _patch_storage_roots(client.app):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "transient"},
            files=[("files", ("notes.txt", io.BytesIO(b"hello"), "text/plain"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["files"][0]["name"] == "notes.txt"
    assert body["files"][0]["kind"] == "transient"
    assert body["files"][0]["path"] == "/mnt/user-data/uploads/notes.txt"
    assert body["files"][0]["url"].endswith(
        "/api/threads/thread-1/artifacts/mnt/user-data/uploads/notes.txt"
    )
    assert client.app.state.paper_service.create_in_workspace.await_count == 0
    assert client.app.state.artifact_service.create.await_count == 0


def test_literature_upload_persists_pdf_to_paper_center(client):
    with _patch_storage_roots(client.app):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "literature", "workspace_id": "ws-1"},
            files=[("files", ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["paper_id"] == "paper-1"
    submit_kwargs = client.app.state.paper_service.create_in_workspace.await_args.kwargs
    assert submit_kwargs["workspace_id"] == "ws-1"
    assert submit_kwargs["source"] == "chat_upload"
    assert submit_kwargs["file_path"].endswith("workspace_uploads/ws-1/papers/paper.pdf")


def test_workspace_context_upload_creates_artifact_and_memory_note(client):
    mock_knowledge_service = MagicMock()
    mock_knowledge_service.upsert = AsyncMock()

    with _patch_storage_roots(client.app), patch(
        "src.gateway.routers.uploads.KnowledgeService",
        return_value=mock_knowledge_service,
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "workspace_context", "workspace_id": "ws-1"},
            files=[("files", ("proposal.md", io.BytesIO(b"# proposal"), "text/markdown"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["artifact_id"] == "artifact-1"
    client.app.state.artifact_service.create.assert_awaited_once()
    artifact_content = client.app.state.artifact_service.create.await_args.kwargs["content"]
    assert artifact_content["text_preview"] == "# proposal"
    mock_knowledge_service.upsert.assert_awaited_once()
    knowledge_args = mock_knowledge_service.upsert.await_args.args
    assert "内容摘要" in knowledge_args[2]
    assert "proposal" in knowledge_args[2]
    client.app.state.db.commit.assert_awaited()

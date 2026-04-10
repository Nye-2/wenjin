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
    get_task_service,
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
    task_service = MagicMock()
    task_service.find_active_task_by_payload = AsyncMock(return_value=None)
    task_service.submit_task = AsyncMock(return_value="task-paper-extract-1")
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

    async def _get_task_service():
        yield task_service

    app.dependency_overrides[get_current_user] = _get_current_user
    app.dependency_overrides[get_chat_thread_service] = _get_chat_thread_service
    app.dependency_overrides[get_workspace_service] = _get_workspace_service
    app.dependency_overrides[get_paper_service] = _get_paper_service
    app.dependency_overrides[get_artifact_service] = _get_artifact_service
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_task_service] = _get_task_service

    app.state.chat_thread_service = chat_thread_service
    app.state.workspace_service = workspace_service
    app.state.paper_service = paper_service
    app.state.artifact_service = artifact_service
    app.state.task_service = task_service
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
    with _patch_storage_roots(client.app), patch(
        "src.gateway.routers.uploads.publish_workspace_event",
        AsyncMock(),
    ) as publish_workspace_event, patch(
        "src.gateway.routers.uploads.extract_document_preview",
        return_value={
            "title": "Transformer Paper",
            "authors": ["Ashish Vaswani", "Noam Shazeer"],
            "page_count": 15,
            "text_preview": "Attention is all you need.",
        },
    ):
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
    assert submit_kwargs["title"] == "Transformer Paper"
    assert submit_kwargs["authors"] == [
        {"name": "Ashish Vaswani"},
        {"name": "Noam Shazeer"},
    ]
    assert submit_kwargs["file_path"].endswith("workspace_uploads/ws-1/papers/paper.pdf")
    assert body["files"][0]["metadata"]["stored_url"] == "/api/workspaces/ws-1/files/papers/paper.pdf"
    assert body["files"][0]["metadata"]["document_title"] == "Transformer Paper"
    assert body["files"][0]["metadata"]["document_authors"] == [
        "Ashish Vaswani",
        "Noam Shazeer",
    ]
    assert body["files"][0]["metadata"]["page_count"] == 15
    assert body["files"][0]["metadata"]["text_preview"] == "Attention is all you need."
    assert body["files"][0]["metadata"]["extraction"]["task_id"] == "task-paper-extract-1"
    assert body["files"][0]["metadata"]["extraction"]["status"] == "scheduled"
    client.app.state.task_service.submit_task.assert_awaited_once_with(
        user_id="user-1",
        task_type="paper_extraction",
        payload={
            "workspace_id": "ws-1",
            "paper_id": "paper-1",
            "tier": 1,
            "thread_id": "thread-1",
        },
    )
    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "papers"]},
    )


def test_literature_upload_keeps_success_when_extraction_queue_fails(client):
    client.app.state.task_service.submit_task = AsyncMock(
        side_effect=RuntimeError("queue offline")
    )

    with _patch_storage_roots(client.app), patch(
        "src.gateway.routers.uploads.extract_document_preview",
        return_value={
            "title": "Transformer Paper",
            "authors": ["Ashish Vaswani"],
            "page_count": 15,
            "text_preview": "Attention is all you need.",
        },
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "literature", "workspace_id": "ws-1"},
            files=[("files", ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["metadata"]["extraction"]["status"] == "failed"
    assert "queue offline" in body["files"][0]["metadata"]["extraction"]["message"]


def test_workspace_context_upload_creates_artifact_and_memory_note(client):
    mock_knowledge_service = MagicMock()
    mock_knowledge_service.upsert = AsyncMock()

    with _patch_storage_roots(client.app), patch(
        "src.gateway.routers.uploads.publish_workspace_event",
        AsyncMock(),
    ) as publish_workspace_event, patch(
        "src.gateway.routers.uploads.KnowledgeService",
        return_value=mock_knowledge_service,
    ), patch(
        "src.gateway.routers.uploads.extract_document_preview",
        return_value={
            "title": "Opening Proposal",
            "authors": [],
            "page_count": None,
            "text_preview": "# proposal",
        },
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "workspace_context", "workspace_id": "ws-1"},
            files=[("files", ("proposal.md", io.BytesIO(b"# proposal"), "text/markdown"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["artifact_id"] == "artifact-1"
    assert body["files"][0]["metadata"]["stored_url"] == "/api/workspaces/ws-1/files/context/proposal.md"
    client.app.state.artifact_service.create.assert_awaited_once()
    assert "created_by_skill" not in client.app.state.artifact_service.create.await_args.kwargs
    artifact_content = client.app.state.artifact_service.create.await_args.kwargs["content"]
    assert artifact_content["text_preview"] == "# proposal"
    assert artifact_content["stored_url"] == "/api/workspaces/ws-1/files/context/proposal.md"
    assert artifact_content["document_title"] == "Opening Proposal"
    mock_knowledge_service.upsert.assert_awaited_once()
    knowledge_args = mock_knowledge_service.upsert.await_args.args
    assert "Opening Proposal" in knowledge_args[2]
    assert "内容摘要" in knowledge_args[2]
    assert "proposal" in knowledge_args[2]
    client.app.state.db.commit.assert_awaited()
    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "artifacts"]},
    )


def test_workspace_context_upload_degrades_when_memory_write_fails(client):
    mock_knowledge_service = MagicMock()
    mock_knowledge_service.upsert = AsyncMock(side_effect=RuntimeError("memory offline"))

    with _patch_storage_roots(client.app), patch(
        "src.gateway.routers.uploads.publish_workspace_event",
        AsyncMock(),
    ) as publish_workspace_event, patch(
        "src.gateway.routers.uploads.KnowledgeService",
        return_value=mock_knowledge_service,
    ), patch(
        "src.gateway.routers.uploads.extract_document_preview",
        return_value={
            "title": "Opening Proposal",
            "authors": [],
            "page_count": None,
            "text_preview": "# proposal",
        },
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
    assert "created_by_skill" not in client.app.state.artifact_service.create.await_args.kwargs
    client.app.state.db.rollback.assert_awaited_once()
    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "artifacts"]},
    )

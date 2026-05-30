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
    get_task_service,
    get_thread_service,
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
    thread_service = MagicMock()
    thread_service.get_thread = AsyncMock(return_value=thread)
    workspace_service = MagicMock()
    workspace_service.get = AsyncMock(return_value=workspace)
    workspace_service.has_active_membership = AsyncMock(return_value=True)
    artifact_service = MagicMock()
    artifact_service.create = AsyncMock(return_value=SimpleNamespace(id="artifact-1"))
    task_service = MagicMock()
    task_service.find_active_task_by_payload = AsyncMock(return_value=None)
    task_service.submit_task = AsyncMock(return_value="task-reference-preprocess-1")

    async def _get_current_user():
        return _mock_user()

    async def _get_thread_service():
        return thread_service

    async def _get_workspace_service():
        return workspace_service

    async def _get_artifact_service():
        return artifact_service

    async def _get_task_service():
        yield task_service

    app.dependency_overrides[get_current_user] = _get_current_user
    app.dependency_overrides[get_thread_service] = _get_thread_service
    app.dependency_overrides[get_workspace_service] = _get_workspace_service
    app.dependency_overrides[get_artifact_service] = _get_artifact_service
    app.dependency_overrides[get_task_service] = _get_task_service

    app.state.thread_service = thread_service
    app.state.workspace_service = workspace_service
    app.state.artifact_service = artifact_service
    app.state.task_service = task_service
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
    assert body["files"][0]["url"].endswith("/api/threads/thread-1/artifacts/mnt/user-data/uploads/notes.txt")
    assert client.app.state.artifact_service.create.await_count == 0
    assert client.app.state.task_service.submit_task.await_count == 0


def test_upload_rejects_oversized_file(client):
    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads._MAX_UPLOAD_SIZE_BYTES",
            8,
        ),
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "transient"},
            files=[("files", ("notes.txt", io.BytesIO(b"123456789"), "text/plain"))],
        )

    assert response.status_code == 413
    client.app.state.artifact_service.create.assert_not_awaited()


def test_upload_rejects_too_many_files(client):
    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads._MAX_UPLOAD_FILES",
            1,
        ),
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "transient"},
            files=[
                ("files", ("a.txt", io.BytesIO(b"a"), "text/plain")),
                ("files", ("b.txt", io.BytesIO(b"b"), "text/plain")),
            ],
        )

    assert response.status_code == 413
    assert "Too many files" in response.json()["detail"]
    client.app.state.artifact_service.create.assert_not_awaited()


def test_literature_upload_persists_pdf_to_reference_library(client):
    import_uploaded_pdf = AsyncMock(
        return_value={
            "success": True,
            "reference": {
                "id": "reference-1",
                "title": "Transformer Paper",
                "authors": ["Ashish Vaswani", "Noam Shazeer"],
            },
            "asset": {
                "id": "asset-1",
                "file_path": "references/paper.pdf",
                "public_url": "/api/workspaces/ws-1/files/references/paper.pdf",
                "page_count": 15,
            },
            "preprocess": {
                "status": "scheduled",
                "task_id": "task-reference-preprocess-1",
                "message": "Reference Library 后台解析队列",
            },
        }
    )

    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads.publish_workspace_event",
            AsyncMock(),
        ) as publish_workspace_event,
        patch(
            "src.gateway.routers.uploads.SourceLibraryImportService",
            return_value=SimpleNamespace(import_uploaded_pdf=import_uploaded_pdf),
        ),
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "literature", "workspace_id": "ws-1"},
            files=[("files", ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["reference_id"] == "reference-1"
    assert body["files"][0]["path"] == "reference://reference-1"
    assert body["files"][0]["url"] == "/api/workspaces/ws-1/files/references/paper.pdf"
    submit_kwargs = import_uploaded_pdf.await_args.kwargs
    assert submit_kwargs["workspace_id"] == "ws-1"
    assert submit_kwargs["filename"] == "paper.pdf"
    assert submit_kwargs["content_type"] == "application/pdf"
    assert submit_kwargs["task_service"] is client.app.state.task_service
    assert submit_kwargs["user_id"] == "user-1"
    assert submit_kwargs["thread_id"] == "thread-1"
    assert not (
        client.app.state.temp_root / "threads" / "thread-1" / "user-data" / "uploads" / "paper.pdf"
    ).exists()
    assert body["files"][0]["metadata"]["reference_asset_id"] == "asset-1"
    assert body["files"][0]["metadata"]["stored_url"] == "/api/workspaces/ws-1/files/references/paper.pdf"
    assert body["files"][0]["metadata"]["document_title"] == "Transformer Paper"
    assert body["files"][0]["metadata"]["document_authors"] == [
        "Ashish Vaswani",
        "Noam Shazeer",
    ]
    assert body["files"][0]["metadata"]["page_count"] == 15
    assert body["files"][0]["metadata"]["preprocess"]["task_id"] == "task-reference-preprocess-1"
    assert body["files"][0]["metadata"]["preprocess"]["status"] == "scheduled"
    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "references"]},
    )


def test_literature_upload_preserves_reference_preprocess_metadata(client):
    import_uploaded_pdf = AsyncMock(
        return_value={
            "success": True,
            "reference": {"id": "reference-1", "title": "Transformer Paper", "authors": []},
            "asset": {
                "id": "asset-1",
                "file_path": "references/paper.pdf",
                "public_url": "/api/workspaces/ws-1/files/references/paper.pdf",
            },
            "preprocess": {
                "status": "succeeded",
                "markdown_paths": ["/references/_preprocessed/paper/doc_0.md"],
                "markdown_urls": ["/api/workspaces/ws-1/files/references/_preprocessed/paper/doc_0.md"],
                "manifest_url": "/api/workspaces/ws-1/files/references/_preprocessed/paper/manifest.json",
            },
        }
    )

    with (
        _patch_storage_roots(client.app),
        patch("src.gateway.routers.uploads.publish_workspace_event", AsyncMock()),
        patch(
            "src.gateway.routers.uploads.SourceLibraryImportService",
            return_value=SimpleNamespace(import_uploaded_pdf=import_uploaded_pdf),
        ),
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "literature", "workspace_id": "ws-1"},
            files=[("files", ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )

    assert response.status_code == 200
    body = response.json()
    preprocess = body["files"][0]["metadata"]["preprocess"]
    assert preprocess["markdown_paths"] == ["/references/_preprocessed/paper/doc_0.md"]
    assert preprocess["markdown_urls"] == ["/api/workspaces/ws-1/files/references/_preprocessed/paper/doc_0.md"]
    assert preprocess["manifest_url"] == "/api/workspaces/ws-1/files/references/_preprocessed/paper/manifest.json"


def test_large_literature_upload_returns_reference_preprocess_pending_state(client):
    import_uploaded_pdf = AsyncMock(
        return_value={
            "success": True,
            "reference": {"id": "reference-1", "title": "Transformer Paper", "authors": ["Ashish Vaswani"]},
            "asset": {
                "id": "asset-1",
                "file_path": "references/paper.pdf",
                "public_url": "/api/workspaces/ws-1/files/references/paper.pdf",
                "page_count": 15,
            },
            "preprocess": {
                "status": "pending",
                "task_id": "task-reference-preprocess-1",
                "message": "文件较大，已进入 Reference Library 后台解析队列；解析完成前不要引用全文内容。",
            },
        }
    )

    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads.publish_workspace_event",
            AsyncMock(),
        ),
        patch(
            "src.gateway.routers.uploads.SourceLibraryImportService",
            return_value=SimpleNamespace(import_uploaded_pdf=import_uploaded_pdf),
        ),
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "literature", "workspace_id": "ws-1"},
            files=[("files", ("paper.pdf", io.BytesIO(b"%PDF-1.4 large"), "application/pdf"))],
        )

    assert response.status_code == 200
    body = response.json()
    preprocess = body["files"][0]["metadata"]["preprocess"]
    assert preprocess["status"] == "pending"
    assert preprocess["task_id"] == "task-reference-preprocess-1"
    assert "解析完成前不要引用全文内容" in preprocess["message"]


def test_literature_upload_reports_reference_preprocess_queue_failure(client):
    import_uploaded_pdf = AsyncMock(
        return_value={
            "success": True,
            "reference": {"id": "reference-1", "title": "Transformer Paper", "authors": ["Ashish Vaswani"]},
            "asset": {
                "id": "asset-1",
                "file_path": "references/paper.pdf",
                "public_url": "/api/workspaces/ws-1/files/references/paper.pdf",
            },
            "preprocess": {
                "status": "failed",
                "message": "queue offline",
            },
        }
    )

    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads.SourceLibraryImportService",
            return_value=SimpleNamespace(import_uploaded_pdf=import_uploaded_pdf),
        ),
    ):
        response = client.post(
            "/api/threads/thread-1/uploads",
            data={"kind": "literature", "workspace_id": "ws-1"},
            files=[("files", ("paper.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["metadata"]["preprocess"]["status"] == "failed"
    assert "queue offline" in body["files"][0]["metadata"]["preprocess"]["message"]


def test_workspace_context_upload_creates_artifact_and_memory_note(client):
    mock_knowledge_service = MagicMock()
    mock_knowledge_service.upsert = AsyncMock()

    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads.publish_workspace_event",
            AsyncMock(),
        ) as publish_workspace_event,
        patch(
            "src.gateway.routers.uploads.KnowledgeService",
            return_value=mock_knowledge_service,
        ),
        patch(
            "src.gateway.routers.uploads.extract_document_preview",
            return_value={
                "title": "Opening Proposal",
                "authors": [],
                "page_count": None,
                "text_preview": "# proposal",
            },
        ),
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
    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "artifacts"]},
    )


def test_workspace_context_upload_degrades_when_memory_write_fails(client):
    mock_knowledge_service = MagicMock()
    mock_knowledge_service.upsert = AsyncMock(side_effect=RuntimeError("memory offline"))

    with (
        _patch_storage_roots(client.app),
        patch(
            "src.gateway.routers.uploads.publish_workspace_event",
            AsyncMock(),
        ) as publish_workspace_event,
        patch(
            "src.gateway.routers.uploads.KnowledgeService",
            return_value=mock_knowledge_service,
        ),
        patch(
            "src.gateway.routers.uploads.extract_document_preview",
            return_value={
                "title": "Opening Proposal",
                "authors": [],
                "page_count": None,
                "text_preview": "# proposal",
            },
        ),
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
    publish_workspace_event.assert_awaited_once_with(
        "ws-1",
        "workspace.refresh",
        {"refresh_targets": ["dashboard", "artifacts"]},
    )

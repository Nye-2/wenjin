"""Tests for workspace templates router."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_template_service, get_workspace_service
from src.gateway.routers.templates import router


def _mock_user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1")


def _mock_template(*, template_id: str, name: str, source_file_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=template_id,
        name=name,
        category="thesis",
        source_type="tex",
        structure=None,
        format_spec=None,
        content_guidelines=None,
        is_active=True,
        is_builtin=False,
        source_file_path=source_file_path,
    )


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    workspace = SimpleNamespace(id="ws-1", user_id="user-1", type="thesis")
    workspace_service = MagicMock()
    workspace_service.get = AsyncMock(return_value=workspace)

    template_service = MagicMock()
    template_service.list_by_workspace = AsyncMock(return_value=[])
    template_service.get_active = AsyncMock(return_value=None)
    template_service.activate = AsyncMock(return_value=None)
    template_service.delete = AsyncMock(return_value=True)

    async def _create_template(**kwargs):
        return _mock_template(
            template_id=f"tpl-{template_service.create.await_count}",
            name=str(kwargs.get("name") or "template"),
            source_file_path=str(kwargs.get("source_file_path") or ""),
        )

    template_service.create = AsyncMock(side_effect=_create_template)

    async def _get_current_user():
        return _mock_user()

    async def _get_workspace_service():
        return workspace_service

    async def _get_template_service():
        return template_service

    app.dependency_overrides[get_current_user] = _get_current_user
    app.dependency_overrides[get_workspace_service] = _get_workspace_service
    app.dependency_overrides[get_template_service] = _get_template_service

    app.state.workspace_service = workspace_service
    app.state.template_service = template_service
    app.state.temp_root = tmp_path
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_upload_template_persists_into_workspace_upload_root(client: TestClient) -> None:
    upload_root = client.app.state.temp_root / "workspace_uploads"
    with patch("src.gateway.routers.templates._TEMPLATE_UPLOAD_ROOT", upload_root), patch(
        "src.gateway.routers.templates.parse_template_content",
        AsyncMock(return_value={}),
    ):
        response = client.post(
            "/api/workspaces/ws-1/templates/upload",
            files=[("file", ("template.tex", io.BytesIO(b"\\documentclass{article}"), "text/plain"))],
        )

    assert response.status_code == 200
    create_kwargs = client.app.state.template_service.create.await_args.kwargs
    stored_path = Path(create_kwargs["source_file_path"])
    assert stored_path.exists()
    assert stored_path.parent == upload_root / "ws-1" / "templates"


def test_upload_template_allocates_unique_path_for_duplicate_filename(client: TestClient) -> None:
    upload_root = client.app.state.temp_root / "workspace_uploads"
    with patch("src.gateway.routers.templates._TEMPLATE_UPLOAD_ROOT", upload_root), patch(
        "src.gateway.routers.templates.parse_template_content",
        AsyncMock(return_value={}),
    ):
        first = client.post(
            "/api/workspaces/ws-1/templates/upload",
            files=[("file", ("template.tex", io.BytesIO(b"first"), "text/plain"))],
        )
        second = client.post(
            "/api/workspaces/ws-1/templates/upload",
            files=[("file", ("template.tex", io.BytesIO(b"second"), "text/plain"))],
        )

    assert first.status_code == 200
    assert second.status_code == 200

    create_calls = client.app.state.template_service.create.await_args_list
    first_path = Path(create_calls[0].kwargs["source_file_path"])
    second_path = Path(create_calls[1].kwargs["source_file_path"])

    assert first_path.name == "template.tex"
    assert second_path.name == "template-2.tex"
    assert first_path.exists()
    assert second_path.exists()

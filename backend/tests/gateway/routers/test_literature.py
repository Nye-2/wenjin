"""Tests for literature router.

This module tests the literature endpoints including:
- Literature CRUD operations
- Literature batch import
- Literature count
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers.literature import router


def create_mock_user(user_id="user-1"):
    user = MagicMock()
    user.id = user_id
    return user


def create_mock_workspace(user_id="user-1"):
    workspace = MagicMock()
    workspace.id = "ws-1"
    workspace.user_id = user_id
    return workspace


def create_test_app(user, literature_service, workspace_service):
    from src.gateway.routers.auth import get_current_user
    from src.gateway.routers.literature import (
        get_literature_service,
        get_workspace_service,
    )

    app = FastAPI()

    async def override_get_current_user():
        return user

    async def override_get_literature_service():
        return literature_service

    async def override_get_workspace_service():
        return workspace_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_literature_service] = override_get_literature_service
    app.dependency_overrides[get_workspace_service] = override_get_workspace_service
    app.include_router(router)
    return TestClient(app)


class TestLiteratureRouter:
    def test_list_literature(self):
        svc = AsyncMock()
        svc.list_literature.return_value = {"items": [], "total": 0, "core_count": 0}
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace()
        client = create_test_app(create_mock_user(), svc, ws_svc)

        resp = client.get("/workspaces/ws-1/literature")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_create_literature(self):
        svc = AsyncMock()
        svc.create_literature.return_value = {
            "id": "lit-1",
            "workspace_id": "ws-1",
            "title": "Test Paper",
            "authors": ["Author"],
            "year": None,
            "citations": None,
            "venue": None,
            "quartile": None,
            "abstract": None,
            "doi": None,
            "source": "manual",
            "is_core": False,
            "created_at": None,
            "updated_at": None,
        }
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace()
        client = create_test_app(create_mock_user(), svc, ws_svc)

        resp = client.post("/workspaces/ws-1/literature", json={
            "title": "Test Paper", "authors": ["Author"],
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "lit-1"

    def test_get_literature_count(self):
        svc = AsyncMock()
        svc.count_literature.return_value = {"total": 18, "core": 5}
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace()
        client = create_test_app(create_mock_user(), svc, ws_svc)

        resp = client.get("/workspaces/ws-1/literature/count")
        assert resp.status_code == 200
        assert resp.json()["total"] == 18

    def test_update_literature_core_flag(self):
        svc = AsyncMock()
        svc.update_literature.return_value = {
            "id": "lit-1",
            "workspace_id": "ws-1",
            "title": "Test Paper",
            "authors": ["Author"],
            "year": None,
            "citations": None,
            "venue": None,
            "quartile": None,
            "abstract": None,
            "doi": None,
            "source": "manual",
            "is_core": True,
            "created_at": None,
            "updated_at": None,
        }
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace()
        client = create_test_app(create_mock_user(), svc, ws_svc)

        resp = client.patch("/workspaces/ws-1/literature/lit-1", json={"is_core": True})
        assert resp.status_code == 200
        svc.update_literature.assert_called_once_with(
            literature_id="lit-1",
            workspace_id="ws-1",
            is_core=True,
        )

    def test_delete_literature(self):
        svc = AsyncMock()
        svc.delete_literature.return_value = True
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace()
        client = create_test_app(create_mock_user(), svc, ws_svc)

        resp = client.delete("/workspaces/ws-1/literature/lit-1")
        assert resp.status_code == 204
        svc.delete_literature.assert_called_once_with("lit-1", workspace_id="ws-1")

    def test_batch_import_literature(self):
        svc = AsyncMock()
        svc.batch_import.return_value = {"imported": 3}
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace()
        client = create_test_app(create_mock_user(), svc, ws_svc)

        resp = client.post("/workspaces/ws-1/literature/import", json={
            "source": "deep_research", "artifact_ids": ["p1", "p2", "p3"],
        })
        assert resp.status_code == 200
        assert resp.json()["imported"] == 3
        svc.batch_import.assert_called_once_with(
            workspace_id="ws-1",
            source="deep_research",
            paper_ids=["p1", "p2", "p3"],
        )

    def test_list_literature_forbidden_when_not_owner(self):
        svc = AsyncMock()
        ws_svc = AsyncMock()
        ws_svc.get.return_value = create_mock_workspace(user_id="another-user")
        client = create_test_app(create_mock_user("user-1"), svc, ws_svc)

        resp = client.get("/workspaces/ws-1/literature")
        assert resp.status_code == 403
        svc.list_literature.assert_not_called()

    def test_update_literature_404_when_workspace_missing(self):
        svc = AsyncMock()
        ws_svc = AsyncMock()
        ws_svc.get.return_value = None
        client = create_test_app(create_mock_user("user-1"), svc, ws_svc)

        resp = client.patch("/workspaces/ws-1/literature/lit-1", json={"is_core": True})
        assert resp.status_code == 404
        svc.update_literature.assert_not_called()

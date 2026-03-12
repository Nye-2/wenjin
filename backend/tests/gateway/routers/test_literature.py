"""Tests for literature router.

This module tests the literature endpoints including:
- Literature CRUD operations
- Literature batch import
- Literature count
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.gateway.routers.literature import router


def create_mock_user(user_id="user-1"):
    user = MagicMock()
    user.id = user_id
    return user


def create_test_app(user, literature_service):
    from src.gateway.routers.auth import get_current_user
    from src.gateway.routers.literature import get_literature_service

    app = FastAPI()

    async def override_get_current_user():
        return user

    async def override_get_literature_service():
        return literature_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_literature_service] = override_get_literature_service
    app.include_router(router)
    return TestClient(app)


class TestLiteratureRouter:
    def test_list_literature(self):
        svc = AsyncMock()
        svc.list_literature.return_value = {"items": [], "total": 0, "core_count": 0}
        client = create_test_app(create_mock_user(), svc)

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
        client = create_test_app(create_mock_user(), svc)

        resp = client.post("/workspaces/ws-1/literature", json={
            "title": "Test Paper", "authors": ["Author"],
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "lit-1"

    def test_get_literature_count(self):
        svc = AsyncMock()
        svc.count_literature.return_value = {"total": 18, "core": 5}
        client = create_test_app(create_mock_user(), svc)

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
        client = create_test_app(create_mock_user(), svc)

        resp = client.patch("/workspaces/ws-1/literature/lit-1", json={"is_core": True})
        assert resp.status_code == 200

    def test_delete_literature(self):
        svc = AsyncMock()
        svc.delete_literature.return_value = True
        client = create_test_app(create_mock_user(), svc)

        resp = client.delete("/workspaces/ws-1/literature/lit-1")
        assert resp.status_code == 204

    def test_batch_import_literature(self):
        svc = AsyncMock()
        svc.batch_import.return_value = {"imported": 3}
        client = create_test_app(create_mock_user(), svc)

        resp = client.post("/workspaces/ws-1/literature/import", json={
            "source": "deep_research", "paper_ids": ["p1", "p2", "p3"],
        })
        assert resp.status_code == 200
        assert resp.json()["imported"] == 3

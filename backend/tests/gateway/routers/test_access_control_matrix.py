"""Access control matrix tests for canonical papers and artifacts routers.

Verifies that:
- Anonymous (no token) access returns 401
- Correct owner can access their resources

These tests validate the auth requirements from Phase 1.
Owner isolation (403 cross-user) will be tested in Phase 2 when
``require_workspace_owner`` is integrated into routers.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.middleware.error_handler import register_error_handlers

# ============ Shared Helpers ============

WORKSPACE_ID = "cccc0000-0000-0000-0000-000000000001"


# ============ Papers Router Access Control Tests ============


class TestPapersAuth:
    """Test that papers endpoints require authentication."""

    @pytest.fixture
    def unauthenticated_client(self):
        """Client with NO auth override — exercises real get_current_user."""
        from src.gateway.routers.papers import get_paper_service, router

        app = FastAPI()
        register_error_handlers(app)

        mock_service = AsyncMock()
        mock_service.get = AsyncMock(return_value=None)
        mock_service.create = AsyncMock()

        async def override_service():
            return mock_service

        app.dependency_overrides[get_paper_service] = override_service
        app.include_router(router)
        return TestClient(app)

    def test_create_paper_requires_auth(self, unauthenticated_client):
        """POST /papers/ without token should return 401."""
        response = unauthenticated_client.post(
            "/papers",
            json={"title": "Unauthorized Paper"},
        )
        assert response.status_code == 401

    def test_list_papers_requires_auth(self, unauthenticated_client):
        """GET /papers/ without token should return 401."""
        response = unauthenticated_client.get("/papers")
        assert response.status_code == 401

    def test_get_paper_requires_auth(self, unauthenticated_client):
        """GET /papers/{id} without token should return 401."""
        response = unauthenticated_client.get(f"/papers/{uuid4()}")
        assert response.status_code == 401

    def test_update_paper_requires_auth(self, unauthenticated_client):
        """PUT /papers/{id} without token should return 401."""
        response = unauthenticated_client.put(
            f"/papers/{uuid4()}",
            json={"title": "Updated"},
        )
        assert response.status_code == 401

    def test_delete_paper_requires_auth(self, unauthenticated_client):
        """DELETE /papers/{id} without token should return 401."""
        response = unauthenticated_client.delete(f"/papers/{uuid4()}")
        assert response.status_code == 401

    def test_extract_paper_requires_auth(self, unauthenticated_client):
        """POST /papers/{id}/extract without token should return 401."""
        response = unauthenticated_client.post(
            f"/papers/{uuid4()}/extract",
            params={"workspace_id": WORKSPACE_ID},
        )
        assert response.status_code == 401

    def test_get_sections_requires_auth(self, unauthenticated_client):
        """GET /papers/{id}/sections without token should return 401."""
        response = unauthenticated_client.get(f"/papers/{uuid4()}/sections")
        assert response.status_code == 401

    def test_search_papers_requires_auth(self, unauthenticated_client):
        """POST /papers/search without token should return 401."""
        response = unauthenticated_client.post(
            "/papers/search",
            json={"query": "test"},
        )
        assert response.status_code == 401


class TestArtifactsAuth:
    """Test that artifacts endpoints require authentication."""

    @pytest.fixture
    def unauthenticated_client(self):
        """Client with NO auth override."""
        from src.gateway.routers.artifacts import get_artifact_service, router

        app = FastAPI()
        register_error_handlers(app)

        mock_service = AsyncMock()
        mock_service.get = AsyncMock(return_value=None)
        mock_service.create = AsyncMock()
        mock_service.list_by_workspace = AsyncMock(return_value=[])

        async def override_service():
            return mock_service

        app.dependency_overrides[get_artifact_service] = override_service
        app.include_router(router)
        return TestClient(app)

    def test_create_artifact_requires_auth(self, unauthenticated_client):
        """POST /workspaces/{id}/artifacts without token should return 401."""
        response = unauthenticated_client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"test": True},
            },
        )
        assert response.status_code == 401

    def test_list_artifacts_requires_auth(self, unauthenticated_client):
        """GET /workspaces/{id}/artifacts without token should return 401."""
        response = unauthenticated_client.get(f"/workspaces/{WORKSPACE_ID}/artifacts")
        assert response.status_code == 401

    def test_update_artifact_requires_auth(self, unauthenticated_client):
        """PUT /workspaces/{id}/artifacts/{id} without token should return 401."""
        response = unauthenticated_client.put(
            f"/workspaces/{WORKSPACE_ID}/artifacts/{uuid4()}",
            json={"title": "Updated"},
        )
        assert response.status_code == 401

    def test_delete_artifact_requires_auth(self, unauthenticated_client):
        """DELETE /workspaces/{id}/artifacts/{id} without token should return 401."""
        response = unauthenticated_client.delete(f"/workspaces/{WORKSPACE_ID}/artifacts/{uuid4()}")
        assert response.status_code == 401

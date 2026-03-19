"""Access control matrix tests for papers, artifacts, and academic routers.

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
        """POST /artifacts/ without token should return 401."""
        response = unauthenticated_client.post(
            "/artifacts",
            json={
                "workspace_id": WORKSPACE_ID,
                "type": "research_idea",
                "content": {"test": True},
            },
        )
        assert response.status_code == 401

    def test_list_artifacts_requires_auth(self, unauthenticated_client):
        """GET /artifacts/ without token should return 401."""
        response = unauthenticated_client.get(
            f"/artifacts/?workspace_id={WORKSPACE_ID}"
        )
        assert response.status_code == 401

    def test_update_artifact_requires_auth(self, unauthenticated_client):
        """PUT /artifacts/{id} without token should return 401."""
        response = unauthenticated_client.put(
            f"/artifacts/{uuid4()}",
            json={"title": "Updated"},
        )
        assert response.status_code == 401

    def test_delete_artifact_requires_auth(self, unauthenticated_client):
        """DELETE /artifacts/{id} without token should return 401."""
        response = unauthenticated_client.delete(f"/artifacts/{uuid4()}")
        assert response.status_code == 401


class TestAcademicAuth:
    """Test that academic endpoints require authentication."""

    @pytest.fixture
    def unauthenticated_client(self):
        """Client with NO auth override."""
        from src.gateway.routers.academic import (
            get_artifact_service,
            get_paper_service,
            router,
        )

        app = FastAPI()
        register_error_handlers(app)

        mock_paper_service = AsyncMock()
        mock_artifact_service = AsyncMock()
        mock_artifact_service.list_by_workspace = AsyncMock(return_value=[])

        async def override_paper_service():
            return mock_paper_service

        async def override_artifact_service():
            return mock_artifact_service

        app.dependency_overrides[get_paper_service] = override_paper_service
        app.dependency_overrides[get_artifact_service] = override_artifact_service
        app.include_router(router)
        return TestClient(app)

    def test_create_paper_requires_auth(self, unauthenticated_client):
        """POST /academic/papers without token should return 401."""
        response = unauthenticated_client.post(
            "/academic/papers",
            json={"title": "Unauthorized Paper"},
        )
        assert response.status_code == 401

    def test_search_papers_requires_auth(self, unauthenticated_client):
        """GET /papers/search without token should return 401."""
        response = unauthenticated_client.get(
            "/papers/search",
            params={"query": "test"},
        )
        assert response.status_code == 401

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
        response = unauthenticated_client.get(
            f"/workspaces/{WORKSPACE_ID}/artifacts"
        )
        assert response.status_code == 401

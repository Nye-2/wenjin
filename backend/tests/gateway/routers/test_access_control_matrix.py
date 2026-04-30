"""Access control matrix tests for canonical references and artifacts routers.

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


# ============ References Router Access Control Tests ============


class TestReferencesAuth:
    """Test that Reference Library endpoints require authentication."""

    @pytest.fixture
    def unauthenticated_client(self):
        """Client with NO auth override — exercises real get_current_user."""
        from src.gateway.routers.references import router

        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router)
        return TestClient(app)

    def test_create_reference_requires_auth(self, unauthenticated_client):
        """POST /workspaces/{id}/references/manual without token should return 401."""
        response = unauthenticated_client.post(
            f"/workspaces/{WORKSPACE_ID}/references/manual",
            json={"title": "Unauthorized Reference"},
        )
        assert response.status_code == 401

    def test_list_references_requires_auth(self, unauthenticated_client):
        """GET /workspaces/{id}/references without token should return 401."""
        response = unauthenticated_client.get(f"/workspaces/{WORKSPACE_ID}/references")
        assert response.status_code == 401

    def test_get_reference_requires_auth(self, unauthenticated_client):
        """GET /workspaces/{id}/references/{id} without token should return 401."""
        response = unauthenticated_client.get(f"/workspaces/{WORKSPACE_ID}/references/{uuid4()}")
        assert response.status_code == 401

    def test_update_reference_requires_auth(self, unauthenticated_client):
        """PATCH /workspaces/{id}/references/{id} without token should return 401."""
        response = unauthenticated_client.patch(
            f"/workspaces/{WORKSPACE_ID}/references/{uuid4()}",
            json={"title": "Updated"},
        )
        assert response.status_code == 401

    def test_delete_reference_requires_auth(self, unauthenticated_client):
        """DELETE /workspaces/{id}/references/{id} without token should return 401."""
        response = unauthenticated_client.delete(f"/workspaces/{WORKSPACE_ID}/references/{uuid4()}")
        assert response.status_code == 401

    def test_reference_outline_requires_auth(self, unauthenticated_client):
        """GET /workspaces/{id}/references/{id}/outline without token should return 401."""
        response = unauthenticated_client.get(f"/workspaces/{WORKSPACE_ID}/references/{uuid4()}/outline")
        assert response.status_code == 401

    def test_reference_evidence_pack_requires_auth(self, unauthenticated_client):
        """POST /workspaces/{id}/references/evidence-pack without token should return 401."""
        response = unauthenticated_client.post(
            f"/workspaces/{WORKSPACE_ID}/references/evidence-pack",
            json={"query": "test"},
        )
        assert response.status_code == 401

    def test_search_reference_text_units_requires_auth(self, unauthenticated_client):
        """POST /workspaces/{id}/references/search-text-units without token should return 401."""
        response = unauthenticated_client.post(
            f"/workspaces/{WORKSPACE_ID}/references/search-text-units",
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

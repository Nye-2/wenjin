"""Tests for artifacts router.

This module tests the artifact endpoints including:
- Creating artifacts
- Listing artifacts (filtered by workspace and type)
- Getting artifact details
- Updating artifacts
- Deleting artifacts
- Getting artifact lineage
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import Artifact
from src.gateway.auth_dependencies import get_current_user_optional
from src.gateway.routers import artifacts as artifacts_router
from src.gateway.routers.artifacts import (
    get_artifact_service,
    get_thread_service,
    router,
)
from src.gateway.routers.auth import get_current_user

# Valid test UUIDs
WORKSPACE_ID = "550e8400-e29b-41d4-a716-446655440001"
USER_ID = "550e8400-e29b-41d4-a716-446655440002"


# ============ Mock Fixtures ============

class MockArtifactService:
    """Mock artifact service for testing."""

    def __init__(self):
        self.artifacts = {}
        self._id_counter = 0

    def _generate_id(self):
        self._id_counter += 1
        return str(uuid.UUID(int=self._id_counter))

    def _create_artifact_obj(self, **kwargs):
        """Create a mock artifact object."""
        artifact = MagicMock(spec=Artifact)
        artifact.id = kwargs.get("id", self._generate_id())
        artifact.workspace_id = kwargs.get("workspace_id", WORKSPACE_ID)
        artifact.type = kwargs.get("type", "research_idea")
        artifact.title = kwargs.get("title")
        artifact.content = kwargs.get("content", {})
        artifact.created_by_skill = kwargs.get("created_by_skill")
        artifact.parent_artifact_id = kwargs.get("parent_artifact_id")
        artifact.version = kwargs.get("version", 1)
        artifact.status = kwargs.get("status", "draft")
        artifact.created_at = kwargs.get("created_at", datetime.now(UTC))
        artifact.updated_at = kwargs.get("updated_at", datetime.now(UTC))

        # Add table mock for orm_to_dict
        artifact.__table__ = MagicMock()
        artifact.__table__.columns = [
            self._create_column_mock("id", artifact.id),
            self._create_column_mock("workspace_id", artifact.workspace_id),
            self._create_column_mock("type", artifact.type),
            self._create_column_mock("title", artifact.title),
            self._create_column_mock("content", artifact.content),
            self._create_column_mock("created_by_skill", artifact.created_by_skill),
            self._create_column_mock("parent_artifact_id", artifact.parent_artifact_id),
            self._create_column_mock("version", artifact.version),
            self._create_column_mock("status", artifact.status),
            self._create_column_mock("created_at", artifact.created_at),
            self._create_column_mock("updated_at", artifact.updated_at),
        ]
        return artifact

    def _create_column_mock(self, name, value):
        """Create a mock column object."""
        column = MagicMock()
        column.name = name
        return column

    async def create(self, workspace_id, type, content, title=None,
                     created_by_skill=None, parent_artifact_id=None, status="draft"):
        artifact = self._create_artifact_obj(
            workspace_id=workspace_id,
            type=type,
            content=content,
            title=title,
            created_by_skill=created_by_skill,
            parent_artifact_id=parent_artifact_id,
            status=status,
        )
        self.artifacts[artifact.id] = artifact
        return artifact

    async def get(self, artifact_id):
        return self.artifacts.get(artifact_id)

    async def list_by_workspace(self, workspace_id, type=None):
        result = [a for a in self.artifacts.values() if a.workspace_id == workspace_id]
        if type:
            result = [a for a in result if a.type == type]
        return result

    async def update(self, artifact_id, content=None, title=None, status=None, increment_version=False):
        artifact = self.artifacts.get(artifact_id)
        if not artifact:
            return None

        if content is not None:
            artifact.content = content
        if title is not None:
            artifact.title = title
        if status is not None:
            artifact.status = status
        if increment_version:
            artifact.version += 1
        artifact.updated_at = datetime.now(UTC)
        return artifact

    async def delete(self, artifact_id):
        if artifact_id in self.artifacts:
            del self.artifacts[artifact_id]
            return True
        return False

    async def get_lineage(self, artifact_id):
        """Get artifact lineage (parent chain)."""
        lineage = []
        current_id = artifact_id

        while current_id:
            artifact = self.artifacts.get(current_id)
            if not artifact:
                break
            lineage.append(artifact)
            current_id = artifact.parent_artifact_id

        return list(reversed(lineage))


class MockThreadService:
    """Mock chat thread service for thread artifact file serving."""

    def __init__(self):
        self._thread = MagicMock()
        self._thread.id = "thread-1"
        self._thread.user_id = USER_ID

    async def get_thread(self, thread_id, user_id):
        if thread_id == self._thread.id and user_id == self._thread.user_id:
            return self._thread
        return None


class MockWorkspaceService:
    """Mock workspace service for workspace file serving."""

    def __init__(self):
        self._workspace = MagicMock()
        self._workspace.id = WORKSPACE_ID
        self._workspace.user_id = USER_ID
        self._workspace.type = "thesis"

    async def get(self, workspace_id):
        if workspace_id == self._workspace.id:
            return self._workspace
        return None


@pytest.fixture
def mock_service():
    """Create a mock artifact service."""
    return MockArtifactService()


@pytest.fixture
def mock_thread_service():
    """Create a mock chat thread service."""
    return MockThreadService()


@pytest.fixture
def mock_workspace_service():
    """Create a mock workspace service."""
    return MockWorkspaceService()


def create_mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = USER_ID
    user.email = "test@test.com"
    user.is_active = True
    return user


@pytest.fixture
def app(mock_service, mock_thread_service, mock_workspace_service):
    """Create FastAPI app with artifacts router."""
    app = FastAPI()

    # Override the artifact service dependency
    async def get_artifact_service_override():
        return mock_service

    async def get_current_user_override():
        return create_mock_user()

    async def get_thread_service_override():
        return mock_thread_service

    async def get_workspace_service_override():
        return mock_workspace_service

    app.dependency_overrides[get_artifact_service] = get_artifact_service_override
    app.dependency_overrides[get_thread_service] = get_thread_service_override
    app.dependency_overrides[artifacts_router.get_workspace_service] = (
        get_workspace_service_override
    )
    app.dependency_overrides[get_current_user] = get_current_user_override
    app.dependency_overrides[get_current_user_optional] = get_current_user_override
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


# ============ Test Classes ============


class TestThreadArtifactFiles:
    """Test thread-scoped sandbox artifact file serving."""

    def test_get_thread_artifact_success(self, client, monkeypatch, tmp_path):
        thread_root = tmp_path / "thread-1" / "user-data"
        artifact_path = thread_root / "outputs" / "report.md"
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text("# Report", encoding="utf-8")

        monkeypatch.setattr(
            artifacts_router,
            "get_thread_data_root",
            lambda thread_id: thread_root,
        )

        response = client.get("/threads/thread-1/artifacts/mnt/user-data/outputs/report.md")

        assert response.status_code == 200
        assert response.text == "# Report"

    def test_get_thread_artifact_downgrades_html_to_plain_text(
        self,
        client,
        monkeypatch,
        tmp_path,
    ):
        thread_root = tmp_path / "thread-1" / "user-data"
        artifact_path = thread_root / "outputs" / "report.html"
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text("<script>alert('xss')</script>", encoding="utf-8")

        monkeypatch.setattr(
            artifacts_router,
            "get_thread_data_root",
            lambda thread_id: thread_root,
        )

        response = client.get("/threads/thread-1/artifacts/mnt/user-data/outputs/report.html")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "<script>alert('xss')</script>" in response.text

    def test_get_thread_artifact_inline_response_avoids_eager_file_reads(
        self,
        client,
        monkeypatch,
        tmp_path,
    ):
        thread_root = tmp_path / "thread-1" / "user-data"
        artifact_path = thread_root / "outputs" / "report.txt"
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text("stream me", encoding="utf-8")

        monkeypatch.setattr(
            artifacts_router,
            "get_thread_data_root",
            lambda thread_id: thread_root,
        )

        original_read_bytes = artifacts_router.Path.read_bytes
        original_read_text = artifacts_router.Path.read_text

        def _guard_read_bytes(path_obj):
            if path_obj == artifact_path:
                raise AssertionError("inline artifact response should not call read_bytes")
            return original_read_bytes(path_obj)

        def _guard_read_text(path_obj, *args, **kwargs):
            if path_obj == artifact_path:
                raise AssertionError("inline artifact response should not call read_text")
            return original_read_text(path_obj, *args, **kwargs)

        monkeypatch.setattr(artifacts_router.Path, "read_bytes", _guard_read_bytes)
        monkeypatch.setattr(artifacts_router.Path, "read_text", _guard_read_text)

        response = client.get("/threads/thread-1/artifacts/mnt/user-data/outputs/report.txt")

        assert response.status_code == 200
        assert response.text == "stream me"

    def test_get_thread_artifact_rejects_paths_outside_virtual_root(self, client):
        response = client.get("/threads/thread-1/artifacts/etc/passwd")

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_get_thread_artifact_requires_owned_thread(self, client):
        response = client.get("/threads/thread-2/artifacts/mnt/user-data/outputs/report.md")

        assert response.status_code == 404
        assert response.json()["detail"] == "Thread not found"

    def test_get_thread_artifact_accepts_signed_url_without_auth(
        self,
        app,
        monkeypatch,
        tmp_path,
    ):
        thread_root = tmp_path / "thread-1" / "user-data"
        artifact_path = thread_root / "outputs" / "report.md"
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text("# Report", encoding="utf-8")

        monkeypatch.setattr(
            artifacts_router,
            "get_thread_data_root",
            lambda thread_id: thread_root,
        )

        client = TestClient(app)
        sign_response = client.post(
            "/assets/sign",
            json={"url": "/threads/thread-1/artifacts/mnt/user-data/outputs/report.md"},
        )
        assert sign_response.status_code == 200
        signed_url = sign_response.json()["signed_url"]

        app.dependency_overrides[get_current_user_optional] = lambda: None
        response = client.get(signed_url)

        assert response.status_code == 200
        assert response.text == "# Report"

class TestWorkspaceFiles:
    """Test canonical workspace upload file serving."""

    def test_get_workspace_file_success(self, client, monkeypatch, tmp_path):
        workspace_root = tmp_path / "workspace_uploads" / WORKSPACE_ID
        file_path = workspace_root / "papers" / "paper.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"%PDF-1.4")

        monkeypatch.setattr(
            artifacts_router,
            "resolve_workspace_upload_relative_path",
            lambda workspace_id, path: file_path,
        )

        response = client.get(f"/workspaces/{WORKSPACE_ID}/files/references/reference.pdf")

        assert response.status_code == 200
        assert response.content == b"%PDF-1.4"

    def test_get_workspace_file_rejects_escaped_path(self, client, monkeypatch):
        def _raise(*_args, **_kwargs):
            raise ValueError("File path escapes workspace uploads root")

        monkeypatch.setattr(
            artifacts_router,
            "resolve_workspace_upload_relative_path",
            _raise,
        )

        response = client.get(
            f"/workspaces/{WORKSPACE_ID}/files/%2E%2E/%2E%2E/etc/passwd"
        )

        assert response.status_code == 403
        assert "escapes workspace uploads root" in response.json()["detail"]

    def test_get_workspace_file_requires_owner(self, client):
        response = client.get("/workspaces/non-owned/files/references/reference.pdf")

        assert response.status_code == 404

    def test_get_workspace_file_accepts_signed_url_without_auth(
        self,
        app,
        monkeypatch,
        tmp_path,
    ):
        workspace_root = tmp_path / "workspace_uploads" / WORKSPACE_ID
        file_path = workspace_root / "references" / "reference.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"%PDF-1.4")

        monkeypatch.setattr(
            artifacts_router,
            "resolve_workspace_upload_relative_path",
            lambda workspace_id, path: file_path,
        )

        client = TestClient(app)
        sign_response = client.post(
            "/assets/sign",
            json={"url": f"/workspaces/{WORKSPACE_ID}/files/references/reference.pdf"},
        )
        assert sign_response.status_code == 200
        signed_url = sign_response.json()["signed_url"]

        app.dependency_overrides[get_current_user_optional] = lambda: None
        response = client.get(signed_url)

        assert response.status_code == 200
        assert response.content == b"%PDF-1.4"

    def test_sign_asset_url_rejects_absolute_urls(self, client):
        response = client.post(
            "/assets/sign",
            json={"url": f"https://evil.example/workspaces/{WORKSPACE_ID}/files/references/reference.pdf"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Asset url must be a relative API path"


class TestCreateArtifact:
    """Test create artifact endpoint."""

    def test_create_artifact_success(self, client):
        """Test successful artifact creation."""
        response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "title": "My Research Idea",
                "content": {"idea": "Test idea"},
                "created_by_skill": "deep-research",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["workspace_id"] == WORKSPACE_ID
        assert data["type"] == "research_idea"
        assert data["title"] == "My Research Idea"
        assert data["content"] == {"idea": "Test idea"}
        assert data["created_by_skill"] == "deep-research"
        assert data["status"] == "draft"
        assert data["version"] == 1

    def test_create_artifact_accepts_arbitrary_skill_id(self, client):
        """Legacy skill-catalog validation is gone; any non-empty id is accepted.

        Capability/skill validity is enforced at launch_feature time against
        the DB capability catalog, not at artifact creation.
        """
        response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "title": "My Research Idea",
                "content": {"idea": "Test idea"},
                "created_by_skill": "brainstorm",
            },
        )

        assert response.status_code == 201
        assert response.json()["created_by_skill"] == "brainstorm"

    def test_create_artifact_minimal(self, client):
        """Test artifact creation with minimal fields."""
        response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "methodology",
                "content": {"method": "quantitative"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["workspace_id"] == WORKSPACE_ID
        assert data["type"] == "methodology"
        assert data["title"] is None
        assert data["created_by_skill"] is None

    def test_create_artifact_with_parent(self, client):
        """Test artifact creation with parent artifact."""
        # First create a parent artifact
        parent_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Parent idea"},
            },
        )
        parent_id = parent_response.json()["id"]

        # Create child artifact
        response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "abstract",
                "content": {"text": "Child abstract"},
                "parent_artifact_id": parent_id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["parent_artifact_id"] == parent_id

    def test_create_artifact_missing_required_fields(self, client):
        """Test artifact creation with missing required fields."""
        response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                # Missing type and content
            },
        )

        assert response.status_code == 422  # Validation error


class TestListArtifacts:
    """Test list artifacts endpoint."""

    def test_list_artifacts_success(self, client):
        """Test successful artifact listing."""
        # Create some artifacts
        client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Idea 1"},
            },
        )
        client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "methodology",
                "content": {"method": "Method 1"},
            },
        )

        response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["artifacts"]) == 2

    def test_list_artifacts_by_type(self, client):
        """Test artifact listing filtered by type."""
        # Create artifacts of different types
        client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Idea 1"},
            },
        )
        client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "methodology",
                "content": {"method": "Method 1"},
            },
        )

        response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts?type=research_idea")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["artifacts"]) == 1
        assert data["artifacts"][0]["type"] == "research_idea"

    def test_list_artifacts_empty(self, client):
        """Test artifact listing with no artifacts."""
        other_workspace = "550e8400-e29b-41d4-a716-446655440099"
        response = client.get(f"/workspaces/{other_workspace}/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["artifacts"] == []

    def test_list_artifacts_different_workspaces(self, client):
        """Test artifact listing isolates workspaces."""
        ws2 = "550e8400-e29b-41d4-a716-446655440098"
        # Create artifacts in different workspaces
        client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "WS1 Idea"},
            },
        )
        client.post(
            f"/workspaces/{ws2}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "WS2 Idea"},
            },
        )

        response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["artifacts"]) == 1
        assert data["artifacts"][0]["workspace_id"] == WORKSPACE_ID


class TestGetArtifact:
    """Test get artifact endpoint."""

    def test_get_artifact_success(self, client):
        """Test successful artifact retrieval."""
        # Create an artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "title": "Test Idea",
                "content": {"idea": "Test idea"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == artifact_id
        assert data["title"] == "Test Idea"
        assert data["content"] == {"idea": "Test idea"}

    def test_get_artifact_not_found(self, client):
        """Test get artifact with non-existent ID."""
        response = client.get(
            f"/workspaces/{WORKSPACE_ID}/artifacts/550e8400-e29b-41d4-a716-446655440099"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestUpdateArtifact:
    """Test update artifact endpoint."""

    def test_update_artifact_content(self, client):
        """Test updating artifact content."""
        # Create an artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Original idea"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.put(
            f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}",
            json={
                "content": {"idea": "Updated idea"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == {"idea": "Updated idea"}
        assert data["version"] == 2  # Version should increment

    def test_update_artifact_title(self, client):
        """Test updating artifact title."""
        # Create an artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Test"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.put(
            f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}",
            json={
                "title": "New Title",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"

    def test_update_artifact_status(self, client):
        """Test updating artifact status."""
        # Create an artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Test"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.put(
            f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}",
            json={
                "status": "in_review",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_review"

    def test_update_artifact_multiple_fields(self, client):
        """Test updating multiple artifact fields."""
        # Create an artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Test"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.put(
            f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}",
            json={
                "title": "Updated Title",
                "content": {"idea": "Updated idea"},
                "status": "approved",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["content"] == {"idea": "Updated idea"}
        assert data["status"] == "approved"

    def test_update_artifact_not_found(self, client):
        """Test updating non-existent artifact."""
        response = client.put(
            f"/workspaces/{WORKSPACE_ID}/artifacts/550e8400-e29b-41d4-a716-446655440099",
            json={
                "title": "New Title",
            },
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteArtifact:
    """Test delete artifact endpoint."""

    def test_delete_artifact_success(self, client):
        """Test successful artifact deletion."""
        # Create an artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Test"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.delete(f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify artifact is deleted
        get_response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}")
        assert get_response.status_code == 404

    def test_delete_artifact_not_found(self, client):
        """Test deleting non-existent artifact."""
        response = client.delete(
            f"/workspaces/{WORKSPACE_ID}/artifacts/550e8400-e29b-41d4-a716-446655440099"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestGetArtifactLineage:
    """Test get artifact lineage endpoint."""

    def test_get_lineage_single_artifact(self, client):
        """Test lineage for artifact without parent."""
        # Create a root artifact
        create_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Root idea"},
            },
        )
        artifact_id = create_response.json()["id"]

        response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts/{artifact_id}/lineage")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == artifact_id

    def test_get_lineage_with_parent(self, client):
        """Test lineage for artifact with parent chain."""
        # Create grandparent
        gp_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "research_idea",
                "content": {"idea": "Grandparent"},
            },
        )
        gp_id = gp_response.json()["id"]

        # Create parent
        p_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "methodology",
                "content": {"method": "Parent"},
                "parent_artifact_id": gp_id,
            },
        )
        p_id = p_response.json()["id"]

        # Create child
        c_response = client.post(
            f"/workspaces/{WORKSPACE_ID}/artifacts",
            json={
                "type": "abstract",
                "content": {"text": "Child"},
                "parent_artifact_id": p_id,
            },
        )
        c_id = c_response.json()["id"]

        response = client.get(f"/workspaces/{WORKSPACE_ID}/artifacts/{c_id}/lineage")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Order should be: grandparent -> parent -> child
        assert data[0]["id"] == gp_id
        assert data[1]["id"] == p_id
        assert data[2]["id"] == c_id

    def test_get_lineage_not_found(self, client):
        """Test lineage for non-existent artifact."""
        response = client.get(
            f"/workspaces/{WORKSPACE_ID}/artifacts/550e8400-e29b-41d4-a716-446655440099/lineage"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

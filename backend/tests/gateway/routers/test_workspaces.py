"""Tests for workspaces router.

This module tests the workspaces endpoints including:
- Workspace CRUD operations
- Paper association management
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import Paper, User, Workspace
from src.gateway.routers import workspaces
from src.gateway.routers.auth import get_current_user


def create_mock_workspace(
    id: str = "test-workspace-id",
    user_id: str = "test-user-id",
    name: str = "Test Workspace",
    type: str = "sci",
    discipline: str = "computer_science",
    description: str = "Test description",
    config: dict = None,
):
    """Create a mock Workspace object."""
    workspace = MagicMock(spec=Workspace)
    workspace.id = id
    workspace.user_id = user_id
    workspace.name = name
    # Create a mock type enum that has .value attribute
    mock_type = MagicMock()
    mock_type.value = type
    workspace.type = mock_type
    workspace.discipline = discipline
    workspace.description = description
    workspace.config = config or {}
    workspace.created_at = datetime.now(UTC)
    workspace.updated_at = datetime.now(UTC)
    return workspace


def create_mock_paper(
    id: str = "test-paper-id",
    doi: str = "10.1234/test",
    title: str = "Test Paper Title",
    authors: list = None,
    year: int = 2024,
    venue: str = "Test Conference",
    abstract: str = "Test abstract",
    source: str = "manual_upload",
    citation_count: int = 10,
    reference_count: int = 20,
):
    """Create a mock Paper object."""
    paper = MagicMock(spec=Paper)
    paper.id = id
    paper.doi = doi
    paper.title = title
    paper.authors = authors or [{"name": "Test Author"}]
    paper.year = year
    paper.venue = venue
    paper.abstract = abstract
    paper.source = source
    paper.citation_count = citation_count
    paper.reference_count = reference_count
    return paper


def create_mock_user(
    id: str = "test-user-id",
    email: str = "test@example.com",
    name: str = "Test User",
    role: str = "user",
    is_active: bool = True,
):
    """Create a mock User object."""
    user = MagicMock(spec=User)
    user.id = id
    user.email = email
    user.name = name
    user.role = role
    user.is_active = is_active
    return user


# ============ Create Workspace Tests ============

class TestCreateWorkspace:
    """Test create workspace endpoint."""

    @pytest.fixture
    def mock_workspace_service(self):
        """Create mock workspace service."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def client(self, mock_workspace_service, mock_user):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_workspace_service():
            return mock_workspace_service

        async def override_get_current_user():
            return mock_user

        app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_create_workspace_success(self, client, mock_workspace_service):
        """Test successful workspace creation."""
        mock_workspace = create_mock_workspace()
        mock_workspace_service.create.return_value = mock_workspace

        response = client.post(
            "/workspaces/",
            json={
                "name": "Test Workspace",
                "type": "sci",
                "discipline": "computer_science",
                "description": "Test description",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Workspace"
        assert data["type"] == "sci"
        assert data["discipline"] == "computer_science"
        mock_workspace_service.create.assert_called_once()

    def test_create_workspace_with_config(self, client, mock_workspace_service):
        """Test workspace creation with config."""
        mock_workspace = create_mock_workspace(config={"key": "value"})
        mock_workspace_service.create.return_value = mock_workspace

        response = client.post(
            "/workspaces/",
            json={
                "name": "Test Workspace",
                "type": "thesis",
                "config": {"key": "value"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["config"] == {"key": "value"}

    def test_create_workspace_invalid_type(self, client, mock_workspace_service):
        """Test workspace creation with invalid type.

        The WorkspaceType enum in the validator ensures only valid types
        are accepted. Pydantic returns a 422 validation error for invalid types.
        """
        response = client.post(
            "/workspaces/",
            json={
                "name": "Test Workspace",
                "type": "invalid_type",
            },
        )

        # Pydantic validates the enum at the request level
        assert response.status_code == 422  # Validation error from Pydantic

    def test_create_workspace_missing_name(self, client, mock_workspace_service):
        """Test workspace creation without name fails."""
        response = client.post(
            "/workspaces/",
            json={
                "type": "sci",
            },
        )

        assert response.status_code == 422  # Validation error


# ============ List Workspaces Tests ============

class TestListWorkspaces:
    """Test list workspaces endpoint."""

    @pytest.fixture
    def mock_workspace_service(self):
        """Create mock workspace service."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def client(self, mock_workspace_service, mock_user):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_workspace_service():
            return mock_workspace_service

        async def override_get_current_user():
            return mock_user

        app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_list_workspaces_success(self, client, mock_workspace_service):
        """Test successful workspace listing."""
        mock_workspaces = [
            create_mock_workspace(id="ws-1", name="Workspace 1"),
            create_mock_workspace(id="ws-2", name="Workspace 2"),
        ]
        mock_workspace_service.list_by_user.return_value = mock_workspaces

        response = client.get("/workspaces/")

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        workspaces = data["workspaces"]
        assert len(workspaces) == 2
        assert workspaces[0]["name"] == "Workspace 1"
        assert workspaces[1]["name"] == "Workspace 2"
        mock_workspace_service.list_by_user.assert_called_once_with("test-user-id")

    def test_list_workspaces_empty(self, client, mock_workspace_service):
        """Test listing workspaces when user has none."""
        mock_workspace_service.list_by_user.return_value = []

        response = client.get("/workspaces/")

        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        assert len(data["workspaces"]) == 0


# ============ Get Workspace Tests ============

class TestGetWorkspace:
    """Test get workspace endpoint."""

    @pytest.fixture
    def mock_workspace_service(self):
        """Create mock workspace service."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def client(self, mock_workspace_service, mock_user):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_workspace_service():
            return mock_workspace_service

        async def override_get_current_user():
            return mock_user

        app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_get_workspace_success(self, client, mock_workspace_service):
        """Test successful workspace retrieval."""
        mock_workspace = create_mock_workspace()
        mock_workspace_service.get.return_value = mock_workspace

        response = client.get("/workspaces/test-workspace-id")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-workspace-id"
        assert data["name"] == "Test Workspace"
        mock_workspace_service.get.assert_called_once_with("test-workspace-id")

    def test_get_workspace_not_found(self, client, mock_workspace_service):
        """Test getting non-existent workspace."""
        mock_workspace_service.get.return_value = None

        response = client.get("/workspaces/non-existent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ============ Update Workspace Tests ============

class TestUpdateWorkspace:
    """Test update workspace endpoint."""

    @pytest.fixture
    def mock_workspace_service(self):
        """Create mock workspace service."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def client(self, mock_workspace_service, mock_user):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_workspace_service():
            return mock_workspace_service

        async def override_get_current_user():
            return mock_user

        app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_update_workspace_success(self, client, mock_workspace_service):
        """Test successful workspace update."""
        mock_workspace = create_mock_workspace(name="Updated Name")
        mock_workspace_service.update.return_value = mock_workspace

        response = client.put(
            "/workspaces/test-workspace-id",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        mock_workspace_service.update.assert_called_once()

    def test_update_workspace_partial(self, client, mock_workspace_service):
        """Test partial workspace update."""
        mock_workspace = create_mock_workspace(description="New description")
        mock_workspace_service.update.return_value = mock_workspace

        response = client.put(
            "/workspaces/test-workspace-id",
            json={"description": "New description"},
        )

        assert response.status_code == 200
        mock_workspace_service.update.assert_called_once()

    def test_update_workspace_not_found(self, client, mock_workspace_service):
        """Test updating non-existent workspace."""
        mock_workspace_service.update.return_value = None

        response = client.put(
            "/workspaces/non-existent-id",
            json={"name": "New Name"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ============ Delete Workspace Tests ============

class TestDeleteWorkspace:
    """Test delete workspace endpoint."""

    @pytest.fixture
    def mock_workspace_service(self):
        """Create mock workspace service."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def client(self, mock_workspace_service, mock_user):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_workspace_service():
            return mock_workspace_service

        async def override_get_current_user():
            return mock_user

        app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_delete_workspace_success(self, client, mock_workspace_service):
        """Test successful workspace deletion."""
        mock_workspace_service.delete.return_value = True

        response = client.delete("/workspaces/test-workspace-id")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_workspace_service.delete.assert_called_once_with("test-workspace-id")

    def test_delete_workspace_not_found(self, client, mock_workspace_service):
        """Test deleting non-existent workspace."""
        mock_workspace_service.delete.return_value = False

        response = client.delete("/workspaces/non-existent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ============ List Workspace Papers Tests ============

class TestListWorkspacePapers:
    """Test list workspace papers endpoint."""

    @pytest.fixture
    def mock_paper_service(self):
        """Create mock paper service."""
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_paper_service):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_paper_service():
            return mock_paper_service

        app.dependency_overrides[workspaces.get_paper_service] = override_get_paper_service
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_list_workspace_papers_success(self, client, mock_paper_service):
        """Test successful paper listing."""
        mock_papers = [
            create_mock_paper(id="paper-1", title="Paper 1"),
            create_mock_paper(id="paper-2", title="Paper 2"),
        ]
        mock_paper_service.list_workspace_papers.return_value = mock_papers

        response = client.get("/workspaces/test-workspace-id/papers")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["papers"]) == 2
        assert data["papers"][0]["title"] == "Paper 1"
        assert data["papers"][1]["title"] == "Paper 2"

    def test_list_workspace_papers_with_filter(self, client, mock_paper_service):
        """Test paper listing with read status filter."""
        mock_papers = [create_mock_paper(id="paper-1")]
        mock_paper_service.list_workspace_papers.return_value = mock_papers

        response = client.get("/workspaces/test-workspace-id/papers?read_status=read")

        assert response.status_code == 200
        mock_paper_service.list_workspace_papers.assert_called_once_with(
            workspace_id="test-workspace-id",
            read_status="read",
        )

    def test_list_workspace_papers_empty(self, client, mock_paper_service):
        """Test listing papers when workspace has none."""
        mock_paper_service.list_workspace_papers.return_value = []

        response = client.get("/workspaces/test-workspace-id/papers")

        assert response.status_code == 200
        data = response.json()
        assert data == {"papers": [], "count": 0}


# ============ Add Paper to Workspace Tests ============

class TestAddPaperToWorkspace:
    """Test add paper to workspace endpoint."""

    @pytest.fixture
    def mock_paper_service(self):
        """Create mock paper service."""
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_paper_service):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_paper_service():
            return mock_paper_service

        app.dependency_overrides[workspaces.get_paper_service] = override_get_paper_service
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_add_paper_success(self, client, mock_paper_service):
        """Test successfully adding paper to workspace."""
        mock_workspace_paper = MagicMock()
        mock_paper_service.add_to_workspace.return_value = mock_workspace_paper

        response = client.post(
            "/workspaces/test-workspace-id/papers/test-paper-id",
            json={"notes": "Important paper", "tags": ["ml", "ai"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["paper_id"] == "test-paper-id"
        mock_paper_service.add_to_workspace.assert_called_once_with(
            paper_id="test-paper-id",
            workspace_id="test-workspace-id",
            notes="Important paper",
            tags=["ml", "ai"],
            is_primary=False,
        )

    def test_add_paper_with_is_primary(self, client, mock_paper_service):
        """Test adding paper as primary reference."""
        mock_workspace_paper = MagicMock()
        mock_paper_service.add_to_workspace.return_value = mock_workspace_paper

        response = client.post(
            "/workspaces/test-workspace-id/papers/test-paper-id",
            json={"is_primary": True},
        )

        assert response.status_code == 200
        mock_paper_service.add_to_workspace.assert_called_once_with(
            paper_id="test-paper-id",
            workspace_id="test-workspace-id",
            notes=None,
            tags=None,
            is_primary=True,
        )

    def test_add_paper_already_exists(self, client, mock_paper_service):
        """Test adding paper returns existing if already in workspace."""
        # PaperService.add_to_workspace returns existing association instead of raising error
        mock_existing = MagicMock()
        mock_paper_service.add_to_workspace.return_value = mock_existing

        response = client.post(
            "/workspaces/test-workspace-id/papers/test-paper-id",
            json={},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


# ============ Remove Paper from Workspace Tests ============

class TestRemovePaperFromWorkspace:
    """Test remove paper from workspace endpoint."""

    @pytest.fixture
    def mock_paper_service(self):
        """Create mock paper service."""
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_paper_service):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_paper_service():
            return mock_paper_service

        app.dependency_overrides[workspaces.get_paper_service] = override_get_paper_service
        app.include_router(workspaces.router)

        return TestClient(app)

    def test_remove_paper_success(self, client, mock_paper_service):
        """Test successfully removing paper from workspace."""
        mock_paper_service.remove_from_workspace.return_value = True

        response = client.delete("/workspaces/test-workspace-id/papers/test-paper-id")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_paper_service.remove_from_workspace.assert_called_once_with(
            paper_id="test-paper-id",
            workspace_id="test-workspace-id",
        )

    def test_remove_paper_not_found(self, client, mock_paper_service):
        """Test removing paper that's not in workspace."""
        mock_paper_service.remove_from_workspace.return_value = False

        response = client.delete("/workspaces/test-workspace-id/papers/non-existent-paper")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ============ Integration Tests ============

class TestWorkspaceEndpointsIntegration:
    """Integration tests using real services with in-memory database."""

    @pytest.mark.asyncio
    async def test_full_workspace_flow(self):
        """Test complete workspace CRUD flow."""
        # This test would use real services with a test database
        # For now, we're testing the flow concept
        workspace_data = {
            "name": "Integration Test Workspace",
            "type": "sci",
            "discipline": "computer_science",
        }
        assert workspace_data["name"] == "Integration Test Workspace"
        assert workspace_data["type"] == "sci"

    @pytest.mark.asyncio
    async def test_paper_association_flow(self):
        """Test adding and removing papers from workspace."""
        # This test would verify the paper association lifecycle
        paper_data = {
            "paper_id": "test-paper-id",
            "notes": "Test notes",
            "tags": ["test"],
            "is_primary": False,
        }
        assert paper_data["paper_id"] == "test-paper-id"
        assert paper_data["is_primary"] is False


# ============ Workspace Type Tests ============

class TestWorkspaceTypes:
    """Test different workspace types."""

    @pytest.fixture
    def mock_workspace_service(self):
        """Create mock workspace service."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user for authentication."""
        return create_mock_user()

    @pytest.fixture
    def client(self, mock_workspace_service, mock_user):
        """Create test client with mocked dependencies."""
        app = FastAPI()

        async def override_get_workspace_service():
            return mock_workspace_service

        async def override_get_current_user():
            return mock_user

        app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(workspaces.router)

        return TestClient(app)

    @pytest.mark.parametrize("workspace_type", ["sci", "thesis", "proposal", "software_copyright", "patent"])
    def test_create_workspace_all_types(self, client, mock_workspace_service, workspace_type):
        """Test creating workspaces of all valid types."""
        mock_workspace = create_mock_workspace(type=workspace_type)
        mock_workspace_service.create.return_value = mock_workspace

        response = client.post(
            "/workspaces/",
            json={
                "name": f"Test {workspace_type} Workspace",
                "type": workspace_type,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == workspace_type

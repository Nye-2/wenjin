"""Integration tests for workspace flow.

Tests the complete workspace management flow including:
- Workspace creation
- Workspace listing
- Workspace retrieval
- Workspace update
- Workspace deletion
"""

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    FixtureUser,
    FixtureWorkspace,
    make_authenticated_client,
)


class TestWorkspaceFlow:
    """Tests for complete workspace flow."""

    @pytest.mark.asyncio
    async def test_create_list_update_delete_workspace(
        self, authenticated_client: AsyncClient, test_user: FixtureUser
    ):
        """Test complete CRUD flow for workspaces."""
        # 1. Create workspace
        response = await authenticated_client.post(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
            json={
                "name": "My Research Project",
                "type": "sci",
                "discipline": "computer_science",
                "description": "A workspace for my research project",
                "config": {"setting1": "value1"},
            },
        )
        assert response.status_code == 201
        workspace = response.json()
        assert workspace["name"] == "My Research Project"
        assert workspace["type"] == "sci"
        assert workspace["discipline"] == "computer_science"
        assert workspace["description"] == "A workspace for my research project"
        assert workspace["config"] == {"setting1": "value1"}
        workspace_id = workspace["id"]

        # 2. List workspaces - should see it
        response = await authenticated_client.get(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
        )
        assert response.status_code == 200
        workspaces = response.json()
        assert len(workspaces) >= 1
        found = any(w["id"] == workspace_id for w in workspaces)
        assert found

        # 3. Get workspace by ID
        response = await authenticated_client.get(f"/api/workspaces/{workspace_id}")
        assert response.status_code == 200
        workspace = response.json()
        assert workspace["id"] == workspace_id
        assert workspace["name"] == "My Research Project"

        # 4. Update workspace
        response = await authenticated_client.put(
            f"/api/workspaces/{workspace_id}",
            json={
                "name": "Updated Research Project",
                "description": "Updated description",
            },
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["name"] == "Updated Research Project"
        assert updated["description"] == "Updated description"
        # Unchanged fields should remain
        assert updated["discipline"] == "computer_science"

        # 5. Delete workspace
        response = await authenticated_client.delete(f"/api/workspaces/{workspace_id}")
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

        # 6. Verify deleted - should get 404
        response = await authenticated_client.get(f"/api/workspaces/{workspace_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_workspace_all_types(self, authenticated_client: AsyncClient, test_user: FixtureUser):
        """Test creating workspaces of all valid types."""
        valid_types = [
            "sci",
            "thesis",
            "proposal",
            "software_copyright",
            "patent",
        ]

        for ws_type in valid_types:
            response = await authenticated_client.post(
                "/api/workspaces",
                params={"user_id": str(test_user.id)},
                json={
                    "name": f"Test {ws_type} Workspace",
                    "type": ws_type,
                },
            )
            assert response.status_code == 201, f"Failed to create {ws_type} workspace"
            workspace = response.json()
            assert workspace["type"] == ws_type

    @pytest.mark.asyncio
    async def test_create_workspace_invalid_type(
        self, authenticated_client: AsyncClient, test_user: FixtureUser
    ):
        """Test that creating workspace with invalid type fails."""
        response = await authenticated_client.post(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
            json={
                "name": "Invalid Type Workspace",
                "type": "invalid_type",
            },
        )
        assert response.status_code == 400
        error = response.json()
        assert "invalid" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_workspace_missing_name(
        self, authenticated_client: AsyncClient, test_user: FixtureUser
    ):
        """Test that creating workspace without name fails."""
        response = await authenticated_client.post(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
            json={
                "type": "sci",
            },
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_list_workspaces_empty_for_new_user(
        self, client: AsyncClient
    ):
        """Test that listing workspaces for user with no workspaces returns empty list."""
        # Register a new user
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "nowsuser@example.com",
                "password": "testpassword123",
                "name": "No Workspace User",
            },
        )
        assert response.status_code == 201
        tokens = response.json()
        auth_client = make_authenticated_client(client, tokens["access_token"])

        # Get user info
        user_response = await auth_client.get("/api/auth/me")
        user_id = user_response.json()["id"]

        # List workspaces
        response = await auth_client.get(
            "/api/workspaces",
            params={"user_id": user_id},
        )
        assert response.status_code == 200
        workspaces = response.json()
        assert workspaces == []

    @pytest.mark.asyncio
    async def test_list_workspaces_only_shows_own_workspaces(
        self,
        client: AsyncClient,
        test_user: FixtureUser,
        test_session,
    ):
        """Test that listing workspaces only shows user's own workspaces."""
        from src.services.auth import hash_password
        from tests.integration.conftest import FixtureUser

        # Create another user
        other_user = FixtureUser(
            email="otheruser@example.com",
            name="Other User",
            hashed_password=hash_password("otherpassword123"),
            is_active=True,
            is_superuser=False,
        )
        test_session.add(other_user)
        await test_session.commit()
        await test_session.refresh(other_user)

        # Login as first user
        response = await client.post(
            "/api/auth/login",
            json={
                "email": test_user.email,
                "password": "testpassword123",
            },
        )
        tokens = response.json()
        auth_client = make_authenticated_client(client, tokens["access_token"])

        # Create workspace for first user
        await auth_client.post(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
            json={
                "name": "First User Workspace",
                "type": "sci",
            },
        )

        # Create workspace for second user (using first user's client - shouldn't matter)
        await auth_client.post(
            "/api/workspaces",
            params={"user_id": str(other_user.id)},
            json={
                "name": "Other User Workspace",
                "type": "thesis",
            },
        )

        # List workspaces for first user
        response = await auth_client.get(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
        )
        workspaces = response.json()
        # Should only see own workspaces
        assert all(w["user_id"] == str(test_user.id) for w in workspaces)

    @pytest.mark.asyncio
    async def test_update_nonexistent_workspace(self, authenticated_client: AsyncClient):
        """Test that updating nonexistent workspace returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.put(
            f"/api/workspaces/{fake_id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_workspace(self, authenticated_client: AsyncClient):
        """Test that deleting nonexistent workspace returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.delete(f"/api/workspaces/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_workspace_partial(
        self, authenticated_client: AsyncClient, test_user: FixtureUser, test_workspace: FixtureWorkspace
    ):
        """Test partial update of workspace."""
        original_name = test_workspace.name
        original_discipline = test_workspace.discipline

        # Update only description
        response = await authenticated_client.put(
            f"/api/workspaces/{test_workspace.id}",
            json={"description": "New description only"},
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["description"] == "New description only"
        # Other fields should remain unchanged
        assert updated["name"] == original_name
        assert updated["discipline"] == original_discipline

    @pytest.mark.asyncio
    async def test_update_workspace_config(
        self, authenticated_client: AsyncClient, test_user: FixtureUser, test_workspace: FixtureWorkspace
    ):
        """Test updating workspace config."""
        new_config = {
            "llm_model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 2000,
        }
        response = await authenticated_client.put(
            f"/api/workspaces/{test_workspace.id}",
            json={"config": new_config},
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["config"] == new_config

    @pytest.mark.asyncio
    async def test_workspace_response_format(
        self, authenticated_client: AsyncClient, test_user: FixtureUser
    ):
        """Test that workspace response has all expected fields."""
        response = await authenticated_client.post(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
            json={
                "name": "Format Test Workspace",
                "type": "thesis",
                "discipline": "biology",
                "description": "Testing response format",
            },
        )
        assert response.status_code == 201
        workspace = response.json()

        # Check all expected fields
        assert "id" in workspace
        assert "user_id" in workspace
        assert "name" in workspace
        assert "type" in workspace
        assert "discipline" in workspace
        assert "description" in workspace
        assert "config" in workspace

        # Check field values
        assert workspace["name"] == "Format Test Workspace"
        assert workspace["type"] == "thesis"
        assert workspace["discipline"] == "biology"
        assert workspace["user_id"] == str(test_user.id)


class TestWorkspacePaperAssociation:
    """Tests for workspace-paper associations."""

    @pytest.mark.asyncio
    async def test_add_paper_to_workspace(
        self,
        authenticated_client: AsyncClient,
        test_workspace: FixtureWorkspace,
        test_paper,
    ):
        """Test adding a paper to a workspace."""
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/papers/{test_paper.id}",
            json={
                "notes": "This is an important paper",
                "tags": ["important", "reference"],
                "is_primary": True,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["paper_id"] == test_paper.id

    @pytest.mark.asyncio
    async def test_list_workspace_papers(
        self,
        authenticated_client: AsyncClient,
        test_workspace: FixtureWorkspace,
        test_workspace_paper,
    ):
        """Test listing papers in a workspace."""
        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/papers"
        )
        assert response.status_code == 200
        papers = response.json()["papers"]
        assert len(papers) >= 1
        paper_ids = [p["id"] for p in papers]
        assert test_workspace_paper.paper_id in paper_ids

    @pytest.mark.asyncio
    async def test_remove_paper_from_workspace(
        self,
        authenticated_client: AsyncClient,
        test_workspace: FixtureWorkspace,
        test_paper,
        test_workspace_paper,
    ):
        """Test removing a paper from a workspace."""
        response = await authenticated_client.delete(
            f"/api/workspaces/{test_workspace.id}/papers/{test_paper.id}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

        # Verify paper is removed
        response = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/papers"
        )
        papers = response.json()["papers"]
        paper_ids = [p["id"] for p in papers]
        assert test_paper.id not in paper_ids

    @pytest.mark.asyncio
    async def test_remove_nonexistent_paper_from_workspace(
        self, authenticated_client: AsyncClient, test_workspace: FixtureWorkspace
    ):
        """Test removing a paper that's not in the workspace."""
        import uuid
        fake_paper_id = str(uuid.uuid4())
        response = await authenticated_client.delete(
            f"/api/workspaces/{test_workspace.id}/papers/{fake_paper_id}"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_same_paper_twice_fails(
        self,
        authenticated_client: AsyncClient,
        test_workspace: FixtureWorkspace,
        test_paper,
        test_workspace_paper,
    ):
        """Test that adding the same paper twice fails."""
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/papers/{test_paper.id}",
            json={},
        )
        assert response.status_code == 400
        error = response.json()
        assert "already" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_papers_empty_workspace(
        self, authenticated_client: AsyncClient, test_user: FixtureUser
    ):
        """Test listing papers in workspace with no papers."""
        # Create empty workspace
        response = await authenticated_client.post(
            "/api/workspaces",
            params={"user_id": str(test_user.id)},
            json={
                "name": "Empty Workspace",
                "type": "sci",
            },
        )
        workspace_id = response.json()["id"]

        response = await authenticated_client.get(
            f"/api/workspaces/{workspace_id}/papers"
        )
        assert response.status_code == 200
        assert response.json() == {"papers": [], "count": 0}

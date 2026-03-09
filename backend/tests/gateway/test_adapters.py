"""Tests for frontend API adapters."""

import pytest

from src.gateway.adapters.skill_adapter import SkillAdapter
from src.gateway.adapters.workspace_adapter import WorkspaceAdapter


class TestSkillAdapter:
    """Tests for SkillAdapter class."""

    @pytest.fixture
    def adapter(self):
        """Create a SkillAdapter instance for testing."""
        return SkillAdapter()

    @pytest.mark.asyncio
    async def test_list_skills(self, adapter):
        """Should list available skills."""
        skills = await adapter.list_skills()
        assert isinstance(skills, list)
        assert len(skills) >= 8  # At least 8 academic skills

    @pytest.mark.asyncio
    async def test_get_skill(self, adapter):
        """Should get a specific skill by name."""
        skill = await adapter.get_skill("deep-research")
        assert skill is not None
        assert skill["name"] == "deep-research"

    @pytest.mark.asyncio
    async def test_get_nonexistent_skill(self, adapter):
        """Should return None for nonexistent skill."""
        skill = await adapter.get_skill("nonexistent")
        assert skill is None

    @pytest.mark.asyncio
    async def test_skill_has_required_fields(self, adapter):
        """Skills should have required fields."""
        skills = await adapter.list_skills()
        for skill in skills:
            assert "name" in skill
            assert "description" in skill

    @pytest.mark.asyncio
    async def test_skill_includes_additional_metadata(self, adapter):
        """Skills should include additional metadata fields."""
        skills = await adapter.list_skills()
        for skill in skills:
            assert "license" in skill
            assert "enabled" in skill
            assert "allowed_tools" in skill

    @pytest.mark.asyncio
    async def test_get_skill_includes_content(self, adapter):
        """Getting a specific skill should include its content."""
        skill = await adapter.get_skill("deep-research")
        assert skill is not None
        assert "content" in skill
        assert isinstance(skill["content"], str)
        assert len(skill["content"]) > 0


class TestWorkspaceAdapter:
    """Tests for WorkspaceAdapter class."""

    @pytest.fixture
    def adapter(self):
        """Create a WorkspaceAdapter instance for testing."""
        return WorkspaceAdapter()

    @pytest.mark.asyncio
    async def test_list_workspaces(self, adapter):
        """Should list workspaces."""
        workspaces = await adapter.list_workspaces(user_id="test-user")
        assert isinstance(workspaces, list)

    @pytest.mark.asyncio
    async def test_create_workspace(self, adapter):
        """Should create a workspace."""
        workspace = await adapter.create_workspace(
            user_id="test-user",
            name="Test Workspace",
            paper_type="research_article",
        )
        assert workspace is not None
        assert workspace["name"] == "Test Workspace"

    @pytest.mark.asyncio
    async def test_get_workspace(self, adapter):
        """Should get workspace by ID."""
        # Create first
        created = await adapter.create_workspace(
            user_id="test-user",
            name="Test",
            paper_type="research_article",
        )
        # Then get
        workspace = await adapter.get_workspace(created["id"])
        assert workspace is not None

    @pytest.mark.asyncio
    async def test_get_nonexistent_workspace(self, adapter):
        """Should return None for nonexistent workspace."""
        workspace = await adapter.get_workspace("nonexistent-id")
        assert workspace is None

    @pytest.mark.asyncio
    async def test_list_workspaces_filters_by_user(self, adapter):
        """Should only list workspaces for the specified user."""
        # Create workspaces for different users
        await adapter.create_workspace(
            user_id="user-1",
            name="Workspace 1",
            paper_type="research_article",
        )
        await adapter.create_workspace(
            user_id="user-2",
            name="Workspace 2",
            paper_type="thesis",
        )
        await adapter.create_workspace(
            user_id="user-1",
            name="Workspace 3",
            paper_type="proposal",
        )

        # List workspaces for user-1
        user1_workspaces = await adapter.list_workspaces(user_id="user-1")
        assert len(user1_workspaces) == 2
        names = {ws["name"] for ws in user1_workspaces}
        assert names == {"Workspace 1", "Workspace 3"}

        # List workspaces for user-2
        user2_workspaces = await adapter.list_workspaces(user_id="user-2")
        assert len(user2_workspaces) == 1
        assert user2_workspaces[0]["name"] == "Workspace 2"

    @pytest.mark.asyncio
    async def test_create_workspace_with_optional_fields(self, adapter):
        """Should create workspace with optional fields."""
        workspace = await adapter.create_workspace(
            user_id="test-user",
            name="Full Workspace",
            paper_type="thesis",
            description="A test thesis workspace",
            config={"field": "computer_science"},
        )
        assert workspace is not None
        assert workspace["name"] == "Full Workspace"
        assert workspace["type"] == "thesis"
        assert workspace["description"] == "A test thesis workspace"
        assert workspace["config"] == {"field": "computer_science"}

    @pytest.mark.asyncio
    async def test_created_workspace_has_id(self, adapter):
        """Created workspace should have a unique ID."""
        workspace = await adapter.create_workspace(
            user_id="test-user",
            name="Test",
            paper_type="research_article",
        )
        assert "id" in workspace
        assert isinstance(workspace["id"], str)
        assert len(workspace["id"]) > 0

    @pytest.mark.asyncio
    async def test_get_workspace_returns_full_data(self, adapter):
        """Getting a workspace should return all data."""
        created = await adapter.create_workspace(
            user_id="test-user",
            name="Full Test",
            paper_type="grant",
            description="Test description",
            config={"key": "value"},
        )

        retrieved = await adapter.get_workspace(created["id"])
        assert retrieved is not None
        assert retrieved["id"] == created["id"]
        assert retrieved["user_id"] == "test-user"
        assert retrieved["name"] == "Full Test"
        assert retrieved["type"] == "grant"
        assert retrieved["description"] == "Test description"
        assert retrieved["config"] == {"key": "value"}

"""Tests for workspace service.

This module contains comprehensive tests for the WorkspaceService class,
covering all CRUD operations and paper association management.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.services.workspace_service import WorkspaceService
from src.database import Workspace, WorkspacePaper, WorkspaceType


class TestWorkspaceServiceInit:
    """Tests for WorkspaceService initialization."""

    def test_init_with_db_session(self):
        """Test that WorkspaceService initializes with a database session."""
        mock_db = AsyncMock()
        service = WorkspaceService(mock_db)
        assert service.db == mock_db


class TestCreateWorkspace:
    """Tests for create method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_user_id(self):
        """Sample user UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_workspace_with_required_fields(
        self, service, mock_db_session, sample_user_id
    ):
        """Test creating a workspace with only required fields."""
        await service.create(
            user_id=sample_user_id,
            name="Test Workspace",
            type="sci",
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Verify the workspace object passed to add
        added_workspace = mock_db_session.add.call_args[0][0]
        assert added_workspace.user_id == sample_user_id
        assert added_workspace.name == "Test Workspace"
        assert added_workspace.type == WorkspaceType.SCI

    @pytest.mark.asyncio
    async def test_create_workspace_with_all_fields(
        self, service, mock_db_session, sample_user_id
    ):
        """Test creating a workspace with all fields."""
        config = {"setting1": "value1"}
        await service.create(
            user_id=sample_user_id,
            name="Full Workspace",
            type="thesis",
            discipline="computer_science",
            description="A test workspace",
            config=config,
        )

        added_workspace = mock_db_session.add.call_args[0][0]
        assert added_workspace.user_id == sample_user_id
        assert added_workspace.name == "Full Workspace"
        assert added_workspace.type == WorkspaceType.THESIS
        assert added_workspace.discipline == "computer_science"
        assert added_workspace.description == "A test workspace"
        assert added_workspace.config == config

    @pytest.mark.asyncio
    async def test_create_workspace_with_enum_type(
        self, service, mock_db_session, sample_user_id
    ):
        """Test creating a workspace with WorkspaceType enum."""
        await service.create(
            user_id=sample_user_id,
            name="Enum Workspace",
            type=WorkspaceType.GRANT,
        )

        added_workspace = mock_db_session.add.call_args[0][0]
        assert added_workspace.type == WorkspaceType.GRANT

    @pytest.mark.asyncio
    async def test_create_workspace_with_invalid_type_raises_error(
        self, service, mock_db_session, sample_user_id
    ):
        """Test that creating a workspace with invalid type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await service.create(
                user_id=sample_user_id,
                name="Invalid Workspace",
                type="invalid_type",
            )

        assert "Invalid workspace type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_workspace_default_config(
        self, service, mock_db_session, sample_user_id
    ):
        """Test that config defaults to empty dict."""
        await service.create(
            user_id=sample_user_id,
            name="Default Config Workspace",
            type="proposal",
        )

        added_workspace = mock_db_session.add.call_args[0][0]
        assert added_workspace.config == {}


class TestGetWorkspace:
    """Tests for get method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_workspace_found(self, service, mock_db_session, sample_workspace_id):
        """Test getting an existing workspace."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = sample_workspace_id
        mock_workspace.name = "Test Workspace"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workspace
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get(sample_workspace_id)

        assert result == mock_workspace
        assert result.id == sample_workspace_id

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(self, service, mock_db_session):
        """Test getting a non-existent workspace."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get("non-existent-id")

        assert result is None


class TestListByUser:
    """Tests for list_by_user method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_user_id(self):
        """Sample user UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_by_user_returns_workspaces(
        self, service, mock_db_session, sample_user_id
    ):
        """Test listing workspaces for a user."""
        mock_workspace1 = MagicMock(spec=Workspace)
        mock_workspace2 = MagicMock(spec=Workspace)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_workspace1,
            mock_workspace2,
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.list_by_user(sample_user_id)

        assert len(result) == 2
        assert result[0] == mock_workspace1
        assert result[1] == mock_workspace2

    @pytest.mark.asyncio
    async def test_list_by_user_empty(self, service, mock_db_session, sample_user_id):
        """Test listing workspaces when user has none."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.list_by_user(sample_user_id)

        assert result == []


class TestUpdateWorkspace:
    """Tests for update method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_workspace_name(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test updating workspace name."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = sample_workspace_id
        mock_workspace.name = "Old Name"

        with patch.object(service, "get", return_value=mock_workspace):
            await service.update(sample_workspace_id, name="New Name")

        assert mock_workspace.name == "New Name"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workspace_multiple_fields(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test updating multiple workspace fields."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.name = "Old Name"
        mock_workspace.discipline = "old_discipline"
        mock_workspace.description = "Old description"

        with patch.object(service, "get", return_value=mock_workspace):
            await service.update(
                sample_workspace_id,
                name="New Name",
                discipline="new_discipline",
                description="New description",
            )

        assert mock_workspace.name == "New Name"
        assert mock_workspace.discipline == "new_discipline"
        assert mock_workspace.description == "New description"

    @pytest.mark.asyncio
    async def test_update_workspace_with_type_string(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test updating workspace type with string value."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.type = WorkspaceType.SCI

        with patch.object(service, "get", return_value=mock_workspace):
            await service.update(sample_workspace_id, type="thesis")

        assert mock_workspace.type == WorkspaceType.THESIS

    @pytest.mark.asyncio
    async def test_update_workspace_invalid_type_raises_error(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test that updating with invalid type raises ValueError."""
        mock_workspace = MagicMock(spec=Workspace)

        with patch.object(service, "get", return_value=mock_workspace):
            with pytest.raises(ValueError) as exc_info:
                await service.update(sample_workspace_id, type="invalid_type")

        assert "Invalid workspace type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_workspace_not_found(self, service, mock_db_session):
        """Test updating a non-existent workspace."""
        with patch.object(service, "get", return_value=None):
            result = await service.update("non-existent-id", name="New Name")

        assert result is None
        mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_workspace_config(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test updating workspace config."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.config = {}

        new_config = {"setting1": "value1", "setting2": "value2"}

        with patch.object(service, "get", return_value=mock_workspace):
            await service.update(sample_workspace_id, config=new_config)

        assert mock_workspace.config == new_config


class TestDeleteWorkspace:
    """Tests for delete method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_delete_workspace_found(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test deleting an existing workspace."""
        mock_workspace = MagicMock(spec=Workspace)
        mock_workspace.id = sample_workspace_id

        with patch.object(service, "get", return_value=mock_workspace):
            result = await service.delete(sample_workspace_id)

        assert result is True
        mock_db_session.delete.assert_called_once_with(mock_workspace)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_workspace_not_found(self, service, mock_db_session):
        """Test deleting a non-existent workspace."""
        with patch.object(service, "get", return_value=None):
            result = await service.delete("non-existent-id")

        assert result is False
        mock_db_session.delete.assert_not_called()


class TestAddPaper:
    """Tests for add_paper method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_add_paper_basic(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test adding a paper to a workspace with minimal args."""
        with patch.object(
            service, "_get_workspace_paper", return_value=None
        ):
            await service.add_paper(sample_workspace_id, sample_paper_id)

        mock_db_session.add.assert_called_once()
        added_wp = mock_db_session.add.call_args[0][0]
        assert added_wp.workspace_id == sample_workspace_id
        assert added_wp.paper_id == sample_paper_id
        assert added_wp.tags == []
        assert added_wp.is_primary is False
        assert added_wp.read_status == "unread"

    @pytest.mark.asyncio
    async def test_add_paper_with_all_options(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test adding a paper with all options."""
        with patch.object(
            service, "_get_workspace_paper", return_value=None
        ):
            await service.add_paper(
                sample_workspace_id,
                sample_paper_id,
                notes="Important reference",
                tags=["primary", "methodology"],
                is_primary=True,
                read_status="reading",
            )

        added_wp = mock_db_session.add.call_args[0][0]
        assert added_wp.notes == "Important reference"
        assert added_wp.tags == ["primary", "methodology"]
        assert added_wp.is_primary is True
        assert added_wp.read_status == "reading"

    @pytest.mark.asyncio
    async def test_add_paper_already_exists_raises_error(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test that adding duplicate paper raises ValueError."""
        existing_wp = MagicMock(spec=WorkspacePaper)

        with patch.object(
            service, "_get_workspace_paper", return_value=existing_wp
        ):
            with pytest.raises(ValueError) as exc_info:
                await service.add_paper(sample_workspace_id, sample_paper_id)

        assert "already in workspace" in str(exc_info.value)
        mock_db_session.add.assert_not_called()


class TestRemovePaper:
    """Tests for remove_paper method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_remove_paper_found(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test removing an existing paper from workspace."""
        mock_wp = MagicMock(spec=WorkspacePaper)
        mock_wp.workspace_id = sample_workspace_id
        mock_wp.paper_id = sample_paper_id

        with patch.object(
            service, "_get_workspace_paper", return_value=mock_wp
        ):
            result = await service.remove_paper(sample_workspace_id, sample_paper_id)

        assert result is True
        mock_db_session.delete.assert_called_once_with(mock_wp)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_paper_not_found(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test removing a non-existent paper from workspace."""
        with patch.object(
            service, "_get_workspace_paper", return_value=None
        ):
            result = await service.remove_paper(sample_workspace_id, sample_paper_id)

        assert result is False
        mock_db_session.delete.assert_not_called()


class TestGetWorkspacePaper:
    """Tests for _get_workspace_paper helper method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_workspace_paper_found(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test getting existing WorkspacePaper association."""
        mock_wp = MagicMock(spec=WorkspacePaper)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service._get_workspace_paper(
            sample_workspace_id, sample_paper_id
        )

        assert result == mock_wp

    @pytest.mark.asyncio
    async def test_get_workspace_paper_not_found(
        self, service, mock_db_session, sample_workspace_id, sample_paper_id
    ):
        """Test getting non-existent WorkspacePaper association."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service._get_workspace_paper(
            sample_workspace_id, sample_paper_id
        )

        assert result is None


class TestWorkspaceTypeValidation:
    """Tests for workspace type validation across methods."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkspaceService instance."""
        return WorkspaceService(mock_db_session)

    @pytest.fixture
    def sample_user_id(self):
        """Sample user UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_all_valid_workspace_types(self, service, mock_db_session, sample_user_id):
        """Test that all valid workspace types are accepted."""
        valid_types = ["sci", "thesis", "proposal", "grant", "literature_review"]

        for type_value in valid_types:
            mock_db_session.add.reset_mock()

            await service.create(
                user_id=sample_user_id,
                name=f"Workspace {type_value}",
                type=type_value,
            )

            added_workspace = mock_db_session.add.call_args[0][0]
            assert added_workspace.type.value == type_value

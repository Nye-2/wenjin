"""Tests for paper service.

This module contains comprehensive tests for the PaperService class,
covering all CRUD operations, search functionality, and workspace association management.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.services.paper_service import PaperService
from src.database import Paper, PaperExtraction, WorkspacePaper


class TestPaperServiceInit:
    """Tests for PaperService initialization."""

    def test_init_with_db_session(self):
        """Test that PaperService initializes with a database session."""
        mock_db = AsyncMock()
        service = PaperService(mock_db)
        assert service.db == mock_db


class TestCreatePaper:
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
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.mark.asyncio
    async def test_create_paper_with_required_fields(self, service, mock_db_session):
        """Test creating a paper with only required fields."""
        authors = [{"name": "John Doe"}, {"name": "Jane Smith"}]

        await service.create(
            title="Test Paper",
            authors=authors,
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Verify the paper object passed to add
        added_paper = mock_db_session.add.call_args[0][0]
        assert added_paper.title == "Test Paper"
        assert added_paper.authors == authors
        assert added_paper.source == "manual_upload"

    @pytest.mark.asyncio
    async def test_create_paper_with_all_fields(self, service, mock_db_session):
        """Test creating a paper with all fields."""
        authors = [{"name": "John Doe", "affiliation": "MIT"}]

        # Mock get_by_doi to return None (DOI doesn't exist yet)
        with patch.object(service, "get_by_doi", return_value=None):
            await service.create(
                title="Full Paper",
                authors=authors,
                doi="10.1234/test.5678",
                year=2024,
                venue="NeurIPS",
                abstract="This is a test abstract.",
                source="semantic_scholar",
            )

        added_paper = mock_db_session.add.call_args[0][0]
        assert added_paper.title == "Full Paper"
        assert added_paper.authors == authors
        assert added_paper.doi == "10.1234/test.5678"
        assert added_paper.year == 2024
        assert added_paper.venue == "NeurIPS"
        assert added_paper.abstract == "This is a test abstract."
        assert added_paper.source == "semantic_scholar"

    @pytest.mark.asyncio
    async def test_create_paper_with_existing_doi_returns_existing(
        self, service, mock_db_session
    ):
        """Test that creating with existing DOI returns existing paper."""
        existing_paper = MagicMock(spec=Paper)
        existing_paper.doi = "10.1234/existing"

        with patch.object(service, "get_by_doi", return_value=existing_paper):
            result = await service.create(
                title="New Title",
                authors=[{"name": "Author"}],
                doi="10.1234/existing",
            )

        assert result == existing_paper
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_paper_default_source(self, service, mock_db_session):
        """Test that source defaults to manual_upload."""
        await service.create(
            title="Test Paper",
            authors=[],
        )

        added_paper = mock_db_session.add.call_args[0][0]
        assert added_paper.source == "manual_upload"

    @pytest.mark.asyncio
    async def test_create_in_workspace_is_atomic(self, service, mock_db_session):
        """Creating in workspace should commit once after paper + association are staged."""
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        paper = await service.create_in_workspace(
            workspace_id=str(uuid.uuid4()),
            title="Atomic Paper",
            authors=[],
        )

        assert paper is not None
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()


class TestGetPaper:
    """Tests for get method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_paper_found(self, service, mock_db_session, sample_paper_id):
        """Test getting an existing paper."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.id = sample_paper_id
        mock_paper.title = "Test Paper"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get(sample_paper_id)

        assert result == mock_paper
        assert result.id == sample_paper_id

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self, service, mock_db_session):
        """Test getting a non-existent paper."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get("non-existent-id")

        assert result is None


class TestGetByDOI:
    """Tests for get_by_doi method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.mark.asyncio
    async def test_get_by_doi_found(self, service, mock_db_session):
        """Test getting an existing paper by DOI."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.doi = "10.1234/test"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_by_doi("10.1234/test")

        assert result == mock_paper
        assert result.doi == "10.1234/test"

    @pytest.mark.asyncio
    async def test_get_by_doi_not_found(self, service, mock_db_session):
        """Test getting a paper with non-existent DOI."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_by_doi("10.1234/nonexistent")

        assert result is None


class TestUpdatePaper:
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
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_paper_title(self, service, mock_db_session, sample_paper_id):
        """Test updating paper title."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.id = sample_paper_id
        mock_paper.title = "Old Title"

        with patch.object(service, "get", return_value=mock_paper):
            await service.update(sample_paper_id, title="New Title")

        assert mock_paper.title == "New Title"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_paper_multiple_fields(
        self, service, mock_db_session, sample_paper_id
    ):
        """Test updating multiple paper fields."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.title = "Old Title"
        mock_paper.year = 2020
        mock_paper.venue = "Old Venue"

        with patch.object(service, "get", return_value=mock_paper):
            await service.update(
                sample_paper_id,
                title="New Title",
                year=2024,
                venue="New Venue",
            )

        assert mock_paper.title == "New Title"
        assert mock_paper.year == 2024
        assert mock_paper.venue == "New Venue"

    @pytest.mark.asyncio
    async def test_update_paper_not_found(self, service, mock_db_session):
        """Test updating a non-existent paper."""
        with patch.object(service, "get", return_value=None):
            result = await service.update("non-existent-id", title="New Title")

        assert result is None
        mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_paper_skips_none_values(
        self, service, mock_db_session, sample_paper_id
    ):
        """Test that update skips None values."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.title = "Existing Title"
        mock_paper.year = 2020

        with patch.object(service, "get", return_value=mock_paper):
            await service.update(
                sample_paper_id,
                title=None,
                year=2024,
            )

        # Title should not be updated since it's None
        assert mock_paper.year == 2024


class TestDeletePaper:
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
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_delete_paper_found(self, service, mock_db_session, sample_paper_id):
        """Test deleting an existing paper."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.id = sample_paper_id

        with patch.object(service, "get", return_value=mock_paper):
            result = await service.delete(sample_paper_id)

        assert result is True
        mock_db_session.delete.assert_called_once_with(mock_paper)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_paper_not_found(self, service, mock_db_session):
        """Test deleting a non-existent paper."""
        with patch.object(service, "get", return_value=None):
            result = await service.delete("non-existent-id")

        assert result is False
        mock_db_session.delete.assert_not_called()


class TestSearchPapers:
    """Tests for search method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_search_papers_global(self, service, mock_db_session):
        """Test searching papers globally (no workspace filter)."""
        mock_paper1 = MagicMock(spec=Paper)
        mock_paper2 = MagicMock(spec=Paper)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_paper1,
            mock_paper2,
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.search("machine learning")

        assert len(result) == 2
        assert result[0] == mock_paper1
        assert result[1] == mock_paper2

    @pytest.mark.asyncio
    async def test_search_papers_in_workspace(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test searching papers within a specific workspace."""
        mock_paper = MagicMock(spec=Paper)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.search(
            query="deep learning",
            workspace_id=sample_workspace_id,
        )

        assert len(result) == 1
        assert result[0] == mock_paper

    @pytest.mark.asyncio
    async def test_search_papers_with_limit(self, service, mock_db_session):
        """Test searching papers with custom limit."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.search("test query", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_search_papers_empty_results(self, service, mock_db_session):
        """Test searching with no matching papers."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.search("nonexistent paper xyz123")

        assert result == []


class TestAddToWorkspace:
    """Tests for add_to_workspace method."""

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
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_add_to_workspace_basic(
        self, service, mock_db_session, sample_paper_id, sample_workspace_id
    ):
        """Test adding a paper to workspace with minimal args."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        await service.add_to_workspace(sample_paper_id, sample_workspace_id)

        mock_db_session.add.assert_called_once()
        added_wp = mock_db_session.add.call_args[0][0]
        assert added_wp.workspace_id == sample_workspace_id
        assert added_wp.paper_id == sample_paper_id
        assert added_wp.tags == []
        assert added_wp.is_primary is False

    @pytest.mark.asyncio
    async def test_add_to_workspace_with_all_options(
        self, service, mock_db_session, sample_paper_id, sample_workspace_id
    ):
        """Test adding a paper with all options."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        await service.add_to_workspace(
            sample_paper_id,
            sample_workspace_id,
            notes="Important reference",
            tags=["primary", "methodology"],
            is_primary=True,
        )

        added_wp = mock_db_session.add.call_args[0][0]
        assert added_wp.notes == "Important reference"
        assert added_wp.tags == ["primary", "methodology"]
        assert added_wp.is_primary is True

    @pytest.mark.asyncio
    async def test_add_to_workspace_already_exists_returns_existing(
        self, service, mock_db_session, sample_paper_id, sample_workspace_id
    ):
        """Test that adding duplicate paper returns existing association."""
        existing_wp = MagicMock(spec=WorkspacePaper)
        existing_wp.paper_id = sample_paper_id
        existing_wp.workspace_id = sample_workspace_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_wp
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.add_to_workspace(sample_paper_id, sample_workspace_id)

        assert result == existing_wp
        mock_db_session.add.assert_not_called()


class TestRemoveFromWorkspace:
    """Tests for remove_from_workspace method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_remove_from_workspace_found(
        self, service, mock_db_session, sample_paper_id, sample_workspace_id
    ):
        """Test removing an existing paper from workspace."""
        mock_wp = MagicMock(spec=WorkspacePaper)
        mock_wp.workspace_id = sample_workspace_id
        mock_wp.paper_id = sample_paper_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.remove_from_workspace(
            sample_paper_id, sample_workspace_id
        )

        assert result is True
        mock_db_session.delete.assert_called_once_with(mock_wp)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_from_workspace_not_found(
        self, service, mock_db_session, sample_paper_id, sample_workspace_id
    ):
        """Test removing a non-existent paper from workspace."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.remove_from_workspace(
            sample_paper_id, sample_workspace_id
        )

        assert result is False
        mock_db_session.delete.assert_not_called()


class TestListWorkspacePapers:
    """Tests for list_workspace_papers method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_workspace_papers_returns_papers(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test listing papers in a workspace."""
        mock_paper1 = MagicMock(spec=Paper)
        mock_paper2 = MagicMock(spec=Paper)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_paper1,
            mock_paper2,
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.list_workspace_papers(sample_workspace_id)

        assert len(result) == 2
        assert result[0] == mock_paper1
        assert result[1] == mock_paper2

    @pytest.mark.asyncio
    async def test_list_workspace_papers_empty(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test listing papers when workspace has none."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.list_workspace_papers(sample_workspace_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_workspace_papers_with_read_status_filter(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test listing papers filtered by read status."""
        mock_paper = MagicMock(spec=Paper)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.list_workspace_papers(
            sample_workspace_id, read_status="read"
        )

        assert len(result) == 1


class TestStoreExtraction:
    """Tests for store_extraction method."""

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
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_store_extraction_tier1(
        self, service, mock_db_session, sample_paper_id
    ):
        """Test storing tier 1 extraction result."""
        structured_data = {"title": "Extracted Title", "sections": 5}

        await service.store_extraction(
            paper_id=sample_paper_id,
            tier=1,
            extraction_type="metadata",
            structured_data=structured_data,
            processing_time_ms=500,
        )

        mock_db_session.add.assert_called_once()
        added_extraction = mock_db_session.add.call_args[0][0]
        assert added_extraction.paper_id == sample_paper_id
        assert added_extraction.tier == 1
        assert added_extraction.extraction_type == "metadata"
        assert added_extraction.structured_data == structured_data
        assert added_extraction.processing_time_ms == 500

    @pytest.mark.asyncio
    async def test_store_extraction_tier2(
        self, service, mock_db_session, sample_paper_id
    ):
        """Test storing tier 2 extraction result with model info."""
        structured_data = {"summary": "This paper presents..."}

        await service.store_extraction(
            paper_id=sample_paper_id,
            tier=2,
            extraction_type="summary",
            structured_data=structured_data,
            processing_time_ms=2000,
            model_used="claude-3-haiku",
        )

        added_extraction = mock_db_session.add.call_args[0][0]
        assert added_extraction.tier == 2
        assert added_extraction.model_used == "claude-3-haiku"


class TestGetExtraction:
    """Tests for get_extraction method."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_paper_id(self):
        """Sample paper UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_extraction_found(self, service, mock_db_session, sample_paper_id):
        """Test getting an existing extraction."""
        mock_extraction = MagicMock(spec=PaperExtraction)
        mock_extraction.paper_id = sample_paper_id
        mock_extraction.tier = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_extraction(sample_paper_id)

        assert result == mock_extraction

    @pytest.mark.asyncio
    async def test_get_extraction_with_tier_filter(
        self, service, mock_db_session, sample_paper_id
    ):
        """Test getting extraction filtered by tier."""
        mock_extraction = MagicMock(spec=PaperExtraction)
        mock_extraction.tier = 2

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_extraction
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_extraction(sample_paper_id, tier=2)

        assert result == mock_extraction
        assert result.tier == 2

    @pytest.mark.asyncio
    async def test_get_extraction_not_found(
        self, service, mock_db_session, sample_paper_id
    ):
        """Test getting a non-existent extraction."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_extraction(sample_paper_id)

        assert result is None


class TestSearchInWorkspace:
    """Tests for search_in_workspace method (legacy method)."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create PaperService instance."""
        return PaperService(mock_db_session)

    @pytest.fixture
    def sample_workspace_id(self):
        """Sample workspace UUID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_search_in_workspace_returns_matching_papers(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test searching papers within workspace."""
        mock_paper = MagicMock(spec=Paper)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.search_in_workspace(
            workspace_id=sample_workspace_id,
            query="transformer",
        )

        assert len(result) == 1
        assert result[0] == mock_paper

    @pytest.mark.asyncio
    async def test_search_in_workspace_with_limit(
        self, service, mock_db_session, sample_workspace_id
    ):
        """Test searching papers with custom limit."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.search_in_workspace(
            workspace_id=sample_workspace_id,
            query="test",
            limit=5,
        )

        assert result == []

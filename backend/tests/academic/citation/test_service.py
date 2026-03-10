"""Tests for CitationService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.citation.service import CitationService
from src.database import Citation, CitationType


class TestCitationServiceInit:
    """Tests for CitationService initialization."""

    def test_init_with_db_session(self):
        """Test that CitationService initializes with database session."""
        mock_db = AsyncMock()
        service = CitationService(mock_db)
        assert service.db == mock_db


class TestAddCitation:
    """Tests for add_citation method."""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        return CitationService(mock_db_session)

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "cited_paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_add_citation_creates_citation(
        self, service, mock_db_session, sample_ids
    ):
        """Test that add_citation creates a Citation object."""
        result = await service.add_citation(**sample_ids)

        mock_db_session.add.assert_called_once()
        added_citation = mock_db_session.add.call_args[0][0]
        assert added_citation.paper_id == sample_ids["paper_id"]
        assert added_citation.cited_paper_id == sample_ids["cited_paper_id"]
        assert added_citation.workspace_id == sample_ids["workspace_id"]

    @pytest.mark.asyncio
    async def test_add_citation_with_context(
        self, service, mock_db_session, sample_ids
    ):
        """Test add_citation with optional context."""
        result = await service.add_citation(
            **sample_ids,
            citation_context="As shown by Smith et al.",
            section="Related Work",
        )

        added_citation = mock_db_session.add.call_args[0][0]
        assert added_citation.citation_context == "As shown by Smith et al."
        assert added_citation.section == "Related Work"


class TestGetCitations:
    """Tests for citation retrieval methods."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db_session):
        return CitationService(mock_db_session)

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_get_outgoing_citations(
        self, service, mock_db_session, sample_ids
    ):
        """Test getting papers cited by a paper."""
        mock_citation = MagicMock(spec=Citation)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_citation]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_outgoing_citations(**sample_ids)

        assert len(result) == 1
        assert result[0] == mock_citation

    @pytest.mark.asyncio
    async def test_get_incoming_citations(
        self, service, mock_db_session, sample_ids
    ):
        """Test getting papers that cite a paper."""
        mock_citation = MagicMock(spec=Citation)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_citation]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_incoming_citations(**sample_ids)

        assert len(result) == 1


class TestRemoveCitation:
    """Tests for remove_citation method."""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        return CitationService(mock_db_session)

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "cited_paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_remove_citation_found(
        self, service, mock_db_session, sample_ids
    ):
        """Test removing an existing citation."""
        mock_citation = MagicMock(spec=Citation)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_citation
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.remove_citation(**sample_ids)

        assert result is True
        mock_db_session.delete.assert_called_once_with(mock_citation)

    @pytest.mark.asyncio
    async def test_remove_citation_not_found(
        self, service, mock_db_session, sample_ids
    ):
        """Test removing a non-existent citation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.remove_citation(**sample_ids)

        assert result is False
        mock_db_session.delete.assert_not_called()

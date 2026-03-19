"""Tests for papers router.

This module tests the papers endpoints including:
- Paper creation
- Paper listing and filtering
- Paper retrieval
- Paper updates
- Paper deletion
- Paper extraction
- Paper sections retrieval
- Paper search
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.academic.services.extraction_service import ExtractionService
from src.academic.services.paper_service import PaperService
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.papers import (
    get_extraction_service,
    get_paper_service,
    get_workspace_service,
    paper_to_response,
    router,
    section_to_response,
)

# ============ Auth Mock ============

MOCK_USER_ID = "test-user-001"


def create_mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = MOCK_USER_ID
    user.email = "test@test.com"
    user.is_active = True
    return user


def create_mock_workspace(
    workspace_id: str = "ws-1",
    user_id: str = MOCK_USER_ID,
):
    workspace = MagicMock()
    workspace.id = workspace_id
    workspace.user_id = user_id
    return workspace


def create_mock_paper(
    id: str = None,
    title: str = "Test Paper Title",
    doi: str = "10.1234/test.5678",
    authors: list = None,
    year: int = 2024,
    venue: str = "Test Conference",
    abstract: str = "This is a test abstract for the paper.",
    file_path: str = None,
    source: str = "manual_upload",
    external_ids: dict = None,
    toc: list = None,
    citation_count: int = 10,
    reference_count: int = 20,
):
    """Create a mock paper object."""
    paper = MagicMock()
    paper.id = id or str(uuid4())
    paper.doi = doi
    paper.title = title
    paper.authors = authors or [{"name": "John Doe"}, {"name": "Jane Smith"}]
    paper.year = year
    paper.venue = venue
    paper.abstract = abstract
    paper.file_path = file_path
    paper.source = source
    paper.external_ids = external_ids or {}
    paper.toc = toc
    paper.citation_count = citation_count
    paper.reference_count = reference_count
    paper.created_at = datetime.now(UTC)
    paper.updated_at = datetime.now(UTC)
    return paper


def create_mock_section(
    id: str = None,
    paper_id: str = None,
    workspace_id: str = None,
    section_title: str = "Introduction",
    section_path: str = "1",
    page_start: int = 1,
    page_end: int = 2,
    content: str = "Introduction content here.",
    level: int = 1,
):
    """Create a mock section object."""
    section = MagicMock()
    section.id = id or str(uuid4())
    section.paper_id = paper_id or str(uuid4())
    section.workspace_id = workspace_id or str(uuid4())
    section.section_title = section_title
    section.section_path = section_path
    section.page_start = page_start
    section.page_end = page_end
    section.content = content
    section.level = level
    return section


def create_mock_extraction(
    id: str = None,
    paper_id: str = None,
    tier: int = 1,
    extraction_type: str = "full_text",
    structured_data: dict = None,
    processing_time_ms: int = 100,
    model_used: str = "pymupdf",
):
    """Create a mock extraction object."""
    extraction = MagicMock()
    extraction.id = id or str(uuid4())
    extraction.paper_id = paper_id or str(uuid4())
    extraction.tier = tier
    extraction.extraction_type = extraction_type
    extraction.structured_data = structured_data or {"test": "data"}
    extraction.processing_time_ms = processing_time_ms
    extraction.model_used = model_used
    return extraction


class MockDBSession:
    """Mock database session for testing."""

    def __init__(self):
        self.execute_result = None
        self.execute_side_effect = None

    async def execute(self, query):
        """Mock execute method."""
        if self.execute_side_effect:
            return self.execute_side_effect.pop(0)
        return self.execute_result

    async def commit(self):
        """Mock commit method."""
        pass

    async def refresh(self, obj):
        """Mock refresh method."""
        pass

    async def delete(self, obj):
        """Mock delete method."""
        pass

    async def add(self, obj):
        """Mock add method."""
        pass


@pytest.fixture
def mock_paper_service():
    """Create mock paper service."""
    service = MagicMock(spec=PaperService)
    service.create = AsyncMock()
    service.get = AsyncMock()

    async def update_side_effect(*args, **kwargs):
        paper = service.get.return_value
        if paper is None:
            return None
        for key, value in kwargs.items():
            if hasattr(paper, key) and value is not None:
                setattr(paper, key, value)
        return paper

    service.update = AsyncMock(side_effect=update_side_effect)
    service.delete = AsyncMock(return_value=False)
    service.list_workspace_papers = AsyncMock(return_value=[])
    service.list_visible_to_user = AsyncMock(return_value=[])
    service.search = AsyncMock(return_value=[])
    service.search_visible_to_user = AsyncMock(return_value=[])
    service.list_sections = AsyncMock(return_value=[])
    service.add_to_workspace = AsyncMock()
    service.is_in_workspace = AsyncMock(return_value=True)
    service.is_accessible_by_user = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_extraction_service():
    """Create mock extraction service."""
    service = MagicMock(spec=ExtractionService)
    service.extract_paper = AsyncMock()
    service.extract_sections = AsyncMock()
    return service


@pytest.fixture
def mock_workspace_service():
    """Create mock workspace service."""
    service = AsyncMock()
    service.get = AsyncMock(return_value=create_mock_workspace())
    return service


@pytest.fixture
def app(mock_paper_service, mock_extraction_service, mock_workspace_service):
    """Create FastAPI app with papers router and dependency overrides."""
    app = FastAPI()

    async def get_paper_service_override() -> PaperService:
        return mock_paper_service

    async def get_extraction_service_override() -> ExtractionService:
        return mock_extraction_service

    async def get_workspace_service_override():
        return mock_workspace_service

    async def get_current_user_override():
        return create_mock_user()

    # Set up dependency overrides
    app.dependency_overrides[get_paper_service] = get_paper_service_override
    app.dependency_overrides[get_extraction_service] = get_extraction_service_override
    app.dependency_overrides[get_workspace_service] = get_workspace_service_override
    app.dependency_overrides[get_current_user] = get_current_user_override

    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_paper():
    """Create sample paper for testing."""
    return create_mock_paper()


class TestCreatePaper:
    """Test paper creation endpoint."""

    def test_create_paper_success(self, client, mock_paper_service):
        """Test successful paper creation."""
        mock_paper = create_mock_paper(title="New Paper")
        mock_paper_service.create.return_value = mock_paper

        response = client.post(
            "/papers",
            json={
                "title": "New Paper",
                "authors": [{"name": "Author One"}],
                "year": 2024,
                "venue": "Test Venue",
                "abstract": "Test abstract content.",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Paper"
        assert data["year"] == 2024
        assert data["source"] == "manual_upload"
        assert "id" in data

    def test_create_paper_with_doi(self, client, mock_paper_service):
        """Test paper creation with DOI."""
        mock_paper = create_mock_paper(title="Paper with DOI", doi="10.5678/test.1234")
        mock_paper_service.create.return_value = mock_paper

        response = client.post(
            "/papers",
            json={
                "title": "Paper with DOI",
                "doi": "10.5678/test.1234",
                "year": 2023,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["doi"] == "10.5678/test.1234"

    def test_create_paper_minimal(self, client, mock_paper_service):
        """Test paper creation with minimal data (only title)."""
        mock_paper = create_mock_paper(title="Minimal Paper")
        mock_paper_service.create.return_value = mock_paper

        response = client.post(
            "/papers",
            json={
                "title": "Minimal Paper",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Paper"
        # Verify the service was called with the correct parameters
        mock_paper_service.create.assert_called_once()

    def test_create_paper_with_workspace_adds_association(self, client, mock_paper_service):
        """Creating with workspace_id should attach the paper to that workspace."""
        mock_paper = create_mock_paper(title="Workspace Linked Paper")
        mock_paper_service.create.return_value = mock_paper
        workspace_id = str(uuid4())

        response = client.post(
            "/papers",
            json={
                "title": "Workspace Linked Paper",
                "workspace_id": workspace_id,
            },
        )

        assert response.status_code == 201
        mock_paper_service.add_to_workspace.assert_awaited_once_with(
            paper_id=mock_paper.id,
            workspace_id=workspace_id,
        )

    def test_create_paper_missing_title_fails(self, client):
        """Test that paper creation without title fails."""
        response = client.post(
            "/papers",
            json={
                "year": 2024,
            },
        )

        assert response.status_code == 422  # Validation error


class TestListPapers:
    """Test paper listing endpoint."""

    def test_list_papers_empty(self, client, mock_paper_service):
        """Test listing papers when none exist."""
        mock_paper_service.list_visible_to_user.return_value = []

        response = client.get("/papers")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_papers_with_data(self, client, sample_paper, mock_paper_service):
        """Test listing papers with data."""
        mock_paper_service.list_visible_to_user.return_value = [sample_paper]

        response = client.get("/papers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Paper Title"

    def test_list_papers_with_limit(self, client, mock_paper_service):
        """Test listing papers with limit."""
        papers = [create_mock_paper(title=f"Paper {i}") for i in range(3)]
        mock_paper_service.list_visible_to_user.return_value = papers[:2]

        response = client.get("/papers?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_papers_by_workspace(self, client, sample_paper, mock_paper_service):
        """Test listing papers filtered by workspace."""
        mock_paper_service.list_workspace_papers.return_value = [sample_paper]

        workspace_id = str(uuid4())
        response = client.get(f"/papers?workspace_id={workspace_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Paper Title"


class TestGetPaper:
    """Test paper retrieval endpoint."""

    def test_get_paper_success(self, client, sample_paper, mock_paper_service):
        """Test successful paper retrieval."""
        mock_paper_service.get.return_value = sample_paper

        response = client.get(f"/papers/{sample_paper.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_paper.id
        assert data["title"] == "Test Paper Title"
        assert data["year"] == 2024

    def test_get_paper_not_found(self, client, mock_paper_service):
        """Test paper not found."""
        mock_paper_service.get.return_value = None

        response = client.get("/papers/nonexistent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestUpdatePaper:
    """Test paper update endpoint."""

    def test_update_paper_title(self, client, sample_paper, mock_paper_service):
        """Test updating paper title."""
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.update.return_value = sample_paper

        response = client.put(
            f"/papers/{sample_paper.id}",
            json={"title": "Updated Title"},
        )

        assert response.status_code == 200
        # Verify the title was set on the mock
        assert sample_paper.title == "Updated Title"

    def test_update_paper_multiple_fields(self, client, sample_paper, mock_paper_service):
        """Test updating multiple paper fields."""
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.update.return_value = sample_paper

        response = client.put(
            f"/papers/{sample_paper.id}",
            json={
                "title": "Updated Title",
                "year": 2025,
                "venue": "New Venue",
            },
        )

        assert response.status_code == 200
        # Verify fields were set on the mock
        assert sample_paper.title == "Updated Title"
        assert sample_paper.year == 2025
        assert sample_paper.venue == "New Venue"

    def test_update_paper_not_found(self, client, mock_paper_service):
        """Test updating non-existent paper."""
        mock_paper_service.get.return_value = None

        response = client.put(
            "/papers/nonexistent-id",
            json={"title": "New Title"},
        )

        assert response.status_code == 404

    def test_update_paper_partial(self, client, sample_paper, mock_paper_service):
        """Test partial paper update."""
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.update.return_value = sample_paper

        response = client.put(
            f"/papers/{sample_paper.id}",
            json={"title": "Only Title Updated"},
        )

        assert response.status_code == 200
        assert sample_paper.title == "Only Title Updated"


class TestDeletePaper:
    """Test paper deletion endpoint."""

    def test_delete_paper_success(self, client, sample_paper, mock_paper_service):
        """Test successful paper deletion."""
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.delete.return_value = True

        response = client.delete(f"/papers/{sample_paper.id}")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_paper_not_found(self, client, mock_paper_service):
        """Test deleting non-existent paper."""
        mock_paper_service.get.return_value = None

        response = client.delete("/papers/nonexistent-id")

        assert response.status_code == 404


class TestExtractPaper:
    """Test paper extraction endpoint."""

    def test_extract_paper_no_file_path(self, client, sample_paper, mock_paper_service):
        """Test extraction fails when paper has no file path."""
        sample_paper.file_path = None
        mock_paper_service.get.return_value = sample_paper

        response = client.post(
            f"/papers/{sample_paper.id}/extract",
            params={"workspace_id": "test-workspace"},
        )

        assert response.status_code == 400
        assert "no file path" in response.json()["detail"].lower()

    def test_extract_paper_not_found(self, client, mock_paper_service):
        """Test extraction fails when paper not found."""
        mock_paper_service.get.return_value = None

        response = client.post(
            "/papers/nonexistent-id/extract",
            params={"workspace_id": "test-workspace"},
        )

        assert response.status_code == 404

    def test_extract_paper_with_file_path(
        self, client, sample_paper, mock_paper_service, mock_extraction_service
    ):
        """Test extraction with file path."""
        sample_paper.file_path = "/tmp/test.pdf"
        mock_paper_service.get.return_value = sample_paper

        mock_extraction = create_mock_extraction(paper_id=sample_paper.id)
        mock_extraction_service.extract_paper.return_value = mock_extraction
        mock_extraction_service.extract_sections.return_value = []

        response = client.post(
            f"/papers/{sample_paper.id}/extract",
            params={"workspace_id": "test-workspace"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["paper_id"] == sample_paper.id
        assert data["tier"] == 1
        mock_extraction_service.extract_paper.assert_called_once()
        mock_extraction_service.extract_sections.assert_called_once()

    def test_extract_paper_tier2(
        self, client, sample_paper, mock_paper_service, mock_extraction_service
    ):
        """Test tier 2 extraction."""
        sample_paper.file_path = "/tmp/test.pdf"
        mock_paper_service.get.return_value = sample_paper

        mock_extraction = create_mock_extraction(paper_id=sample_paper.id, tier=2)
        mock_extraction_service.extract_paper.return_value = mock_extraction
        mock_extraction_service.extract_sections.return_value = []

        response = client.post(
            f"/papers/{sample_paper.id}/extract",
            params={"workspace_id": "test-workspace", "tier": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == 2


class TestGetPaperSections:
    """Test paper sections retrieval endpoint."""

    def test_get_sections_empty(self, client, sample_paper, mock_paper_service):
        """Test getting sections when none exist."""
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.list_sections.return_value = []

        response = client.get(f"/papers/{sample_paper.id}/sections")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_sections_not_found(self, client, mock_paper_service):
        """Test getting sections for non-existent paper."""
        mock_paper_service.get.return_value = None

        response = client.get("/papers/nonexistent-id/sections")

        assert response.status_code == 404

    def test_get_sections_with_data(self, client, sample_paper, mock_paper_service):
        """Test getting sections with data."""
        mock_section = create_mock_section(paper_id=sample_paper.id)
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.list_sections.return_value = [mock_section]

        response = client.get(f"/papers/{sample_paper.id}/sections")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["section_title"] == "Introduction"
        assert data[0]["section_path"] == "1"

    def test_get_sections_with_workspace_filter(self, client, sample_paper, mock_paper_service):
        """Test getting sections filtered by workspace."""
        workspace_id = str(uuid4())
        mock_section = create_mock_section(paper_id=sample_paper.id, workspace_id=workspace_id)
        mock_paper_service.get.return_value = sample_paper
        mock_paper_service.list_sections.return_value = [mock_section]

        response = client.get(
            f"/papers/{sample_paper.id}/sections",
            params={"workspace_id": workspace_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


class TestSearchPapers:
    """Test paper search endpoint."""

    def test_search_papers_global(self, client, sample_paper, mock_paper_service):
        """Test global paper search."""
        mock_paper_service.search_visible_to_user.return_value = [sample_paper]

        response = client.post(
            "/papers/search",
            json={"query": "Test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "Test"
        assert data["count"] >= 1

    def test_search_papers_in_workspace(self, client, sample_paper, mock_paper_service):
        """Test paper search within workspace."""
        mock_paper_service.search.return_value = [sample_paper]

        workspace_id = str(uuid4())
        response = client.post(
            "/papers/search",
            json={
                "query": "Test",
                "workspace_id": workspace_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1

    def test_search_papers_no_results(self, client, mock_paper_service):
        """Test search with no results."""
        mock_paper_service.search_visible_to_user.return_value = []

        response = client.post(
            "/papers/search",
            json={"query": "nonexistent"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["papers"] == []

    def test_search_papers_by_abstract(self, client, sample_paper, mock_paper_service):
        """Test search matching abstract content."""
        mock_paper_service.search_visible_to_user.return_value = [sample_paper]

        response = client.post(
            "/papers/search",
            json={"query": "abstract"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1

    def test_search_papers_empty_query_fails(self, client):
        """Test that empty query fails validation."""
        response = client.post(
            "/papers/search",
            json={"query": ""},
        )

        assert response.status_code == 422  # Validation error

    def test_search_papers_with_limit(self, client, sample_paper, mock_paper_service):
        """Test search with custom limit."""
        mock_paper_service.search_visible_to_user.return_value = [sample_paper]

        response = client.post(
            "/papers/search",
            json={"query": "Test", "limit": 5},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["papers"]) <= 5


class TestPaperResponse:
    """Test paper response model."""

    def test_response_includes_all_fields(self, client, sample_paper, mock_paper_service):
        """Test that response includes all expected fields."""
        mock_paper_service.get.return_value = sample_paper

        response = client.get(f"/papers/{sample_paper.id}")

        assert response.status_code == 200
        data = response.json()

        # Check all expected fields are present
        expected_fields = [
            "id", "doi", "title", "authors", "year", "venue",
            "abstract", "file_path", "source", "external_ids",
            "toc", "citation_count", "reference_count"
        ]
        for field in expected_fields:
            assert field in data

    def test_response_authors_format(self, client, sample_paper, mock_paper_service):
        """Test that authors are returned in correct format."""
        mock_paper_service.get.return_value = sample_paper

        response = client.get(f"/papers/{sample_paper.id}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["authors"], list)
        assert len(data["authors"]) == 2
        assert data["authors"][0]["name"] == "John Doe"


class TestHelperFunctions:
    """Test helper functions."""

    def test_paper_to_response(self, sample_paper):
        """Test paper_to_response helper function."""
        response = paper_to_response(sample_paper)

        assert response.id == sample_paper.id
        assert response.title == sample_paper.title
        assert response.authors == sample_paper.authors
        assert response.year == sample_paper.year
        assert response.doi == sample_paper.doi

    def test_section_to_response(self):
        """Test section_to_response helper function."""
        section = create_mock_section()
        response = section_to_response(section)

        assert response.id == section.id
        assert response.paper_id == section.paper_id
        assert response.section_title == section.section_title
        assert response.section_path == section.section_path
        assert response.level == section.level

    def test_paper_to_response_with_none_values(self):
        """Test paper_to_response handles None values correctly."""
        paper = create_mock_paper(
            doi=None,
            year=None,
            venue=None,
            abstract=None,
            toc=None,
            citation_count=None,
            reference_count=None,
        )
        response = paper_to_response(paper)

        assert response.doi is None
        assert response.year is None
        assert response.venue is None
        assert response.abstract is None
        assert response.toc is None
        assert response.citation_count is None
        assert response.reference_count is None

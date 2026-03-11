"""Integration tests for paper flow.

Tests the complete paper management flow including:
- Paper creation
- Paper listing
- Paper retrieval
- Paper update
- Paper deletion
- Paper search
"""

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    FixturePaper,
    FixtureUser,
    FixtureWorkspace,
)


class TestPaperFlow:
    """Tests for complete paper flow."""

    @pytest.mark.asyncio
    async def test_create_paper(self, authenticated_client: AsyncClient):
        """Test creating a new paper."""
        response = await authenticated_client.post(
            "/api/papers/",
            json={
                "title": "Attention Is All You Need",
                "authors": [
                    {"name": "Ashish Vaswani", "affiliation": "Google Brain"},
                    {"name": "Noam Shazeer", "affiliation": "Google Brain"},
                ],
                "year": 2017,
                "venue": "NeurIPS",
                "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
                "doi": "10.48550/arXiv.1706.03762",
                "source": "manual_upload",
            },
        )
        assert response.status_code == 201
        paper = response.json()
        assert paper["title"] == "Attention Is All You Need"
        assert len(paper["authors"]) == 2
        assert paper["year"] == 2017
        assert paper["doi"] == "10.48550/arXiv.1706.03762"
        assert "id" in paper

    @pytest.mark.asyncio
    async def test_create_paper_minimal(self, authenticated_client: AsyncClient):
        """Test creating a paper with minimal required fields."""
        response = await authenticated_client.post(
            "/api/papers/",
            json={
                "title": "Minimal Paper",
            },
        )
        assert response.status_code == 201
        paper = response.json()
        assert paper["title"] == "Minimal Paper"
        assert paper["source"] == "manual_upload"  # Default value
        assert paper["authors"] == []  # Default empty list

    @pytest.mark.asyncio
    async def test_create_paper_missing_title_fails(self, authenticated_client: AsyncClient):
        """Test that creating paper without title fails."""
        response = await authenticated_client.post(
            "/api/papers/",
            json={
                "year": 2024,
            },
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_paper_by_id(
        self, authenticated_client: AsyncClient, test_paper: TestPaper
    ):
        """Test retrieving a paper by ID."""
        response = await authenticated_client.get(f"/api/papers/{test_paper.id}")
        assert response.status_code == 200
        paper = response.json()
        assert paper["id"] == test_paper.id
        assert paper["title"] == test_paper.title
        assert paper["doi"] == test_paper.doi

    @pytest.mark.asyncio
    async def test_get_nonexistent_paper(self, authenticated_client: AsyncClient):
        """Test retrieving a nonexistent paper."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.get(f"/api/papers/{fake_id}")
        assert response.status_code == 404
        error = response.json()
        assert "not found" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_papers(
        self, authenticated_client: AsyncClient, test_paper: TestPaper
    ):
        """Test listing papers."""
        response = await authenticated_client.get("/api/papers/")
        assert response.status_code == 200
        papers = response.json()
        assert isinstance(papers, list)
        # Should contain at least the test paper
        paper_ids = [p["id"] for p in papers]
        assert test_paper.id in paper_ids

    @pytest.mark.asyncio
    async def test_list_papers_with_limit(
        self, authenticated_client: AsyncClient
    ):
        """Test listing papers with limit."""
        # Create multiple papers
        for i in range(5):
            await authenticated_client.post(
                "/api/papers/",
                json={"title": f"Paper {i}"},
            )

        response = await authenticated_client.get("/api/papers/?limit=3")
        assert response.status_code == 200
        papers = response.json()
        assert len(papers) <= 3

    @pytest.mark.asyncio
    async def test_update_paper(
        self, authenticated_client: AsyncClient, test_paper: TestPaper
    ):
        """Test updating a paper."""
        response = await authenticated_client.put(
            f"/api/papers/{test_paper.id}",
            json={
                "title": "Updated Paper Title",
                "year": 2025,
            },
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["title"] == "Updated Paper Title"
        assert updated["year"] == 2025
        # Other fields should remain unchanged
        assert updated["doi"] == test_paper.doi

    @pytest.mark.asyncio
    async def test_update_nonexistent_paper(self, authenticated_client: AsyncClient):
        """Test updating a nonexistent paper."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.put(
            f"/api/papers/{fake_id}",
            json={"title": "Updated Title"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_paper(
        self, authenticated_client: AsyncClient, test_session
    ):
        """Test deleting a paper."""
        # Create a paper to delete
        response = await authenticated_client.post(
            "/api/papers/",
            json={"title": "Paper to Delete"},
        )
        paper_id = response.json()["id"]

        # Delete it
        response = await authenticated_client.delete(f"/api/papers/{paper_id}")
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

        # Verify it's deleted
        response = await authenticated_client.get(f"/api/papers/{paper_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_paper(self, authenticated_client: AsyncClient):
        """Test deleting a nonexistent paper."""
        import uuid
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.delete(f"/api/papers/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_search_papers_by_title(
        self, authenticated_client: AsyncClient, test_paper: TestPaper
    ):
        """Test searching papers by title."""
        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "Integration Testing",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert "papers" in result
        assert "count" in result
        assert result["query"] == "Integration Testing"
        # Should find our test paper with "Integration Testing" in title
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_papers_by_abstract(
        self, authenticated_client: AsyncClient, test_paper: TestPaper
    ):
        """Test searching papers by abstract."""
        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "test abstract",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        result = response.json()
        # Should find paper with "test abstract" in abstract
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_papers_in_workspace(
        self,
        authenticated_client: AsyncClient,
        test_workspace: TestWorkspace,
        test_paper: TestPaper,
    ):
        """Test searching papers within a specific workspace."""
        # First add paper to workspace
        await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/papers/{test_paper.id}",
            json={},
        )

        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "Test",
                "workspace_id": test_workspace.id,
                "limit": 10,
            },
        )
        assert response.status_code == 200
        result = response.json()
        # Should find our test paper in the workspace
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_papers_no_results(
        self, authenticated_client: AsyncClient
    ):
        """Test searching with query that matches nothing."""
        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "zzzzzzzznonexistentxxxxx",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["count"] == 0
        assert result["papers"] == []

    @pytest.mark.asyncio
    async def test_paper_response_format(
        self, authenticated_client: AsyncClient
    ):
        """Test that paper response has all expected fields."""
        response = await authenticated_client.post(
            "/api/papers/",
            json={
                "title": "Format Test Paper",
                "authors": [{"name": "Test Author"}],
                "year": 2024,
                "venue": "Test Venue",
                "abstract": "Test abstract",
                "doi": "10.1234/test.2024",
                "citation_count": 10,
                "reference_count": 25,
            },
        )
        assert response.status_code == 201
        paper = response.json()

        # Check all expected fields
        assert "id" in paper
        assert "doi" in paper
        assert "title" in paper
        assert "authors" in paper
        assert "year" in paper
        assert "venue" in paper
        assert "abstract" in paper
        assert "file_path" in paper
        assert "source" in paper
        assert "external_ids" in paper
        assert "toc" in paper
        assert "citation_count" in paper
        assert "reference_count" in paper


class TestPaperWorkspaceAssociation:
    """Tests for paper-workspace associations."""

    @pytest.mark.asyncio
    async def test_list_papers_filtered_by_workspace(
        self,
        authenticated_client: AsyncClient,
        test_workspace: TestWorkspace,
        test_paper: TestPaper,
    ):
        """Test listing papers filtered by workspace."""
        # Add paper to workspace
        await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/papers/{test_paper.id}",
            json={},
        )

        response = await authenticated_client.get(
            f"/api/papers/?workspace_id={test_workspace.id}"
        )
        assert response.status_code == 200
        papers = response.json()
        paper_ids = [p["id"] for p in papers]
        assert test_paper.id in paper_ids

    @pytest.mark.asyncio
    async def test_paper_can_be_in_multiple_workspaces(
        self,
        authenticated_client: AsyncClient,
        test_user: TestUser,
        test_paper: TestPaper,
        test_workspace: TestWorkspace,
    ):
        """Test that the same paper can be added to multiple workspaces."""
        # Create another workspace
        response = await authenticated_client.post(
            "/api/workspaces/",
            params={"user_id": str(test_user.id)},
            json={
                "name": "Second Workspace",
                "type": "thesis",
            },
        )
        second_workspace_id = response.json()["id"]

        # Add paper to first workspace
        response = await authenticated_client.post(
            f"/api/workspaces/{test_workspace.id}/papers/{test_paper.id}",
            json={},
        )
        assert response.status_code == 200

        # Add same paper to second workspace
        response = await authenticated_client.post(
            f"/api/workspaces/{second_workspace_id}/papers/{test_paper.id}",
            json={},
        )
        assert response.status_code == 200

        # Verify paper is in both workspaces
        response1 = await authenticated_client.get(
            f"/api/workspaces/{test_workspace.id}/papers"
        )
        response2 = await authenticated_client.get(
            f"/api/workspaces/{second_workspace_id}/papers"
        )

        papers1 = response1.json()
        papers2 = response2.json()

        assert any(p["id"] == test_paper.id for p in papers1)
        assert any(p["id"] == test_paper.id for p in papers2)


class TestPaperDOIHandling:
    """Tests for DOI handling."""

    @pytest.mark.asyncio
    async def test_create_paper_with_doi(self, authenticated_client: AsyncClient):
        """Test creating a paper with DOI."""
        response = await authenticated_client.post(
            "/api/papers/",
            json={
                "title": "DOI Test Paper",
                "doi": "10.1234/unique.doi.2024",
            },
        )
        assert response.status_code == 201
        paper = response.json()
        assert paper["doi"] == "10.1234/unique.doi.2024"

    @pytest.mark.asyncio
    async def test_create_paper_without_doi(self, authenticated_client: AsyncClient):
        """Test creating a paper without DOI."""
        response = await authenticated_client.post(
            "/api/papers/",
            json={
                "title": "No DOI Paper",
            },
        )
        assert response.status_code == 201
        paper = response.json()
        assert paper["doi"] is None


class TestPaperSearchFeatures:
    """Tests for paper search features."""

    @pytest.mark.asyncio
    async def test_search_case_insensitive(
        self, authenticated_client: AsyncClient, test_paper: TestPaper
    ):
        """Test that search is case insensitive."""
        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "INTEGRATION TESTING",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_with_special_characters(
        self, authenticated_client: AsyncClient
    ):
        """Test search with special characters."""
        # Create paper with special characters
        await authenticated_client.post(
            "/api/papers/",
            json={
                "title": "Machine Learning: A Review (2024)",
                "abstract": "Testing special characters: @#$%^&*()",
            },
        )

        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "Machine Learning",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_respects_limit(
        self, authenticated_client: AsyncClient
    ):
        """Test that search respects the limit parameter."""
        # Create multiple papers with same keyword
        for i in range(15):
            await authenticated_client.post(
                "/api/papers/",
                json={
                    "title": f"Machine Learning Paper {i}",
                },
            )

        response = await authenticated_client.post(
            "/api/papers/search",
            json={
                "query": "Machine Learning",
                "limit": 5,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert len(result["papers"]) <= 5

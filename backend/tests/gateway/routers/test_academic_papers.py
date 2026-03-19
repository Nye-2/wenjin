"""Tests for deprecated academic paper compatibility routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.routers.academic import get_paper_service, router


def _mock_user():
    user = MagicMock()
    user.id = "user-1"
    return user


def _mock_paper():
    paper = MagicMock()
    paper.id = "paper-1"
    paper.doi = "10.1234/test"
    paper.title = "Compatibility Paper"
    paper.authors = [{"name": "Tester"}]
    paper.year = 2024
    paper.venue = "TestConf"
    paper.abstract = "Abstract"
    paper.source = "manual_upload"
    paper.citation_count = 1
    paper.reference_count = 2
    return paper


def _create_client(mock_service):
    app = FastAPI()

    async def override_user():
        return _mock_user()

    async def override_paper_service():
        return mock_service

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_paper_service] = override_paper_service
    app.include_router(router)
    return TestClient(app)


def test_create_paper_uses_summary_response():
    service = AsyncMock()
    service.create.return_value = _mock_paper()
    client = _create_client(service)

    response = client.post(
        "/papers",
        json={"title": "Compatibility Paper", "authors": [{"name": "Tester"}]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Compatibility Paper"
    assert "file_path" not in body


def test_search_papers_returns_legacy_result_shape():
    service = AsyncMock()
    client = _create_client(service)

    with patch(
        "src.academic.tools.semantic_scholar.semantic_scholar_search_tool",
        new=SimpleNamespace(ainvoke=AsyncMock(return_value="legacy result")),
    ):
        response = client.get("/papers/search", params={"query": "llm", "limit": 3})

    assert response.status_code == 200
    assert response.json() == {"result": "legacy result"}

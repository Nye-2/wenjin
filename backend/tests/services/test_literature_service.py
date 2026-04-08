"""Tests for LiteratureService batch import behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.literature_service import LiteratureService


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_batch_import_deep_research_creates_new_rows(mock_db_session):
    service = LiteratureService(mock_db_session)

    artifact = SimpleNamespace(
        id="art-1",
        content={
            "discovery": {
                "seminal_works": [
                    {
                        "title": "Paper A",
                        "authors": ["Alice", "Bob"],
                        "year": 2021,
                        "significance": "Seminal contribution",
                    }
                ],
                "recent_works": [
                    {
                        "title": "Paper B",
                        "authors": [{"name": "Carol"}, {"author": "Dave"}],
                        "year": "2024",
                        "relevance": "Highly relevant",
                        "DOI": "10.1000/paper-b",
                        "citation_count": "42",
                        "journal": "Nature",
                        "summary": "Recent progress in this domain",
                    }
                ],
            }
        },
    )

    mock_db_session.execute.side_effect = [
        _scalars_result([artifact]),
        _scalars_result([]),
    ]

    result = await service.batch_import(
        workspace_id="ws-1",
        source="deep_research",
        paper_ids=["art-1"],
    )

    assert result == {"imported": 2}
    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_awaited_once()

    added_rows = [call.args[0] for call in mock_db_session.add.call_args_list]
    assert added_rows[0].title == "Paper A"
    assert added_rows[0].authors == ["Alice", "Bob"]
    assert added_rows[0].source == "deep_research"
    assert added_rows[1].title == "Paper B"
    assert added_rows[1].authors == ["Carol", "Dave"]
    assert added_rows[1].doi == "10.1000/paper-b"
    assert added_rows[1].citations == 42
    assert added_rows[1].venue == "Nature"
    assert "Recent progress in this domain" in (added_rows[1].abstract or "")


@pytest.mark.asyncio
async def test_batch_import_literature_search_creates_new_rows(mock_db_session):
    service = LiteratureService(mock_db_session)

    artifact = SimpleNamespace(
        id="art-search-1",
        type="literature_search_results",
        content={
            "top_hits": [
                {
                    "title": "Search Paper A",
                    "authors": ["Alice"],
                    "year": 2023,
                    "venue": "ACL",
                    "summary": "High confidence literature search hit",
                    "doi": "10.1000/search-paper-a",
                }
            ],
            "papers": [
                {
                    "title": "Search Paper B",
                    "authors": [{"name": "Bob"}],
                    "year": "2022",
                    "journal": "TACL",
                    "relevance": "Directly related to the query",
                }
            ],
        },
    )

    mock_db_session.execute.side_effect = [
        _scalars_result([artifact]),
        _scalars_result([]),
    ]

    result = await service.batch_import(
        workspace_id="ws-1",
        source="literature_search",
        paper_ids=["art-search-1"],
    )

    assert result == {"imported": 2}
    assert mock_db_session.add.call_count == 2
    added_rows = [call.args[0] for call in mock_db_session.add.call_args_list]
    assert {row.source for row in added_rows} == {"literature_search"}
    assert {row.title for row in added_rows} == {
        "Search Paper A",
        "Search Paper B",
    }


@pytest.mark.asyncio
async def test_batch_import_deep_research_skips_existing_title_and_doi(mock_db_session):
    service = LiteratureService(mock_db_session)

    artifact = SimpleNamespace(
        id="art-1",
        content={
            "discovery": {
                "seminal_works": [
                    {
                        "title": "Paper A",
                        "authors": ["Alice"],
                        "year": 2021,
                    }
                ],
                "recent_works": [
                    {
                        "title": "Paper C",
                        "authors": ["Carol"],
                        "doi": "10.1000/existing-doi",
                    }
                ],
            }
        },
    )
    existing_items = [
        SimpleNamespace(title="paper a", doi=None),
        SimpleNamespace(title="Legacy", doi="10.1000/existing-doi"),
    ]

    mock_db_session.execute.side_effect = [
        _scalars_result([artifact]),
        _scalars_result(existing_items),
    ]

    result = await service.batch_import(
        workspace_id="ws-1",
        source="deep_research",
        paper_ids=["art-1"],
    )

    assert result == {"imported": 0}
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_batch_import_non_deep_research_returns_zero(mock_db_session):
    service = LiteratureService(mock_db_session)

    result = await service.batch_import(
        workspace_id="ws-1",
        source="manual",
        paper_ids=["x"],
    )

    assert result == {"imported": 0}
    mock_db_session.execute.assert_not_called()
    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_batch_import_empty_ids_returns_zero(mock_db_session):
    service = LiteratureService(mock_db_session)

    result = await service.batch_import(
        workspace_id="ws-1",
        source="deep_research",
        paper_ids=[],
    )

    assert result == {"imported": 0}
    mock_db_session.execute.assert_not_called()

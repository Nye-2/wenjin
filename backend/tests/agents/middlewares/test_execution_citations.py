"""Tests for ExecutionMiddleware citation handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_generate_bibliography_from_citations():
    """Test that citation_ids are processed to generate bibliography."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    # Mock execution service
    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    # Mock database and papers
    mock_paper_1 = MagicMock()
    mock_paper_1.id = "uuid-1"
    mock_paper_1.title = "Test Paper"
    mock_paper_1.authors = [{"name": "John Smith"}]
    mock_paper_1.year = 2024
    mock_paper_1.venue = "Nature"
    mock_paper_1.doi = "10.1234/test"
    mock_paper_1.abstract = None

    mock_paper_2 = MagicMock()
    mock_paper_2.id = "uuid-2"
    mock_paper_2.title = "Another Paper"
    mock_paper_2.authors = [{"name": "Jane Doe"}]
    mock_paper_2.year = 2023
    mock_paper_2.venue = "Science"
    mock_paper_2.doi = None
    mock_paper_2.abstract = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_paper_1, mock_paper_2]
    mock_db.execute.return_value = mock_result

    # Generate bibliography
    bibliography = await middleware._generate_bibliography(mock_db, ["uuid-1", "uuid-2"])

    assert bibliography is not None
    assert "Smith2024" in bibliography
    assert "Doe2023" in bibliography


@pytest.mark.asyncio
async def test_generate_bibliography_empty_ids():
    """Test bibliography generation with empty citation_ids."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    mock_db = AsyncMock()
    bibliography = await middleware._generate_bibliography(mock_db, [])

    assert bibliography is None


@pytest.mark.asyncio
async def test_generate_bibliography_no_papers_found():
    """Test bibliography generation when no papers found."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    bibliography = await middleware._generate_bibliography(mock_db, ["nonexistent"])

    assert bibliography is None


def test_build_request_with_bibliography_style():
    """Test that bibliography_style is passed through options."""
    from src.agents.middlewares.execution import ExecutionMiddleware
    from src.execution.types import ExecutionType

    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    request = middleware._build_request(
        exec_type=ExecutionType.LATEX_COMPILE,
        tool_args={
            "latex_source": r"\documentclass{article}\begin{document}\end{document}",
            "compiler": "xelatex",
            "bibliography_style": "alpha",
        },
        thread_id="test-thread",
        workspace_id="test-workspace",
    )

    assert request.options.get("bibliography_style") == "alpha"

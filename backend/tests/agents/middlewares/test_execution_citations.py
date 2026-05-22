"""Tests for ExecutionMiddleware citation handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_generate_bibliography_from_citations():
    """Test that citation_ids are processed to generate bibliography."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    # Mock execution service
    mock_service = MagicMock()
    reference_service = SimpleNamespace(
        build_source_bibliography=AsyncMock(
            return_value=SimpleNamespace(content="@article{Smith2024}\n@article{Doe2023}")
        )
    )
    middleware = ExecutionMiddleware(mock_service, reference_service=reference_service)

    # Generate bibliography
    bibliography = await middleware._generate_bibliography(
        ["uuid-1", "uuid-2"],
        workspace_id="ws-1",
    )

    assert bibliography is not None
    assert "Smith2024" in bibliography
    assert "Doe2023" in bibliography


@pytest.mark.asyncio
async def test_generate_bibliography_empty_ids():
    """Test bibliography generation with empty citation_ids."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    bibliography = await middleware._generate_bibliography([], workspace_id="ws-1")

    assert bibliography is None


@pytest.mark.asyncio
async def test_generate_bibliography_no_papers_found():
    """Test bibliography generation when no papers found."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    mock_service = MagicMock()
    reference_service = SimpleNamespace(
        build_source_bibliography=AsyncMock(return_value=SimpleNamespace(content=None))
    )
    middleware = ExecutionMiddleware(mock_service, reference_service=reference_service)

    bibliography = await middleware._generate_bibliography(
        ["nonexistent"],
        workspace_id="ws-1",
    )

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

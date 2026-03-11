"""Integration tests for citation-to-LaTeX workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_citation_to_latex_workflow():
    """Test complete workflow: citation_ids -> BibTeX -> LaTeX compilation."""
    from src.agents.middlewares.execution import ExecutionMiddleware
    from src.execution.types import ExecutionType
    from src.academic.citation.bibtex.exporter import generate_citation_key

    # Setup mock papers in database
    mock_paper = MagicMock()
    mock_paper.id = "test-uuid"
    mock_paper.title = "Deep Learning Advances"
    mock_paper.authors = [{"name": "John Smith"}]
    mock_paper.year = 2024
    mock_paper.venue = "Nature"
    mock_paper.doi = "10.1234/test"
    mock_paper.abstract = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_paper]
    mock_db.execute.return_value = mock_result

    # Setup middleware
    mock_service = MagicMock()
    mock_service.execute = AsyncMock()
    middleware = ExecutionMiddleware(mock_service)

    # Generate citation key
    paper_dict = {
        "title": mock_paper.title,
        "authors": mock_paper.authors,
        "year": mock_paper.year,
    }
    citation_key = generate_citation_key(paper_dict)
    assert citation_key == "Smith2024"

    # Generate bibliography
    bibliography = await middleware._generate_bibliography(mock_db, ["test-uuid"])

    assert bibliography is not None
    assert "Smith2024" in bibliography
    assert "Deep Learning Advances" in bibliography
    assert "John Smith" in bibliography


@pytest.mark.asyncio
async def test_latex_provider_bibliography_injection():
    """Test LaTeX provider correctly injects bibliography commands."""
    from src.execution.providers.latex import LaTeXProvider

    provider = LaTeXProvider()

    latex_source = r"""\documentclass{article}
\begin{document}
According to \cite{Smith2024}, this is important.
\end{document}"""

    options = {
        "compiler": "xelatex",
        "bibliography": "@article{Smith2024, author={Smith, John}, title={Test}}",
        "bibliography_style": "alpha",
    }

    command = provider.build_command(latex_source, options)
    command_str = " ".join(command)

    # Check that bibliography commands are injected
    assert "bibliographystyle{alpha}" in command_str
    assert "bibliography{refs}" in command_str


@pytest.mark.asyncio
async def test_end_to_end_citation_workflow():
    """Test complete end-to-end citation workflow with mocked components."""
    from src.agents.middlewares.execution import ExecutionMiddleware
    from src.execution.types import ExecutionType, ExecutionResult, ExecutionStatus
    from src.academic.citation.bibtex.exporter import generate_citation_key

    # Mock paper
    mock_paper = MagicMock()
    mock_paper.id = "paper-1"
    mock_paper.title = "Research Paper"
    mock_paper.authors = [{"name": "Alice Researcher"}]
    mock_paper.year = 2024
    mock_paper.venue = "Conference on Testing"
    mock_paper.doi = "10.5678/paper"
    mock_paper.abstract = None

    # Mock database
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_paper]
    mock_db.execute.return_value = mock_result

    # Mock execution service
    mock_service = AsyncMock()
    mock_service.execute.return_value = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        sandbox_path="/mnt/user-data/test/output.pdf",
        execution_time_ms=500,
        metadata={"page_count": 1},
    )

    # Create middleware
    middleware = ExecutionMiddleware(mock_service)

    # Step 1: Generate bibliography from citation IDs
    bibliography = await middleware._generate_bibliography(mock_db, ["paper-1"])
    assert bibliography is not None

    # Step 2: Verify citation key format
    citation_key = generate_citation_key({
        "title": mock_paper.title,
        "authors": mock_paper.authors,
        "year": mock_paper.year,
    })
    assert citation_key == "Researcher2024"

    # Step 3: Verify bibliography contains expected content
    assert "Researcher2024" in bibliography
    assert "Research Paper" in bibliography
    assert "Alice Researcher" in bibliography

    # Step 4: Build execution request
    request = middleware._build_request(
        exec_type=ExecutionType.LATEX_COMPILE,
        tool_args={
            "latex_source": r"\documentclass{article}\begin{document}\cite{Researcher2024}\end{document}",
            "compiler": "xelatex",
            "citation_ids": ["paper-1"],
            "bibliography": bibliography,
            "bibliography_style": "plain",
        },
        thread_id="test-thread",
        workspace_id="test-workspace",
    )

    # Verify request was built correctly
    assert request.execution_type == ExecutionType.LATEX_COMPILE
    assert request.options.get("bibliography") == bibliography
    assert request.options.get("bibliography_style") == "plain"


def test_citation_key_consistency():
    """Test that citation keys are consistent between exporter and generation."""
    from src.academic.citation.bibtex.exporter import generate_citation_key, BibTeXExporter

    paper = {
        "title": "Test Paper",
        "authors": [{"name": "John Smith"}],
        "year": 2024,
    }

    # Generate key directly
    key = generate_citation_key(paper)

    # Generate key via exporter
    exporter = BibTeXExporter()
    bib_output = exporter.export([paper])

    # Both should use same key
    assert key in bib_output
    # Verify the BibTeX entry format includes the key
    # Format is: @type{key, ...} - check that key appears after opening brace
    assert f"{{{key}," in bib_output

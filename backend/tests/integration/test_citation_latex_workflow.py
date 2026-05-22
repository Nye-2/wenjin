"""Integration tests for citation-to-LaTeX workflow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _reference_service(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        build_source_bibliography=AsyncMock(
            return_value=SimpleNamespace(content=content)
        )
    )


@pytest.mark.asyncio
async def test_citation_to_latex_workflow():
    """Test complete workflow: citation_ids -> BibTeX -> LaTeX compilation."""
    from src.agents.middlewares.execution import ExecutionMiddleware

    # Setup middleware
    mock_service = MagicMock()
    mock_service.execute = AsyncMock()
    bibliography_content = (
        "@article{Smith2024,\n"
        "  title={Deep Learning Advances},\n"
        "  author={John Smith}\n"
        "}"
    )
    middleware = ExecutionMiddleware(
        mock_service,
        reference_service=_reference_service(bibliography_content),
    )

    # Generate bibliography
    bibliography = await middleware._generate_bibliography(
        ["test-uuid"],
        workspace_id="ws-1",
    )

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
    from src.execution.types import ExecutionResult, ExecutionStatus, ExecutionType

    # Mock execution service
    mock_service = AsyncMock()
    mock_service.execute.return_value = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        sandbox_path="/mnt/user-data/test/output.pdf",
        execution_time_ms=500,
        metadata={"page_count": 1},
    )

    # Create middleware
    bibliography_content = (
        "@inproceedings{Researcher2024,\n"
        "  title={Research Paper},\n"
        "  author={Alice Researcher}\n"
        "}"
    )
    middleware = ExecutionMiddleware(
        mock_service,
        reference_service=_reference_service(bibliography_content),
    )

    # Step 1: Generate bibliography from citation IDs
    bibliography = await middleware._generate_bibliography(
        ["paper-1"],
        workspace_id="ws-1",
    )
    assert bibliography is not None

    # Step 2: Verify bibliography contains expected Reference Library content
    assert "Researcher2024" in bibliography
    assert "Research Paper" in bibliography
    assert "Alice Researcher" in bibliography

    # Step 3: Build execution request
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

"""Tests for strict LaTeX rewrite structural guards."""

from __future__ import annotations

import pytest

from src.services.latex.rewrite_guard import (
    LatexStructureValidationError,
    validate_latex_document_structure,
    validate_rewrite_segment,
)


def test_validate_rewrite_segment_rejects_boundary_leak() -> None:
    with pytest.raises(LatexStructureValidationError, match="Selection rewrite expanded"):
        validate_rewrite_segment(
            original_text="alpha beta",
            rewritten_text="alpha gamma beta",
            scope="selection",
            target_start=10,
            target_end=20,
            resolved_selection_start=10,
            resolved_selection_end=21,
        )


def test_validate_rewrite_segment_allows_document_scope_full_range() -> None:
    validate_rewrite_segment(
        original_text="\\begin{document}\nOld.\n\\end{document}",
        rewritten_text="\\begin{document}\nNew.\n\\end{document}",
        scope="document",
        target_start=0,
        target_end=36,
        resolved_selection_start=12,
        resolved_selection_end=16,
    )


def test_validate_rewrite_segment_rejects_citation_drop() -> None:
    with pytest.raises(LatexStructureValidationError, match="citation markers"):
        validate_rewrite_segment(
            original_text="See \\cite{smith2020}.",
            rewritten_text="See this result.",
        )


def test_validate_rewrite_segment_rejects_unbalanced_braces() -> None:
    with pytest.raises(LatexStructureValidationError, match="opening brace"):
        validate_rewrite_segment(
            original_text="A",
            rewritten_text="{A",
        )


def test_validate_document_structure_rejects_environment_mismatch() -> None:
    with pytest.raises(LatexStructureValidationError, match="Environment mismatch"):
        validate_latex_document_structure(
            "\\begin{equation}x=1\\end{align}",
        )


def test_validate_document_structure_accepts_simple_valid_content() -> None:
    validate_latex_document_structure(
        "\\section{Intro}\n"
        "Value is $x+1$.\n"
        "\\begin{equation}\n"
        "x = y + 1\n"
        "\\end{equation}\n"
    )


def test_validate_document_structure_ignores_verbatim_like_block_content() -> None:
    validate_latex_document_structure(
        "\\begin{lstlisting}\n"
        "{ code with $ and fake \\end{equation} markers }\n"
        "\\end{lstlisting}\n"
        "\\begin{minted}{python}\n"
        "print('{ not latex }')\n"
        "\\end{minted}\n"
    )


def test_validate_document_structure_still_rejects_unmatched_verbatim_begin() -> None:
    with pytest.raises(LatexStructureValidationError, match="unmatched \\\\begin"):
        validate_latex_document_structure(
            "\\begin{verbatim}\n"
            "code block without end\n",
        )

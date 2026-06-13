"""Tests for LaTeX rewrite diff helpers."""

from __future__ import annotations

from src.services.latex.rewrite_diff import (
    build_latex_rewrite_diff,
    compute_content_hash,
    compute_range_hash,
)


def test_hash_helpers_are_stable() -> None:
    content = "\\section{Intro}\nA text.\n"
    assert compute_content_hash(content) == compute_content_hash(content)
    segment = content[0:10]
    assert compute_range_hash(0, 10, segment) == compute_range_hash(0, 10, segment)


def test_diff_includes_hunks_and_stats() -> None:
    diff = build_latex_rewrite_diff(
        original_text="The method is robust.",
        rewritten_text="The proposed method is robust and efficient.",
        target_start=120,
        target_end=141,
        scope="selection",
        resolved_selection_start=120,
        resolved_selection_end=141,
    )
    hunks = diff.get("hunks")
    stats = diff.get("stats")
    assert isinstance(hunks, list) and hunks
    assert isinstance(stats, dict)
    assert int(stats["tokens_changed"]) > 0
    assert int(stats["chars_added"]) > 0


def test_diff_risk_flags_detect_citation_and_brace_issues() -> None:
    diff = build_latex_rewrite_diff(
        original_text="See \\cite{smith2020}.",
        rewritten_text="See the result in {.",
        target_start=10,
        target_end=28,
        scope="selection",
        resolved_selection_start=10,
        resolved_selection_end=28,
    )
    risk_flags = set(diff.get("risk_flags") or [])
    assert "citation_drop" in risk_flags
    assert "brace_unbalanced" in risk_flags


def test_diff_risk_flags_detect_boundary_leak_for_selection_scope() -> None:
    diff = build_latex_rewrite_diff(
        original_text="alpha beta",
        rewritten_text="alpha gamma beta",
        target_start=50,
        target_end=60,
        scope="selection",
        resolved_selection_start=52,
        resolved_selection_end=58,
    )
    risk_flags = set(diff.get("risk_flags") or [])
    assert "boundary_leak" in risk_flags


def test_diff_document_scope_does_not_report_selection_boundary_leak() -> None:
    diff = build_latex_rewrite_diff(
        original_text="\\begin{document}\nOld.\n\\end{document}",
        rewritten_text="\\begin{document}\nNew.\n\\end{document}",
        target_start=0,
        target_end=36,
        scope="document",
        resolved_selection_start=12,
        resolved_selection_end=16,
    )

    risk_flags = set(diff.get("risk_flags") or [])
    assert "boundary_leak" not in risk_flags

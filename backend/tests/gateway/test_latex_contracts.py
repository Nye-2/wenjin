"""Gateway contract tests for LaTeX Prism adapter payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.gateway.contracts.latex import LatexFeedbackRewriteRequest


def test_feedback_rewrite_document_scope_allows_empty_selection() -> None:
    request = LatexFeedbackRewriteRequest(
        file_path="main.tex",
        selected_text="",
        comment="整体改得更像研究者写作。",
        scope="document",
    )

    assert request.scope == "document"
    assert request.selected_text == ""


def test_feedback_rewrite_local_scope_requires_selection() -> None:
    with pytest.raises(ValidationError, match="selected_text is required"):
        LatexFeedbackRewriteRequest(
            file_path="main.tex",
            selected_text="",
            comment="改写这一段。",
            scope="section",
        )

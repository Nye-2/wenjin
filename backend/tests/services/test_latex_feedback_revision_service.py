"""Tests for LaTeX feedback revision service helpers."""

from __future__ import annotations

import pytest

from src.services.latex import feedback_revision_service as service


def test_build_feedback_anchor_contains_heading_and_line_hint() -> None:
    content = (
        "\\section{Introduction}\n"
        "This is the first paragraph.\n"
        "More details here.\n"
    )
    start = content.index("first")
    end = start + len("first paragraph")
    anchor = service.build_feedback_anchor(content, start, end)

    assert anchor["selected_text"] == "first paragraph"
    assert anchor["heading_title"] == "Introduction"
    assert anchor["heading_level"] == "section"
    assert anchor["line_hint"] == 2


def test_resolve_feedback_range_uses_anchor_after_text_shift() -> None:
    original = (
        "\\section{Intro}\n"
        "The method is robust.\n"
        "The method is robust.\n"
    )
    first_start = original.index("The method is robust.")
    first_end = first_start + len("The method is robust.")
    anchor = service.build_feedback_anchor(original, first_start, first_end)

    shifted = (
        "\\section{Intro}\n"
        "A new sentence inserted.\n"
        "The method is robust.\n"
        "The method is robust.\n"
    )
    resolved = service.resolve_feedback_range(
        content=shifted,
        selected_text="The method is robust.",
        start=first_start,
        end=first_end,
        anchor=anchor,
    )

    assert resolved is not None
    assert shifted[resolved.start:resolved.end] == "The method is robust."
    assert resolved.start == shifted.index("The method is robust.")


def test_resolve_section_by_offset_prefers_nearest_heading_level() -> None:
    content = (
        "\\section{A}\n"
        "Alpha.\n"
        "\\subsection{B}\n"
        "Bravo paragraph.\n"
        "\\section{C}\n"
        "Charlie.\n"
    )
    offset = content.index("Bravo")
    section = service.resolve_section_by_offset(content, offset)

    assert section.title == "B"
    assert section.level == "subsection"
    assert content[section.start:section.end].startswith("\\subsection{B}")
    assert "\\section{C}" not in content[section.start:section.end]


@pytest.mark.asyncio
async def test_rewrite_with_feedback_selection_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    content = "\\section{Intro}\nOriginal sentence.\n"
    start = content.index("Original")
    end = start + len("Original sentence.")

    monkeypatch.setattr(service, "_pick_model_id", lambda _requested: "fake-model")

    async def _fake_invoke(prompt: str, *, model_id: str) -> tuple[str, dict]:
        assert "Original sentence." in prompt
        assert model_id == "fake-model"
        return (
            '{"rewritten_text":"Updated sentence.","changes_summary":"polished"}',
            {"rewritten_text": "Updated sentence.", "changes_summary": "polished"},
        )

    monkeypatch.setattr(service, "_invoke_rewrite", _fake_invoke)

    result = await service.rewrite_with_feedback(
        content=content,
        comment="Make it clearer.",
        selected_text="Original sentence.",
        selection_start=start,
        selection_end=end,
        scope="selection",
    )

    assert result["scope"] == "selection"
    assert result["target_start"] == start
    assert result["target_end"] == end
    assert result["rewritten_text"] == "Updated sentence."


@pytest.mark.asyncio
async def test_rewrite_with_feedback_section_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    content = (
        "\\section{Intro}\n"
        "Original sentence.\n"
        "\\section{Next}\n"
        "Another section.\n"
    )
    start = content.index("Original")
    end = start + len("Original sentence.")

    monkeypatch.setattr(service, "_pick_model_id", lambda _requested: "fake-model")

    async def _fake_invoke(prompt: str, *, model_id: str) -> tuple[str, dict]:
        assert "\\section{Intro}" in prompt
        assert "Original sentence." in prompt
        assert model_id == "fake-model"
        return (
            '{"rewritten_section":"\\\\section{Intro}\\nRewritten intro.\\n","changes_summary":"rewrote section"}',
            {
                "rewritten_section": "\\section{Intro}\nRewritten intro.\n",
                "changes_summary": "rewrote section",
            },
        )

    monkeypatch.setattr(service, "_invoke_rewrite", _fake_invoke)

    result = await service.rewrite_with_feedback(
        content=content,
        comment="Rewrite this section.",
        selected_text="Original sentence.",
        selection_start=start,
        selection_end=end,
        scope="section",
    )

    assert result["scope"] == "section"
    assert result["section_title"] == "Intro"
    assert result["target_start"] == 0
    assert result["rewritten_text"].startswith("\\section{Intro}")


@pytest.mark.asyncio
async def test_rewrite_with_feedback_document_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    content = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\section{Intro}\n"
        "Original sentence.\n"
        "\\section{Method}\n"
        "Method sentence.\n"
        "\\end{document}\n"
    )

    monkeypatch.setattr(service, "_pick_model_id", lambda _requested: "fake-model")

    async def _fake_invoke(prompt: str, *, model_id: str) -> tuple[str, dict]:
        assert "完整主稿" in prompt
        assert "\\section{Intro}" in prompt
        assert "\\section{Method}" in prompt
        assert model_id == "fake-model"
        return (
            '{"rewritten_document":"\\\\documentclass{article}\\n\\\\begin{document}\\nRewritten full manuscript.\\n\\\\end{document}\\n","changes_summary":"rewrote document"}',
            {
                "rewritten_document": (
                    "\\documentclass{article}\n"
                    "\\begin{document}\n"
                    "Rewritten full manuscript.\n"
                    "\\end{document}\n"
                ),
                "changes_summary": "rewrote document",
            },
        )

    monkeypatch.setattr(service, "_invoke_rewrite", _fake_invoke)

    result = await service.rewrite_with_feedback(
        content=content,
        comment="Make the whole manuscript sound less AI-generated.",
        selected_text=content,
        selection_start=0,
        selection_end=len(content),
        scope="document",
    )

    assert result["scope"] == "document"
    assert result["section_title"] == "全文"
    assert result["section_level"] == "document"
    assert result["target_start"] == 0
    assert result["target_end"] == len(content)
    assert result["rewritten_text"].startswith("\\documentclass{article}")


@pytest.mark.asyncio
async def test_rewrite_with_feedback_document_scope_does_not_require_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "\\documentclass{article}\n\\begin{document}\nOriginal.\n\\end{document}\n"

    monkeypatch.setattr(service, "_pick_model_id", lambda _requested: "fake-model")

    async def _fake_invoke(prompt: str, *, model_id: str) -> tuple[str, dict]:
        assert "完整主稿" in prompt
        assert "Original." in prompt
        assert model_id == "fake-model"
        return (
            '{"rewritten_document":"\\\\documentclass{article}\\n\\\\begin{document}\\nRewritten.\\n\\\\end{document}\\n","changes_summary":"rewrote document"}',
            {
                "rewritten_document": (
                    "\\documentclass{article}\n"
                    "\\begin{document}\n"
                    "Rewritten.\n"
                    "\\end{document}\n"
                ),
                "changes_summary": "rewrote document",
            },
        )

    monkeypatch.setattr(service, "_invoke_rewrite", _fake_invoke)

    result = await service.rewrite_with_feedback(
        content=content,
        comment="整体改得更像研究者写作。",
        selected_text="",
        scope="document",
    )

    assert result["scope"] == "document"
    assert result["resolved_selection_start"] == 0
    assert result["resolved_selection_end"] == len(content)
    assert result["target_start"] == 0
    assert result["target_end"] == len(content)
    assert "Rewritten." in result["rewritten_text"]

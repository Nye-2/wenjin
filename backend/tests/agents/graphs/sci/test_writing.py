"""Tests for SCI writing graph orchestration."""

from __future__ import annotations

import pytest

from src.workspace_features.latex_sync import LatexSyncResult


@pytest.mark.asyncio
async def test_writing_graph_merges_sync_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.graphs.sci.writing import writing_graph

    async def _fake_build_sci_writing_payload(**_kwargs):
        return {
            "section_title": "Introduction",
            "content": "Draft content",
            "outline": ["Background"],
            "references": ["Ref A"],
            "word_count": 123,
            "writing_mode": "llm",
            "output_language": "en",
            "model_id": "mock-model",
            "generation_error": None,
            "generated_at": "2026-04-08T00:00:00+00:00",
        }

    async def _fake_sync_sci_writing_payload(**_kwargs):
        return LatexSyncResult(
            latex_project_id="latex-sci-2",
            main_file="main.tex",
            section_file="sections/introduction.tex",
            section_map={"introduction": "sections/introduction.tex"},
            sync_conflicts=[],
        )

    monkeypatch.setattr(
        "src.agents.graphs.sci.writing.build_sci_writing_payload",
        _fake_build_sci_writing_payload,
    )
    monkeypatch.setattr(
        "src.agents.graphs.sci.writing.sync_sci_writing_payload",
        _fake_sync_sci_writing_payload,
    )

    result = await writing_graph(
        {},
        {
            "workspace_id": "ws-sci",
            "workspace_name": "SCI Workspace",
            "workspace_description": "desc",
            "params": {"paper_title": "Paper Title", "section_type": "introduction"},
        },
    )

    assert result["section_title"] == "Introduction"
    assert result["content"] == "Draft content"
    assert result["latex_project_id"] == "latex-sci-2"
    assert result["section_file"] == "sections/introduction.tex"
    assert result["section_map"] == {"introduction": "sections/introduction.tex"}

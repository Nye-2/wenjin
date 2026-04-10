"""Tests for SCI framework-outline graph orchestration."""

from __future__ import annotations

import pytest

from src.workspace_features.latex_sync import LatexSyncResult


@pytest.mark.asyncio
async def test_framework_outline_graph_merges_sync_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.graphs.sci.framework_outline import framework_outline_graph

    async def _fake_build_framework_outline_payload(**_kwargs):
        return {
            "schema_version": "v1",
            "document_type": "framework_outline",
            "output_language": "en",
            "paper_title": "Paper Title",
            "topic": "Agent Planning",
            "abstract": "Abstract",
            "keywords": ["agents"],
            "sections": [{"title": "Introduction", "focus": "Background"}],
            "contributions": ["Contribution A"],
            "context_artifact_ids": ["artifact-1"],
            "context_artifacts_count": 1,
            "generated_at": "2026-04-08T00:00:00+00:00",
            "model_id": "mock-model",
            "generation_error": None,
            "generation_mode": "llm",
        }

    async def _fake_sync_sci_framework_outline_payload(**_kwargs):
        return LatexSyncResult(
            latex_project_id="latex-sci-1",
            main_file="main.tex",
            section_map={"introduction": "sections/introduction.tex"},
            sync_conflicts=[
                {"logical_key": "introduction", "path": "sections/introduction.tex", "reason": "user_modified"}
            ],
        )

    monkeypatch.setattr(
        "src.agents.graphs.sci.framework_outline.build_framework_outline_payload",
        _fake_build_framework_outline_payload,
    )
    monkeypatch.setattr(
        "src.agents.graphs.sci.framework_outline.sync_sci_framework_outline_payload",
        _fake_sync_sci_framework_outline_payload,
    )

    result = await framework_outline_graph(
        {},
        {
            "workspace_id": "ws-sci",
            "workspace_name": "SCI Workspace",
            "workspace_description": "desc",
            "params": {"paper_title": "Paper Title", "topic": "Agent Planning"},
        },
    )

    assert result["paper_title"] == "Paper Title"
    assert result["topic"] == "Agent Planning"
    assert result["latex_project_id"] == "latex-sci-1"
    assert result["main_file"] == "main.tex"
    assert result["section_map"] == {"introduction": "sections/introduction.tex"}
    assert result["sync_conflicts"] == [
        {"logical_key": "introduction", "path": "sections/introduction.tex", "reason": "user_modified"}
    ]

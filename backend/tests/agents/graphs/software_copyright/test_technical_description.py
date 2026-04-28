"""Tests for software technical-description graph orchestration."""

from __future__ import annotations

import pytest

from src.workspace_features.latex_sync import LatexSyncResult


@pytest.mark.asyncio
async def test_technical_description_graph_merges_sync_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.graphs.software_copyright.technical_description import technical_description_graph

    async def _fake_build_technical_description_payload(**_kwargs):
        return {
            "software_profile": {"software_name": "Agent Studio", "version": "V2.1"},
            "sections": {"system_overview": {"title": "系统概述", "content": "内容"}},
            "generation_mode": "llm",
            "model_id": "mock-model",
            "generation_error": None,
            "generated_at": "2026-04-08T00:00:00+00:00",
            "upgrade": {"auto_upgrade": False, "can_regenerate_with_llm": False, "last_error": None},
        }

    async def _fake_sync_software_technical_description_payload(**_kwargs):
        return LatexSyncResult(
            latex_project_id="latex-soft-1",
            main_file="main.tex",
            section_map={"system_overview": "sections/01_system_overview.tex"},
            file_changes=[],
        )

    monkeypatch.setattr(
        "src.agents.graphs.software_copyright.technical_description.build_technical_description_payload",
        _fake_build_technical_description_payload,
    )
    monkeypatch.setattr(
        "src.agents.graphs.software_copyright.technical_description.sync_software_technical_description_payload",
        _fake_sync_software_technical_description_payload,
    )

    result = await technical_description_graph(
        {},
        {
            "workspace_id": "ws-soft",
            "workspace_name": "Software Workspace",
            "workspace_description": "desc",
            "params": {"software_name": "Agent Studio", "version": "V2.1"},
        },
    )

    assert result["software_profile"]["software_name"] == "Agent Studio"
    assert result["latex_project_id"] == "latex-soft-1"
    assert result["main_file"] == "main.tex"
    assert result["section_map"] == {"system_overview": "sections/01_system_overview.tex"}

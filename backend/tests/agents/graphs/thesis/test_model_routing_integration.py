"""Model routing propagation tests for thesis feature graphs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.graphs.thesis import (
    compile_export,
    deep_research,
    figure_generation,
    literature_management,
    opening_research,
    thesis_writing,
)


@pytest.mark.asyncio
async def test_deep_research_graph_propagates_model_id():
    payload = {
        "workspace_name": "topic",
        "workspace_discipline": "cs",
        "params": {"model_id": "user-model"},
    }
    with patch.object(
        deep_research,
        "_resolve_research_model",
        return_value="resolved-model",
    ) as resolve_model, patch.object(
        deep_research,
        "_phase1_discovery",
        new_callable=AsyncMock,
        return_value={"seminal_works": [], "recent_works": [], "trends": []},
    ) as phase1, patch.object(
        deep_research,
        "_phase2_gap_mining",
        new_callable=AsyncMock,
        return_value=[],
    ) as phase2, patch.object(
        deep_research,
        "_phase3_synthesis",
        new_callable=AsyncMock,
        return_value=[],
    ) as phase3, patch.object(
        deep_research,
        "_phase4_cross_validate",
        new_callable=AsyncMock,
        return_value=None,
    ) as phase4:
        result = await deep_research.deep_research_graph({}, payload)

    resolve_model.assert_called_once_with("user-model")
    assert phase1.await_args.kwargs["model_id"] == "resolved-model"
    assert phase2.await_args.kwargs["model_id"] == "resolved-model"
    assert phase3.await_args.kwargs["model_id"] == "resolved-model"
    assert phase4.await_args.kwargs["model_id"] == "resolved-model"
    assert result["model_id"] == "resolved-model"


@pytest.mark.asyncio
async def test_opening_research_graph_propagates_model_id():
    payload = {
        "workspace_id": "ws-1",
        "workspace_description": "desc",
        "params": {"topic": "topic", "model_id": "picked-model"},
    }
    with patch.object(
        opening_research,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        opening_research,
        "_load_literature",
        new_callable=AsyncMock,
        return_value=[{"title": "Paper A", "year": 2024}],
    ), patch.object(
        opening_research,
        "_analyze_research_status",
        new_callable=AsyncMock,
        return_value={"research_status": "ok"},
    ) as step1, patch.object(
        opening_research,
        "_plan_methodology",
        new_callable=AsyncMock,
        return_value={"objectives": ["obj"]},
    ) as step2, patch.object(
        opening_research,
        "_generate_report_sections",
        new_callable=AsyncMock,
        return_value=[{"title": "A", "content": "B", "source": "llm"}],
    ) as step3:
        result = await opening_research.opening_research_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert step1.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert step2.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert step3.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert result["model_id"] == "resolved-writing-model"


@pytest.mark.asyncio
async def test_figure_generation_graph_propagates_model_id():
    payload = {
        "params": {
            "figure_type": "flowchart",
            "description": "desc",
            "model_id": "picked-model",
        }
    }
    with patch.object(
        figure_generation,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        figure_generation,
        "_plan_figure",
        new_callable=AsyncMock,
        return_value={"recommended_strategy": "python"},
    ) as plan_figure, patch.object(
        figure_generation,
        "_generate_figure_code",
        new_callable=AsyncMock,
        return_value="print('ok')",
    ) as gen_code, patch.object(
        figure_generation,
        "generate_figure",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            success=True,
            figure_path="/mnt/user-data/execution/mermaid/test.svg",
            format="svg",
            error=None,
        ),
    ) as execute_figure:
        result = await figure_generation.figure_generation_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert plan_figure.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert gen_code.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert execute_figure.await_args.kwargs["strategy"] == "python"
    assert result["model_id"] == "resolved-writing-model"
    assert result["strategy"] == "python"
    assert result["render_data"]["file_path"] == "/mnt/user-data/execution/mermaid/test.svg"


@pytest.mark.asyncio
async def test_compile_export_graph_propagates_model_id():
    payload = {
        "workspace_id": "ws-1",
        "workspace_name": "topic",
        "workspace_description": "desc",
        "params": {"model_id": "picked-model"},
    }
    with patch.object(
        compile_export,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        compile_export,
        "_load_outline_context",
        new_callable=AsyncMock,
        return_value={"paper_title": "topic"},
    ), patch.object(
        compile_export,
        "_load_chapter_summaries",
        new_callable=AsyncMock,
        return_value=[{"title": "Chapter 1", "summary": "summary"}],
    ), patch.object(
        compile_export,
        "_load_literature_count",
        new_callable=AsyncMock,
        return_value=7,
    ), patch.object(
        compile_export,
        "_review_consistency",
        new_callable=AsyncMock,
        return_value={"issues": [], "overall_assessment": "ok"},
    ) as review_consistency, patch.object(
        compile_export,
        "_generate_abstract_keywords",
        new_callable=AsyncMock,
        return_value={
            "abstract_zh": "a",
            "keywords_zh": ["k1"],
            "abstract_en": "b",
            "keywords_en": ["k2"],
        },
    ) as gen_abstract:
        with patch.object(
            compile_export,
            "build_compile_payload",
            new_callable=AsyncMock,
            return_value={
                "latex_content": "\\documentclass{article}",
                "bib_content": "",
                "source_summary": {"chapter_count": 1},
                "template": "default",
                "compiler": "xelatex",
                "bibliography_style": "gbt7714",
                "paper_title": "topic",
            },
        ) as build_compile, patch.object(
            compile_export,
            "compile_thesis_payload",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                latex_project_id="latex-thesis-1",
                main_file="main.tex",
                compile_status="success",
                pdf_path="/mnt/user-data/execution/latex_compile/test.pdf",
                pdf_url="/api/threads/default/artifacts/mnt/user-data/execution/latex_compile/test.pdf",
                pdf_endpoint="/api/threads/default/artifacts/mnt/user-data/execution/latex_compile/test.pdf",
                page_count=12,
                compile_error=None,
                compile_logs="ok",
                sync_conflicts=[],
            ),
        ) as compile_thesis:
            result = await compile_export.compile_export_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert review_consistency.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert gen_abstract.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert build_compile.await_args.kwargs["workspace_id"] == "ws-1"
    assert compile_thesis.await_args.kwargs["workspace_id"] == "ws-1"
    assert result["model_id"] == "resolved-writing-model"
    assert result["compile_status"] == "success"


@pytest.mark.asyncio
async def test_literature_management_graph_propagates_model_id():
    payload = {
        "workspace_id": "ws-1",
        "workspace_name": "topic",
        "params": {"topic": "topic", "model_id": "picked-model"},
    }
    with patch.object(
        literature_management,
        "_resolve_management_model",
        return_value="resolved-chat-model",
    ) as resolve_model, patch.object(
        literature_management,
        "_load_literature",
        new_callable=AsyncMock,
        return_value=[
            {
                "title": "Paper A",
                "year": 2024,
                "source": "scopus",
                "citations": 12,
                "abstract": "abs",
                "doi": "10.1/x",
            }
        ],
    ), patch.object(
        literature_management,
        "_llm_analyze_literature",
        new_callable=AsyncMock,
        return_value={
            "topic_clusters": [{"name": "cluster", "papers_count": 1}],
            "quality_assessment": "good",
            "recommendations": ["keep"],
        },
    ) as llm_analyze:
        result = await literature_management.literature_management_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert llm_analyze.await_args.kwargs["model_id"] == "resolved-chat-model"
    assert result["model_id"] == "resolved-chat-model"


@pytest.mark.asyncio
async def test_thesis_writing_graph_review_action_propagates_model_id():
    payload = {
        "params": {
            "action": "review_section",
            "section_title": "S1",
            "section_content": "content",
            "model_id": "picked-model",
        }
    }
    with patch.object(
        thesis_writing,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        thesis_writing,
        "_handle_review_section",
        new_callable=AsyncMock,
        return_value={
            "action": "review_section",
            "model_id": "resolved-writing-model",
        },
    ) as handle_review:
        result = await thesis_writing.thesis_writing_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert handle_review.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert result["model_id"] == "resolved-writing-model"


@pytest.mark.asyncio
async def test_thesis_writing_graph_generate_outline_action_propagates_model_id():
    payload = {
        "params": {
            "action": "generate_outline",
            "paper_title": "A",
            "target_words": 20000,
            "model_id": "picked-model",
        }
    }
    with patch.object(
        thesis_writing,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        thesis_writing,
        "_handle_generate_outline",
        new_callable=AsyncMock,
        return_value={
            "action": "generate_outline",
            "model_id": "resolved-writing-model",
        },
    ) as handle_outline:
        result = await thesis_writing.thesis_writing_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert handle_outline.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert result["model_id"] == "resolved-writing-model"


@pytest.mark.asyncio
async def test_thesis_writing_graph_write_chapter_action_propagates_model_id():
    payload = {
        "params": {
            "action": "write_chapter",
            "paper_title": "A",
            "chapter_index": 0,
            "chapter_title": "Intro",
            "model_id": "picked-model",
        }
    }
    with patch.object(
        thesis_writing,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        thesis_writing,
        "_handle_write_chapter",
        new_callable=AsyncMock,
        return_value={
            "action": "write_chapter",
            "model_id": "resolved-writing-model",
        },
    ) as handle_write:
        result = await thesis_writing.thesis_writing_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert handle_write.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert result["model_id"] == "resolved-writing-model"


@pytest.mark.asyncio
async def test_thesis_writing_graph_default_action_propagates_model_id():
    payload = {
        "params": {
            "section_title": "S1",
            "section_content": "content",
            "model_id": "picked-model",
        }
    }
    with patch.object(
        thesis_writing,
        "_resolve_writing_model",
        return_value="resolved-writing-model",
    ) as resolve_model, patch.object(
        thesis_writing,
        "_handle_review_and_revise",
        new_callable=AsyncMock,
        return_value={
            "action": "review_and_revise",
            "model_id": "resolved-writing-model",
        },
    ) as handle_default:
        result = await thesis_writing.thesis_writing_graph({}, payload)

    resolve_model.assert_called_once_with("picked-model")
    assert handle_default.await_args.kwargs["model_id"] == "resolved-writing-model"
    assert result["model_id"] == "resolved-writing-model"

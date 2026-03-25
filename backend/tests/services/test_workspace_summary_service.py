"""Tests for workspace summary service."""

from unittest.mock import AsyncMock

import pytest

from src.services.workspace_summary_service import WorkspaceSummaryService


@pytest.mark.asyncio
async def test_summary_prioritizes_failed_module_and_generates_risk():
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "deep_research", "status": "completed", "summary": {}},
                {"id": "literature_management", "status": "completed", "summary": {"total": 12, "core": 5}},
                {"id": "opening_research", "status": "failed", "summary": {}},
                {"id": "thesis_writing", "status": "not_started", "summary": {}},
                {"id": "figure_generation", "status": "not_started", "summary": {}},
                {"id": "compile_export", "status": "not_started", "summary": {}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(
        return_value={
            "items": [
                {
                    "title": "开题调研",
                    "summary": "运行失败",
                    "kind": "feature_task",
                    "occurred_at": "2026-03-23T09:00:00+00:00",
                }
            ]
        }
    )
    service = WorkspaceSummaryService(
        AsyncMock(),
        dashboard_service=dashboard_service,
        activity_service=activity_service,
    )

    result = await service.get_summary(
        "ws-1",
        workspace_type="thesis",
        user_id="user-1",
    )

    assert result["current_phase"]["feature_id"] == "opening_research"
    assert result["next_step"]["feature_id"] == "opening_research"
    assert result["risk_items"][0]["tone"] == "danger"
    assert "阻塞" in result["headline"]


@pytest.mark.asyncio
async def test_summary_builds_progress_and_recommended_actions_for_in_progress_module():
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "literature_search", "status": "completed", "summary": {"results_count": 18}},
                {"id": "paper_analysis", "status": "in_progress", "summary": {"analysis_count": 1}},
                {"id": "writing", "status": "not_started", "summary": {"drafts_count": 0}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    service = WorkspaceSummaryService(
        AsyncMock(),
        dashboard_service=dashboard_service,
        activity_service=activity_service,
    )

    result = await service.get_summary(
        "ws-2",
        workspace_type="sci",
        user_id="user-2",
    )

    assert result["progress"]["completed"] == 1
    assert result["progress"]["in_progress"] == 1
    assert result["progress"]["total"] == 7
    assert result["progress"]["percent"] == 21
    assert result["current_phase"]["feature_id"] == "paper_analysis"
    assert result["recommended_actions"][0]["feature_id"] == "paper_analysis"
    assert result["recommended_actions"][1]["feature_id"] == "writing"


@pytest.mark.asyncio
async def test_summary_warns_when_thesis_literature_is_thin():
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "deep_research", "status": "completed", "summary": {"ideas_count": 3}},
                {"id": "literature_management", "status": "in_progress", "summary": {"total": 2, "core": 1}},
                {"id": "opening_research", "status": "not_started", "summary": {}},
                {"id": "thesis_writing", "status": "not_started", "summary": {}},
                {"id": "figure_generation", "status": "not_started", "summary": {}},
                {"id": "compile_export", "status": "not_started", "summary": {}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    service = WorkspaceSummaryService(
        AsyncMock(),
        dashboard_service=dashboard_service,
        activity_service=activity_service,
    )

    result = await service.get_summary(
        "ws-3",
        workspace_type="thesis",
        user_id="user-3",
    )

    assert result["current_phase"]["feature_id"] == "literature_management"
    assert result["risk_items"][0]["tone"] == "warning"
    assert "文献储备偏少" in result["risk_items"][0]["title"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_type", "modules", "expected_risk_id"),
    [
        (
            "proposal",
            [
                {"id": "proposal_outline", "status": "completed", "summary": {"count": 1}},
                {"id": "background_research", "status": "not_started", "summary": {"count": 0}},
                {"id": "experiment_design", "status": "not_started", "summary": {"count": 0}},
            ],
            "proposal:background_research",
        ),
        (
            "patent",
            [
                {"id": "patent_outline", "status": "completed", "summary": {"has_outline": True}},
                {"id": "prior_art_search", "status": "not_started", "summary": {"reports_count": 0}},
            ],
            "patent:prior_art_search",
        ),
        (
            "software_copyright",
            [
                {"id": "copyright_materials", "status": "completed", "summary": {"has_materials": True}},
                {"id": "technical_description", "status": "not_started", "summary": {"has_description": False}},
            ],
            "software_copyright:technical_description",
        ),
    ],
)
async def test_summary_adds_workspace_specific_warning_risks(
    workspace_type: str,
    modules: list[dict[str, object]],
    expected_risk_id: str,
):
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={"modules": modules, "recent_artifacts": []}
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    service = WorkspaceSummaryService(
        AsyncMock(),
        dashboard_service=dashboard_service,
        activity_service=activity_service,
    )

    result = await service.get_summary(
        "ws-risk",
        workspace_type=workspace_type,
        user_id="user-risk",
    )

    assert any(item["id"] == expected_risk_id for item in result["risk_items"])

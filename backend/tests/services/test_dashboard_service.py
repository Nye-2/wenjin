"""Tests for dashboard service workspace-specific module aggregation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.dashboard_service import DashboardService


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _ScalarOneOrNoneResult:
    def __init__(self, item):
        self._item = item

    def scalar_one_or_none(self):
        return self._item


@pytest.mark.asyncio
async def test_get_dashboard_sci_uses_workspace_specific_modules():
    db = AsyncMock()
    service = DashboardService(db)

    service._get_sci_literature_search_status = AsyncMock(
        return_value={
            "id": "literature_search",
            "status": "completed",
            "summary": {"results_count": 6, "last_task_status": "success"},
        }
    )
    service._get_sci_paper_analysis_status = AsyncMock(
        return_value={
            "id": "paper_analysis",
            "status": "in_progress",
            "summary": {"analysis_count": 1},
        }
    )
    service._get_sci_writing_status = AsyncMock(
        return_value={
            "id": "writing",
            "status": "not_started",
            "summary": {"drafts_count": 0},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    # Thesis module methods should not be called.
    service._get_deep_research_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_literature_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_opening_research_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_thesis_writing_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_figure_generation_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_compile_export_status = AsyncMock(side_effect=AssertionError("unexpected call"))

    result = await service.get_dashboard("ws-1", workspace_type="sci")

    assert [module["id"] for module in result["modules"]] == [
        "literature_search",
        "paper_analysis",
        "writing",
    ]


@pytest.mark.asyncio
async def test_get_dashboard_proposal_uses_workspace_specific_modules():
    db = AsyncMock()
    service = DashboardService(db)

    service._get_proposal_outline_status = AsyncMock(
        return_value={
            "id": "proposal_outline",
            "status": "completed",
            "summary": {"has_outline": True, "count": 1},
        }
    )
    service._get_background_research_status = AsyncMock(
        return_value={
            "id": "background_research",
            "status": "in_progress",
            "summary": {"count": 2},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-2", workspace_type="proposal")

    assert [module["id"] for module in result["modules"]] == [
        "proposal_outline",
        "background_research",
    ]


@pytest.mark.asyncio
async def test_get_dashboard_software_copyright_uses_workspace_specific_modules():
    db = AsyncMock()
    service = DashboardService(db)

    service._get_software_copyright_materials_status = AsyncMock(
        return_value={
            "id": "copyright_materials",
            "status": "completed",
            "summary": {"has_materials": True},
        }
    )
    service._get_technical_description_status = AsyncMock(
        return_value={
            "id": "technical_description",
            "status": "in_progress",
            "summary": {"has_description": False},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-3", workspace_type="software_copyright")

    assert [module["id"] for module in result["modules"]] == [
        "copyright_materials",
        "technical_description",
    ]


@pytest.mark.asyncio
async def test_get_dashboard_patent_uses_workspace_specific_modules():
    db = AsyncMock()
    service = DashboardService(db)

    service._get_patent_outline_status = AsyncMock(
        return_value={
            "id": "patent_outline",
            "status": "completed",
            "summary": {"has_outline": True},
        }
    )
    service._get_prior_art_search_status = AsyncMock(
        return_value={
            "id": "prior_art_search",
            "status": "not_started",
            "summary": {"reports_count": 0},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-4", workspace_type="patent")

    assert [module["id"] for module in result["modules"]] == [
        "patent_outline",
        "prior_art_search",
    ]


@pytest.mark.asyncio
async def test_opening_research_status_filters_by_opening_handler():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarsResult([]),
            _ScalarOneOrNoneResult(None),
        ]
    )
    service = DashboardService(db)
    service._count_running_workspace_feature_tasks = AsyncMock(return_value=0)

    await service._get_opening_research_status("ws-1")

    statement = db.execute.call_args_list[0].args[0]
    params = statement.compile().params
    assert "thesis.opening_research" in params.values()


@pytest.mark.asyncio
async def test_compile_export_status_failed_compile_not_marked_completed():
    db = AsyncMock()
    service = DashboardService(db)
    service._count_running_workspace_feature_tasks = AsyncMock(return_value=0)
    db.execute = AsyncMock(
        return_value=_ScalarOneOrNoneResult(
            SimpleNamespace(
                content={"compile_status": "failed"},
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
            )
        )
    )

    result = await service._get_compile_export_status("ws-1")

    assert result["id"] == "compile_export"
    assert result["status"] == "failed"
    assert result["summary"]["compile_status"] == "failed"
    assert result["summary"]["last_compile_success"] is False
    assert result["summary"]["last_compile"]


@pytest.mark.asyncio
async def test_compile_export_status_success_compile_marked_completed():
    db = AsyncMock()
    service = DashboardService(db)
    service._count_running_workspace_feature_tasks = AsyncMock(return_value=0)
    db.execute = AsyncMock(
        return_value=_ScalarOneOrNoneResult(
            SimpleNamespace(
                content={"compile_status": "success"},
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
            )
        )
    )

    result = await service._get_compile_export_status("ws-1")

    assert result["id"] == "compile_export"
    assert result["status"] == "completed"
    assert result["summary"]["compile_status"] == "success"
    assert result["summary"]["last_compile_success"] is True


@pytest.mark.asyncio
async def test_status_from_count_and_running_returns_failed_when_latest_task_failed():
    """When no artifacts exist and the latest task is failed, status must be 'failed'."""
    db = AsyncMock()
    service = DashboardService(db)

    result = await service._status_from_count_and_running(
        count=0,
        running_count=0,
        latest_task_status="failed",
    )
    assert result == "failed"


@pytest.mark.asyncio
async def test_status_from_count_and_running_prefers_in_progress_over_failed():
    """Running tasks take priority over a previous failure."""
    db = AsyncMock()
    service = DashboardService(db)

    result = await service._status_from_count_and_running(
        count=0,
        running_count=1,
        latest_task_status="failed",
    )
    assert result == "in_progress"


@pytest.mark.asyncio
async def test_status_from_count_and_running_completed_overrides_failed():
    """Existing artifacts mean completed even if latest task failed."""
    db = AsyncMock()
    service = DashboardService(db)

    result = await service._status_from_count_and_running(
        count=3,
        running_count=0,
        latest_task_status="failed",
    )
    assert result == "completed"


@pytest.mark.asyncio
async def test_sci_literature_search_shows_failed_when_latest_task_failed():
    """Sci literature_search module should surface failed status from task history."""
    db = AsyncMock()
    service = DashboardService(db)
    service._count_artifacts = AsyncMock(return_value=0)
    service._count_running_workspace_feature_tasks = AsyncMock(return_value=0)
    service._get_latest_workspace_feature_task_status = AsyncMock(return_value="failed")

    result = await service._get_sci_literature_search_status("ws-1")

    assert result["status"] == "failed"

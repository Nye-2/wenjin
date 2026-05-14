"""Tests for dashboard service workspace-specific module aggregation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.dashboard_service import DashboardService
from src.workspace_features import CANONICAL_WORKSPACE_TYPES, list_workspace_features


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


def test_dashboard_status_builders_cover_workspace_registry() -> None:
    service = DashboardService(AsyncMock())
    expected_method_names = {
        f"_get_{feature.id}_status"
        for workspace_type in CANONICAL_WORKSPACE_TYPES
        for feature in list_workspace_features(workspace_type)
    }
    missing_methods = [
        method_name
        for method_name in sorted(expected_method_names)
        if not hasattr(service, method_name)
    ]
    assert missing_methods == []


@pytest.mark.asyncio
async def test_get_dashboard_sci_uses_workspace_specific_modules():
    db = AsyncMock()
    service = DashboardService(db)

    service._get_literature_search_status = AsyncMock(
        return_value={
            "id": "literature_search",
            "status": "completed",
            "summary": {"results_count": 6, "last_task_status": "success"},
        }
    )
    service._get_paper_analysis_status = AsyncMock(
        return_value={
            "id": "paper_analysis",
            "status": "in_progress",
            "summary": {"analysis_count": 1},
        }
    )
    service._get_writing_status = AsyncMock(
        return_value={
            "id": "writing",
            "status": "not_started",
            "summary": {"drafts_count": 0},
        }
    )
    service._get_literature_review_status = AsyncMock(
        return_value={
            "id": "literature_review",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_framework_outline_status = AsyncMock(
        return_value={
            "id": "framework_outline",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_figure_generation_status = AsyncMock(
        return_value={
            "id": "figure_generation",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_peer_review_status = AsyncMock(
        return_value={
            "id": "peer_review",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_journal_recommend_status = AsyncMock(
        return_value={
            "id": "journal_recommend",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    # Thesis module methods should not be called.
    service._get_deep_research_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_literature_management_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_opening_research_status = AsyncMock(side_effect=AssertionError("unexpected call"))
    service._get_thesis_writing_status = AsyncMock(side_effect=AssertionError("unexpected call"))

    result = await service.get_dashboard("ws-1", workspace_type="sci")

    assert [module["id"] for module in result["modules"]] == [
        "literature_search",
        "paper_analysis",
        "writing",
        "literature_review",
        "framework_outline",
        "figure_generation",
        "peer_review",
        "journal_recommend",
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
    service._get_experiment_design_status = AsyncMock(
        return_value={
            "id": "experiment_design",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_figure_generation_status = AsyncMock(
        return_value={
            "id": "figure_generation",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-2", workspace_type="proposal")

    assert [module["id"] for module in result["modules"]] == [
        "proposal_outline",
        "background_research",
        "experiment_design",
        "figure_generation",
    ]


@pytest.mark.asyncio
async def test_get_dashboard_software_copyright_uses_workspace_specific_modules():
    db = AsyncMock()
    service = DashboardService(db)

    service._get_copyright_materials_status = AsyncMock(
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
    service._get_figure_generation_status = AsyncMock(
        return_value={
            "id": "figure_generation",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-3", workspace_type="software_copyright")

    assert [module["id"] for module in result["modules"]] == [
        "copyright_materials",
        "technical_description",
        "figure_generation",
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
    service._get_figure_generation_status = AsyncMock(
        return_value={
            "id": "figure_generation",
            "status": "not_started",
            "summary": {"count": 0},
        }
    )
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-4", workspace_type="patent")

    assert [module["id"] for module in result["modules"]] == [
        "patent_outline",
        "prior_art_search",
        "figure_generation",
    ]


@pytest.mark.asyncio
async def test_get_dashboard_raises_when_workspace_type_missing():
    db = AsyncMock()
    db.execute.return_value = _ScalarOneOrNoneResult(None)
    service = DashboardService(db)

    with pytest.raises(ValueError, match="Workspace not found: missing-ws"):
        await service.get_dashboard("missing-ws")


@pytest.mark.asyncio
async def test_opening_research_status_runs_without_legacy_skill_filter():
    """The legacy skill → feature mapping is gone, so the dashboard query no
    longer narrows by ``created_by_skill``.  This test ensures the query still
    completes (broadened artifact scan) — refining per-feature attribution is
    deferred until artifacts carry a capability_id reference.
    """
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarsResult([]),
            _ScalarOneOrNoneResult(None),
        ]
    )
    service = DashboardService(db)
    service._count_running_feature_executions = AsyncMock(return_value=0)

    await service._get_opening_research_status("ws-1")

    statement = db.execute.call_args_list[0].args[0]
    params = statement.compile().params
    assert not any(
        value == "literature-reviewer"
        or (isinstance(value, list) and "literature-reviewer" in value)
        for value in params.values()
    )

@pytest.mark.asyncio
async def test_deep_research_status_uses_feature_execution_history():
    """Deep research status should resolve from canonical feature executions."""
    db = AsyncMock()
    service = DashboardService(db)
    service._count_running_feature_executions = AsyncMock(return_value=1)
    service._get_latest_feature_execution_status = AsyncMock(return_value="running")
    service._get_latest_artifact = AsyncMock(
        return_value=SimpleNamespace(
            content={
                "ideas": [{"title": "Idea A"}, {"title": "Idea B"}],
            }
        )
    )
    service._count_artifacts = AsyncMock(return_value=1)

    result = await service._get_deep_research_status("ws-1")

    assert result["id"] == "deep_research"
    assert result["status"] == "in_progress"
    assert result["summary"]["reports_count"] == 1
    assert result["summary"]["ideas_count"] == 2
    assert result["summary"]["last_task_status"] == "running"
    service._count_running_feature_executions.assert_awaited_once_with(
        "ws-1",
        "deep_research",
    )
    service._get_latest_feature_execution_status.assert_awaited_once_with(
        "ws-1",
        "deep_research",
    )


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
    service._count_running_feature_executions = AsyncMock(return_value=0)
    service._get_latest_feature_execution_status = AsyncMock(return_value="failed")

    result = await service._get_literature_search_status("ws-1")

    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_sci_sidecar_statuses_include_latest_artifact_metrics():
    """SCI sidecar modules should surface artifact-derived summary metrics."""
    db = AsyncMock()
    service = DashboardService(db)
    service._count_artifacts = AsyncMock(return_value=1)
    service._count_running_feature_executions = AsyncMock(return_value=0)
    service._get_latest_feature_execution_status = AsyncMock(return_value="success")

    latest_artifacts = [
        SimpleNamespace(
            content={
                "sections": [{"title": "Background"}, {"title": "Methods"}],
                "research_gaps": ["Gap A"],
                "key_papers": [{"title": "Paper A"}],
            }
        ),
        SimpleNamespace(
            content={
                "sections": [{"title": "Introduction"}, {"title": "Method"}],
                "keywords": ["llm", "planning", "agent"],
            }
        ),
        SimpleNamespace(
            content={
                "score": 8.2,
                "revision_actions": ["Action A", "Action B"],
            }
        ),
        SimpleNamespace(
            content={
                "journals": [{"name": "Journal A"}, {"name": "Journal B"}],
            }
        ),
    ]
    service._get_latest_artifact = AsyncMock(side_effect=latest_artifacts)

    literature_review = await service._get_literature_review_status("ws-1")
    framework_outline = await service._get_framework_outline_status("ws-1")
    peer_review = await service._get_peer_review_status("ws-1")
    journal_recommend = await service._get_journal_recommend_status("ws-1")

    assert literature_review["summary"]["sections_count"] == 2
    assert literature_review["summary"]["gaps_count"] == 1
    assert literature_review["summary"]["key_papers_count"] == 1
    assert framework_outline["summary"]["sections_count"] == 2
    assert framework_outline["summary"]["keywords_count"] == 3
    assert peer_review["summary"]["score"] == 8.2
    assert peer_review["summary"]["revision_actions_count"] == 2
    assert journal_recommend["summary"]["journals_count"] == 2


@pytest.mark.asyncio
async def test_experiment_design_status_includes_hypotheses_and_variables():
    """Proposal experiment_design module should expose design richness metrics."""
    db = AsyncMock()
    service = DashboardService(db)
    service._count_artifacts = AsyncMock(return_value=1)
    service._count_running_feature_executions = AsyncMock(return_value=0)
    service._get_latest_feature_execution_status = AsyncMock(return_value="success")
    service._get_latest_artifact = AsyncMock(
        return_value=SimpleNamespace(
            content={
                "hypotheses": ["H1", "H2"],
                "variables": [{"name": "x"}, {"name": "y"}, {"name": "z"}],
            }
        )
    )

    result = await service._get_experiment_design_status("ws-2")

    assert result["status"] == "completed"
    assert result["summary"]["hypotheses_count"] == 2
    assert result["summary"]["variables_count"] == 3

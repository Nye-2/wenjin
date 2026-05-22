"""Tests for mission-level workspace summary service."""

from unittest.mock import AsyncMock

import pytest

from src.services.workspace_summary_service import WorkspaceSummaryService
from tests.database.conftest import _Capability as DbCapability


def _make_capability(
    capability_id: str,
    workspace_type: str,
    *,
    order: int = 0,
    display_name: str | None = None,
    description: str = "",
    dashboard_meta: dict | None = None,
) -> DbCapability:
    return DbCapability(
        id=capability_id,
        workspace_type=workspace_type,
        enabled=True,
        display_name=display_name or capability_id,
        description=description,
        intent_description="test",
        trigger_phrases=[],
        required_decisions=[],
        brief_schema={},
        graph_template={},
        ui_meta={"order": order, "icon": "x", "color": "x", "entry_tier": "primary"},
        runtime={"mode": "compute_agentic"},
        dashboard_meta=dashboard_meta or {},
        notes=None,
    )


class _FakeSummaryDataService:
    def __init__(self, capabilities: list[DbCapability]) -> None:
        self.capabilities = list(capabilities)

    async def list_catalog_capabilities(
        self,
        *,
        workspace_type: str | None = None,
        enabled_only: bool = False,
    ):
        return [
            capability
            for capability in self.capabilities
            if (workspace_type is None or capability.workspace_type == workspace_type)
            and (not enabled_only or capability.enabled)
        ]


@pytest.mark.asyncio
async def test_summary_prioritizes_failed_mission_and_generates_risk(test_session):
    capabilities = [
        _make_capability("idea_to_thesis_manuscript", "thesis", order=0, display_name="论文全文"),
        _make_capability("thesis_research_pack", "thesis", order=1, display_name="研究包"),
        _make_capability("thesis_revision_pass", "thesis", order=2, display_name="论文修订"),
    ]
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "idea_to_thesis_manuscript", "status": "completed", "summary": {}},
                {"id": "thesis_research_pack", "status": "failed", "summary": {}},
                {"id": "thesis_revision_pass", "status": "not_started", "summary": {}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    service = WorkspaceSummaryService(
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        dataservice=_FakeSummaryDataService(capabilities),
    )

    result = await service.get_summary("ws-1", workspace_type="thesis", user_id="user-1")

    assert result["current_phase"]["feature_id"] == "thesis_research_pack"
    assert result["next_step"]["feature_id"] == "thesis_research_pack"
    assert result["risk_items"][0]["tone"] == "danger"
    assert "阻塞" in result["headline"]


@pytest.mark.asyncio
async def test_summary_builds_progress_and_recommended_actions_for_missions(test_session):
    capabilities = [
        _make_capability("sci_literature_positioning", "sci", order=0, display_name="文献定位"),
        _make_capability("sci_empirical_package", "sci", order=1, display_name="实证包"),
        _make_capability("research_question_to_paper", "sci", order=2, display_name="论文主稿"),
        _make_capability("sci_revision_for_journal", "sci", order=3, display_name="期刊修订"),
    ]
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "sci_literature_positioning", "status": "completed", "summary": {}},
                {"id": "sci_empirical_package", "status": "in_progress", "summary": {}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    service = WorkspaceSummaryService(
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        dataservice=_FakeSummaryDataService(capabilities),
    )

    result = await service.get_summary("ws-2", workspace_type="sci", user_id="user-2")

    assert result["progress"] == {
        "completed": 1,
        "in_progress": 1,
        "failed": 0,
        "total": 4,
        "percent": 38,
    }
    assert result["current_phase"]["feature_id"] == "sci_empirical_package"
    assert result["recommended_actions"][0]["feature_id"] == "sci_empirical_package"
    assert result["recommended_actions"][1]["feature_id"] == "research_question_to_paper"


@pytest.mark.asyncio
async def test_summary_prefers_active_execution_session(test_session):
    capabilities = [
        _make_capability("sci_literature_positioning", "sci", order=0, display_name="文献定位"),
        _make_capability("research_question_to_paper", "sci", order=1, display_name="论文主稿"),
    ]
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "sci_literature_positioning", "status": "completed", "summary": {}},
                {"id": "research_question_to_paper", "status": "not_started", "summary": {}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    execution_service = AsyncMock()
    execution_service.list_executions = AsyncMock(
        return_value=[
            AsyncMock(
                id="exec-1",
                feature_id="research_question_to_paper",
                status="running",
                result_summary="正在生成论文主稿",
                next_actions=[{"label": "补充摘要约束", "feature_id": "research_question_to_paper"}],
                graph_structure={"nodes": [{"id": "draft", "phase": "draft"}]},
                node_states={"draft": {"status": "running"}},
                updated_at="2026-04-10T12:00:00+00:00",
            )
        ]
    )
    service = WorkspaceSummaryService(
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        execution_service=execution_service,
        dataservice=_FakeSummaryDataService(capabilities),
    )

    result = await service.get_summary("ws-exec", workspace_type="sci", user_id="user-exec")

    assert result["current_phase"]["feature_id"] == "research_question_to_paper"
    assert result["current_phase"]["status"] == "in_progress"
    assert result["next_step"]["title"] == "补充摘要约束"


@pytest.mark.asyncio
async def test_summary_adds_advisory_risk_for_awaiting_user_input(test_session):
    capabilities = [
        _make_capability("technical_route_package", "proposal", order=0, display_name="技术路线包"),
    ]
    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "technical_route_package", "status": "in_progress", "summary": {}},
            ],
            "recent_artifacts": [],
        }
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    execution_service = AsyncMock()
    execution_service.list_executions = AsyncMock(
        return_value=[
            AsyncMock(
                id="exec-2",
                feature_id="technical_route_package",
                status="awaiting_user_input",
                result_summary="需要确认技术路线边界",
                next_actions=[],
                graph_structure={},
                node_states={},
                updated_at="2026-04-10T12:00:00+00:00",
            )
        ]
    )
    service = WorkspaceSummaryService(
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        execution_service=execution_service,
        dataservice=_FakeSummaryDataService(capabilities),
    )

    result = await service.get_summary("ws-advisory", workspace_type="proposal", user_id="user-1")

    assert result["risk_items"][0]["id"] == "advisory:technical_route_package"
    assert result["risk_items"][0]["tone"] == "warning"

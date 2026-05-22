"""Tests for workspace summary service."""

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
    """Build a minimal DbCapability row for summary tests."""
    if dashboard_meta is None:
        dashboard_meta = {"status_kind": capability_id}
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
        ui_meta={"order": order, "icon": "x", "color": "x"},
        runtime={"mode": "chat_only"},
        dashboard_meta=dashboard_meta,
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
async def test_summary_prioritizes_failed_module_and_generates_risk(test_session):
    capabilities = [
        _make_capability("deep_research", "thesis", order=0, display_name="深度调研"),
        _make_capability(
            "literature_management",
            "thesis",
            order=1,
            display_name="文献管理",
        ),
        _make_capability("opening_research", "thesis", order=2, display_name="开题调研"),
        _make_capability("thesis_writing", "thesis", order=3, display_name="论文写作"),
        _make_capability("figure_generation", "thesis", order=4, display_name="图表生成"),
    ]

    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "deep_research", "status": "completed", "summary": {}},
                {"id": "literature_management", "status": "completed", "summary": {"total": 12, "core": 5}},
                {"id": "opening_research", "status": "failed", "summary": {}},
                {"id": "thesis_writing", "status": "not_started", "summary": {}},
                {"id": "figure_generation", "status": "not_started", "summary": {}},
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
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        dataservice=_FakeSummaryDataService(capabilities),
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
async def test_summary_builds_progress_and_recommended_actions_for_in_progress_module(
    test_session,
):
    capabilities = [
        _make_capability("literature_search", "sci", order=0, display_name="文献检索"),
        _make_capability("paper_analysis", "sci", order=1, display_name="论文分析"),
        _make_capability("writing", "sci", order=2, display_name="论文写作"),
        _make_capability("literature_review", "sci", order=3, display_name="文献综述"),
        _make_capability("framework_outline", "sci", order=4, display_name="框架与摘要"),
        _make_capability("figure_generation", "sci", order=5, display_name="图表生成"),
        _make_capability("peer_review", "sci", order=6, display_name="同行评审"),
        _make_capability("journal_recommend", "sci", order=7, display_name="期刊推荐"),
    ]

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
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        dataservice=_FakeSummaryDataService(capabilities),
    )

    result = await service.get_summary(
        "ws-2",
        workspace_type="sci",
        user_id="user-2",
    )

    assert result["progress"]["completed"] == 1
    assert result["progress"]["in_progress"] == 1
    assert result["progress"]["total"] == 8
    assert result["progress"]["percent"] == 19
    assert result["current_phase"]["feature_id"] == "paper_analysis"
    assert result["recommended_actions"][0]["feature_id"] == "paper_analysis"
    assert result["recommended_actions"][1]["feature_id"] == "writing"


@pytest.mark.asyncio
async def test_summary_warns_when_thesis_literature_is_thin(test_session):
    capabilities = [
        _make_capability("deep_research", "thesis", order=0, display_name="深度调研"),
        _make_capability(
            "literature_management",
            "thesis",
            order=1,
            display_name="文献管理",
        ),
        _make_capability("opening_research", "thesis", order=2, display_name="开题调研"),
        _make_capability("thesis_writing", "thesis", order=3, display_name="论文写作"),
        _make_capability("figure_generation", "thesis", order=4, display_name="图表生成"),
    ]

    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "deep_research", "status": "completed", "summary": {"ideas_count": 3}},
                {"id": "literature_management", "status": "in_progress", "summary": {"total": 2, "core": 1}},
                {"id": "opening_research", "status": "not_started", "summary": {}},
                {"id": "thesis_writing", "status": "not_started", "summary": {}},
                {"id": "figure_generation", "status": "not_started", "summary": {}},
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

    result = await service.get_summary(
        "ws-3",
        workspace_type="thesis",
        user_id="user-3",
    )

    assert result["current_phase"]["feature_id"] == "literature_management"
    assert result["risk_items"][0]["tone"] == "warning"
    assert "文献储备偏少" in result["risk_items"][0]["title"]


@pytest.mark.asyncio
async def test_summary_prefers_active_execution_session_for_current_phase_and_next_step(
    test_session,
):
    capabilities = [
        _make_capability("literature_search", "sci", order=0, display_name="文献检索"),
        _make_capability("framework_outline", "sci", order=1, display_name="框架与摘要"),
    ]

    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={
            "modules": [
                {"id": "literature_search", "status": "completed", "summary": {"results_count": 18}},
                {"id": "framework_outline", "status": "not_started", "summary": {}},
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
                feature_id="framework_outline",
                status="running",
                result_summary="正在生成论文框架",
                next_actions=[{"label": "补充摘要约束", "feature_id": "framework_outline"}],
                graph_structure={
                    "nodes": [
                        {"id": "outline__draft", "phase": "outline"},
                    ],
                },
                node_states={
                    "outline__draft": {"status": "running"},
                },
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

    result = await service.get_summary(
        "ws-exec",
        workspace_type="sci",
        user_id="user-exec",
    )

    assert result["current_phase"]["feature_id"] == "framework_outline"
    assert result["current_phase"]["status"] == "in_progress"
    assert result["next_step"]["feature_id"] == "framework_outline"
    assert result["next_step"]["title"] == "补充摘要约束"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_type", "capabilities", "modules", "expected_risk_id"),
    [
        (
            "proposal",
            [
                ("proposal_outline", 0, "申报书大纲"),
                ("background_research", 1, "背景调研"),
                ("experiment_design", 2, "实验设计"),
            ],
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
                ("patent_outline", 0, "专利框架"),
                ("prior_art_search", 1, "现有技术检索"),
            ],
            [
                {"id": "patent_outline", "status": "completed", "summary": {"has_outline": True}},
                {"id": "prior_art_search", "status": "not_started", "summary": {"reports_count": 0}},
            ],
            "patent:prior_art_search",
        ),
        (
            "software_copyright",
            [
                ("copyright_materials", 0, "材料准备"),
                ("technical_description", 1, "技术说明"),
            ],
            [
                {"id": "copyright_materials", "status": "completed", "summary": {"has_materials": True}},
                {"id": "technical_description", "status": "not_started", "summary": {"has_description": False}},
            ],
            "software_copyright:technical_description",
        ),
    ],
)
async def test_summary_adds_workspace_specific_warning_risks(
    test_session,
    workspace_type: str,
    capabilities: list[tuple[str, int, str]],
    modules: list[dict[str, object]],
    expected_risk_id: str,
):
    catalog_capabilities = [
        _make_capability(cap_id, workspace_type, order=order, display_name=name)
        for cap_id, order, name in capabilities
    ]

    dashboard_service = AsyncMock()
    dashboard_service.get_dashboard = AsyncMock(
        return_value={"modules": modules, "recent_artifacts": []}
    )
    activity_service = AsyncMock()
    activity_service.get_activity = AsyncMock(return_value={"items": []})
    service = WorkspaceSummaryService(
        test_session,
        dashboard_service=dashboard_service,
        activity_service=activity_service,
        dataservice=_FakeSummaryDataService(catalog_capabilities),
    )

    result = await service.get_summary(
        "ws-risk",
        workspace_type=workspace_type,
        user_id="user-risk",
    )

    assert any(item["id"] == expected_risk_id for item in result["risk_items"])

"""Tests for dashboard service workspace-specific module aggregation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.contracts.workspace import WorkspacePayload
from src.services.dashboard_service import DashboardService
from tests.database.conftest import _Capability as DbCapability

CANONICAL_WORKSPACE_TYPES = ("sci", "thesis", "proposal", "software_copyright", "patent")


def _make_capability(
    capability_id: str,
    workspace_type: str,
    *,
    order: int = 0,
    status_kind: str | None = None,
    dashboard_meta: dict | None = None,
) -> DbCapability:
    """Build a minimal DbCapability row for dashboard module ordering tests."""
    if dashboard_meta is None:
        dashboard_meta = {"status_kind": status_kind or capability_id}
    return DbCapability(
        id=capability_id,
        workspace_type=workspace_type,
        enabled=True,
        display_name=capability_id,
        description="",
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


class FakeDashboardClient:
    def __init__(self, capabilities: list[DbCapability] | None = None) -> None:
        self.workspace = WorkspacePayload(
            id="ws-1",
            created_by_user_id="user-1",
            name="Workspace",
            workspace_type="thesis",
        )
        self.capabilities = list(capabilities or [])
        self.list_legacy_artifacts = AsyncMock(return_value=[])
        self.count_legacy_artifacts = AsyncMock(return_value=0)
        self.count_running_feature_executions = AsyncMock(return_value=0)
        self.get_latest_feature_execution_status = AsyncMock(return_value=None)

    async def get_workspace(self, workspace_id: str):
        return self.workspace if workspace_id == self.workspace.id else None

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
async def test_dashboard_status_builders_cover_capabilities(test_session) -> None:
    """Every capability with a dashboard_meta.status_kind must have a matching mixin method."""
    from sqlalchemy import select

    from src.database.models.capability import Capability

    service = DashboardService(AsyncMock())
    result = await test_session.execute(
        select(Capability).where(Capability.enabled == True)  # noqa: E712
    )
    capabilities = result.scalars().all()
    missing = []
    for cap in capabilities:
        status_kind = (cap.dashboard_meta or {}).get("status_kind", cap.id)
        method_name = f"_get_{status_kind}_status"
        if not hasattr(service, method_name):
            missing.append(method_name)
    assert missing == [], f"Missing mixin methods: {missing}"


@pytest.mark.asyncio
async def test_get_dashboard_sci_uses_workspace_specific_modules(test_session):
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("literature_search", "sci", order=0),
            _make_capability("paper_analysis", "sci", order=1),
            _make_capability("writing", "sci", order=2),
            _make_capability("literature_review", "sci", order=3),
            _make_capability("framework_outline", "sci", order=4),
            _make_capability("figure_generation", "sci", order=5),
            _make_capability("peer_review", "sci", order=6),
            _make_capability("journal_recommend", "sci", order=7),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)

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
async def test_get_dashboard_proposal_uses_workspace_specific_modules(test_session):
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("proposal_outline", "proposal", order=0),
            _make_capability("background_research", "proposal", order=1),
            _make_capability("experiment_design", "proposal", order=2),
            _make_capability("figure_generation", "proposal", order=3),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)

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
async def test_get_dashboard_software_copyright_uses_workspace_specific_modules(test_session):
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("copyright_materials", "software_copyright", order=0),
            _make_capability("technical_description", "software_copyright", order=1),
            _make_capability("figure_generation", "software_copyright", order=2),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)

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
async def test_get_dashboard_patent_uses_workspace_specific_modules(test_session):
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("patent_outline", "patent", order=0),
            _make_capability("prior_art_search", "patent", order=1),
            _make_capability("figure_generation", "patent", order=2),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)

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
    service = DashboardService(db, dataservice=FakeDashboardClient())

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
    fake_client = FakeDashboardClient()
    service = DashboardService(db, dataservice=fake_client)
    service._count_running_feature_executions = AsyncMock(return_value=0)

    await service._get_opening_research_status("ws-1")

    _, kwargs = fake_client.list_legacy_artifacts.call_args
    assert kwargs["created_by_skills"] is None

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


@pytest.mark.asyncio
async def test_modules_built_from_capability_table(test_session):
    """DashboardService reads modules from capabilities table, not workspace_features registry."""
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("deep_research", "thesis", order=0),
            _make_capability("literature_management", "thesis", order=1),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)
    service._get_deep_research_status = AsyncMock(
        return_value={
            "id": "deep_research",
            "status": "not_started",
            "summary": {},
        }
    )
    service._get_literature_management_status = AsyncMock(
        return_value={
            "id": "literature_management",
            "status": "not_started",
            "summary": {},
        }
    )

    modules = await service._get_modules_for_workspace("ws-uuid", "thesis")

    assert len(modules) == 2
    assert [m["id"] for m in modules] == ["deep_research", "literature_management"]


@pytest.mark.asyncio
async def test_modules_respect_ui_meta_order(test_session):
    """Capabilities are returned in ascending ui_meta.order (then id) regardless of insert order."""
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("literature_management", "thesis", order=5),
            _make_capability("deep_research", "thesis", order=1),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)
    service._get_deep_research_status = AsyncMock(
        return_value={"id": "deep_research", "status": "not_started", "summary": {}}
    )
    service._get_literature_management_status = AsyncMock(
        return_value={
            "id": "literature_management",
            "status": "not_started",
            "summary": {},
        }
    )

    modules = await service._get_modules_for_workspace("ws-uuid", "thesis")

    assert [m["id"] for m in modules] == ["deep_research", "literature_management"]


@pytest.mark.asyncio
async def test_modules_skip_disabled_capabilities(test_session):
    """Capabilities with enabled=False must not produce modules."""
    enabled = _make_capability("deep_research", "thesis", order=0)
    disabled = _make_capability("literature_management", "thesis", order=1)
    disabled.enabled = False

    service = DashboardService(
        test_session,
        dataservice=FakeDashboardClient(capabilities=[enabled, disabled]),
    )
    service._get_deep_research_status = AsyncMock(
        return_value={"id": "deep_research", "status": "not_started", "summary": {}}
    )

    modules = await service._get_modules_for_workspace("ws-uuid", "thesis")

    assert [m["id"] for m in modules] == ["deep_research"]


@pytest.mark.asyncio
async def test_modules_use_dashboard_meta_status_kind(test_session):
    """status_kind from dashboard_meta drives method dispatch when it differs from capability.id."""
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability(
                "alias_capability",
                "thesis",
                order=0,
                status_kind="deep_research",
            ),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)
    service._get_deep_research_status = AsyncMock(
        return_value={"id": "deep_research", "status": "not_started", "summary": {}}
    )

    modules = await service._get_modules_for_workspace("ws-uuid", "thesis")

    assert [m["id"] for m in modules] == ["deep_research"]
    service._get_deep_research_status.assert_awaited_once_with("ws-uuid")


@pytest.mark.asyncio
async def test_modules_raise_when_status_kind_missing_method(test_session):
    """If a capability's status_kind has no _get_<status_kind>_status method, raise RuntimeError."""
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability(
                "future_capability",
                "thesis",
                order=0,
                status_kind="not_implemented_kind",
            ),
        ]
    )

    service = DashboardService(test_session, dataservice=fake_client)

    with pytest.raises(RuntimeError, match="not_implemented_kind"):
        await service._get_modules_for_workspace("ws-uuid", "thesis")


@pytest.mark.asyncio
async def test_hidden_capabilities_skipped(test_session):
    """Capabilities marked dashboard_meta.hidden=true do not appear as dashboard modules."""
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("deep_research", "thesis", order=0),
            _make_capability("outline_generate", "thesis", order=1, dashboard_meta={"status_kind": "outline_generate", "hidden": True}),
        ]
    )
    service = DashboardService(test_session, dataservice=fake_client)
    service._get_deep_research_status = AsyncMock(return_value={"id": "deep_research", "status": "not_started", "summary": {}})
    modules = await service._get_modules_for_workspace("ws", "thesis")
    assert len(modules) == 1
    assert modules[0]["id"] == "deep_research"

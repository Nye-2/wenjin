"""Tests for catalog-driven workspace dashboard aggregation."""

from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.contracts.workspace import WorkspacePayload
from src.services.dashboard_service import DashboardService
from tests.database.conftest import _Capability as DbCapability


def _make_capability(
    capability_id: str,
    workspace_type: str,
    *,
    order: int = 0,
    enabled: bool = True,
    hidden: bool = False,
) -> DbCapability:
    return DbCapability(
        id=capability_id,
        workspace_type=workspace_type,
        enabled=enabled,
        display_name=capability_id,
        description="",
        intent_description="test",
        trigger_phrases=[],
        required_decisions=[],
        brief_schema={},
        graph_template={},
        ui_meta={"order": order, "icon": "x", "color": "x", "entry_tier": "primary"},
        runtime={"mode": "compute_agentic"},
        dashboard_meta={"hidden": hidden},
        notes=None,
    )


class FakeDashboardClient:
    def __init__(self, capabilities: list[DbCapability] | None = None) -> None:
        self.workspace = WorkspacePayload(
            id="ws-1",
            created_by_user_id="user-1",
            name="Workspace",
            workspace_type="thesis",
        )
        self.capabilities = list(capabilities or [])
        self.list_workspace_artifacts = AsyncMock(return_value=[])
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
async def test_get_dashboard_uses_catalog_missions_in_order(test_session):
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("research_question_to_paper", "sci", order=20),
            _make_capability("sci_literature_positioning", "sci", order=10),
            _make_capability("idea_to_thesis_manuscript", "thesis", order=0),
        ]
    )
    service = DashboardService(test_session, dataservice=fake_client)
    service._get_recent_artifacts = AsyncMock(return_value=[])

    result = await service.get_dashboard("ws-1", workspace_type="sci")

    assert [module["id"] for module in result["modules"]] == [
        "sci_literature_positioning",
        "research_question_to_paper",
    ]
    assert result["modules"][0]["status"] == "not_started"


@pytest.mark.asyncio
async def test_get_dashboard_raises_when_workspace_type_missing():
    service = DashboardService(AsyncMock(), dataservice=FakeDashboardClient())

    with pytest.raises(ValueError, match="Workspace not found: missing-ws"):
        await service.get_dashboard("missing-ws")


@pytest.mark.asyncio
async def test_catalog_capability_status_prefers_running_execution():
    service = DashboardService(AsyncMock())
    service._count_running_feature_executions = AsyncMock(return_value=1)
    service._get_latest_feature_execution_status = AsyncMock(return_value="failed")

    result = await service._get_catalog_capability_status(
        "ws-1",
        _make_capability("thesis_research_pack", "thesis"),
    )

    assert result["id"] == "thesis_research_pack"
    assert result["status"] == "in_progress"
    assert result["summary"]["running_count"] == 1
    assert result["summary"]["last_task_status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("latest_status", "expected"),
    [
        ("completed", "completed"),
        ("succeeded", "completed"),
        ("success", "completed"),
        ("failed", "failed"),
        (None, "not_started"),
    ],
)
async def test_catalog_capability_status_from_latest_execution(latest_status, expected):
    service = DashboardService(AsyncMock())
    service._count_running_feature_executions = AsyncMock(return_value=0)
    service._get_latest_feature_execution_status = AsyncMock(return_value=latest_status)

    result = await service._get_catalog_capability_status(
        "ws-1",
        _make_capability("idea_to_proposal_package", "proposal"),
    )

    assert result["status"] == expected


@pytest.mark.asyncio
async def test_modules_skip_disabled_and_hidden_capabilities(test_session):
    fake_client = FakeDashboardClient(
        capabilities=[
            _make_capability("idea_to_thesis_manuscript", "thesis", order=0),
            _make_capability("thesis_research_pack", "thesis", order=1, enabled=False),
            _make_capability("thesis_empirical_analysis", "thesis", order=2, hidden=True),
        ]
    )
    service = DashboardService(test_session, dataservice=fake_client)

    modules = await service._get_modules_for_workspace("ws-1", "thesis")

    assert [module["id"] for module in modules] == ["idea_to_thesis_manuscript"]


@pytest.mark.asyncio
async def test_status_from_count_and_running_keeps_shared_contract():
    service = DashboardService(AsyncMock())

    assert await service._status_from_count_and_running(
        count=0,
        running_count=1,
        latest_task_status="failed",
    ) == "in_progress"
    assert await service._status_from_count_and_running(
        count=1,
        running_count=0,
        latest_task_status="failed",
    ) == "completed"
    assert await service._status_from_count_and_running(
        count=0,
        running_count=0,
        latest_task_status="failed",
    ) == "failed"

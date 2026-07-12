"""Mission-backed workspace summary projection tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.contracts.mission import MissionStatus
from src.services.workspace_summary_service import WorkspaceSummaryService


def _mission(
    mission_id: str,
    status: MissionStatus,
    *,
    policy_id: str = "sci_research",
    title: str = "Federated PEFT",
    objective: str = "Map research gaps",
) -> SimpleNamespace:
    return SimpleNamespace(
        mission_id=mission_id,
        mission_policy_id=policy_id,
        status=status,
        title=title,
        objective=objective,
    )


def _service(missions: list[SimpleNamespace], *, activity: dict | None = None) -> WorkspaceSummaryService:
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(list_workspace=AsyncMock(return_value=missions)),
    )
    activity_service = SimpleNamespace(
        get_activity=AsyncMock(return_value=activity or {"items": []}),
    )
    return WorkspaceSummaryService(
        dataservice=dataservice,  # type: ignore[arg-type]
        activity_service=activity_service,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_empty_workspace_summary_invites_a_research_goal() -> None:
    result = await _service([]).get_summary("ws-1", workspace_type="sci", user_id="user-1")

    assert result["progress"] == {
        "completed": 0,
        "in_progress": 0,
        "failed": 0,
        "total": 0,
        "percent": 0,
    }
    assert result["current_phase"]["mission_id"] is None
    assert result["current_phase"]["mission_policy_id"] is None
    assert result["next_step"] is None
    assert result["headline"] == "从一个具体研究目标开始"


@pytest.mark.asyncio
async def test_active_mission_is_the_current_phase_and_next_step() -> None:
    active = _mission("mission-2", MissionStatus.RUNNING, title="Literature positioning")
    completed = _mission("mission-1", MissionStatus.COMPLETED)

    result = await _service([active, completed]).get_summary("ws-1", workspace_type="sci")

    assert result["progress"] == {
        "completed": 1,
        "in_progress": 1,
        "failed": 0,
        "total": 2,
        "percent": 50,
    }
    assert result["current_phase"] == {
        "mission_id": "mission-2",
        "mission_policy_id": "sci_research",
        "title": "Literature positioning",
        "status": "running",
        "description": "Map research gaps",
    }
    assert result["next_step"]["mission_id"] == "mission-2"
    assert result["next_step"]["mission_policy_id"] == "sci_research"
    assert result["recommended_actions"] == [result["next_step"]]


@pytest.mark.asyncio
async def test_terminal_missions_project_completed_and_failed_counts() -> None:
    missions = [
        _mission("mission-3", MissionStatus.FAILED),
        _mission("mission-2", MissionStatus.CANCELLED),
        _mission("mission-1", MissionStatus.COMPLETED),
    ]

    result = await _service(missions).get_summary("ws-1", workspace_type="thesis")

    assert result["progress"]["completed"] == 1
    assert result["progress"]["failed"] == 2
    assert result["progress"]["in_progress"] == 0
    assert result["current_phase"]["status"] == "failed"
    assert result["next_step"] is None


@pytest.mark.asyncio
async def test_recent_activity_is_projected_without_catalog_lookup() -> None:
    activity = {
        "items": [
            {
                "title": "Stage accepted",
                "summary": "Scope passed",
                "kind": "mission_stage",
                "occurred_at": "2026-07-11T00:00:00Z",
            }
        ]
    }

    result = await _service([], activity=activity).get_summary("ws-1", workspace_type="proposal")

    assert result["recent_activity"] == activity["items"][0]

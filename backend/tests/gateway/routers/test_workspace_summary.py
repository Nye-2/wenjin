"""Tests for workspace summary router."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers.auth import get_current_user


def create_mock_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


def create_workspace(user_id: str = "user-1", workspace_type: str = "thesis"):
    workspace = MagicMock()
    workspace.id = "ws-1"
    workspace.user_id = user_id
    workspace.type = MagicMock(value=workspace_type)
    return workspace


def create_test_app(user, workspace_service, summary_service):
    from src.gateway.routers import workspaces

    app = FastAPI()
    workspace = getattr(workspace_service.get, "return_value", None)
    workspace_service.has_active_membership = AsyncMock(return_value=workspace is not None and str(workspace.user_id) == str(user.id))

    async def override_get_current_user():
        return user

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_workspace_summary_service():
        return summary_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_workspace_summary_service] = override_get_workspace_summary_service
    app.include_router(workspaces.router)
    return TestClient(app)


def test_workspace_summary_returns_cockpit_payload():
    ws_svc = AsyncMock()
    ws_svc.get = AsyncMock(return_value=create_workspace())

    summary_svc = AsyncMock()
    summary_svc.get_summary = AsyncMock(
        return_value={
            "workspace_id": "ws-1",
            "workspace_type": "thesis",
            "headline": "建议优先推进论文写作。",
            "progress": {
                "completed": 2,
                "in_progress": 1,
                "failed": 0,
                "total": 6,
                "percent": 42,
            },
            "current_phase": {
                "mission_id": "mission-1",
                "mission_policy_id": "opening_research",
                "title": "开题调研",
                "status": "in_progress",
                "description": "该模块正在推进中。",
            },
            "next_step": {
                "mission_id": "mission-1",
                "mission_policy_id": "opening_research",
                "title": "开题调研",
                "description": "开题报告调研与撰写辅助",
                "reason": "当前已有任务在运行，建议优先跟进其结果。",
                "status": "in_progress",
                "status_label": "进行中",
            },
            "recommended_actions": [
                {
                    "mission_id": "mission-1",
                    "mission_policy_id": "opening_research",
                    "title": "开题调研",
                    "description": "开题报告调研与撰写辅助",
                    "reason": "当前已有任务在运行，建议优先跟进其结果。",
                    "status": "in_progress",
                    "status_label": "进行中",
                },
                {
                    "mission_id": "mission-2",
                    "mission_policy_id": "thesis_writing",
                    "title": "论文写作",
                    "description": "大纲生成与章节内容撰写",
                    "reason": "主链推荐下一步。",
                    "status": "not_started",
                    "status_label": "未开始",
                },
            ],
            "risk_items": [
                {
                    "id": "literature-core:thesis",
                    "title": "核心文献偏少",
                    "tone": "warning",
                }
            ],
            "recent_activity": {
                "title": "开题调研",
                "summary": "最近更新",
                "kind": "mission",
                "occurred_at": "2026-03-23T09:00:00+00:00",
            },
        }
    )

    client = create_test_app(create_mock_user(), ws_svc, summary_svc)
    response = client.get("/workspaces/ws-1/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["current_phase"]["mission_policy_id"] == "opening_research"
    assert data["recommended_actions"][1]["mission_policy_id"] == "thesis_writing"
    summary_svc.get_summary.assert_awaited_once_with(
        "ws-1",
        workspace_type="thesis",
        user_id="user-1",
    )


def test_workspace_summary_returns_404_for_missing_workspace():
    ws_svc = AsyncMock()
    ws_svc.get = AsyncMock(return_value=None)
    summary_svc = AsyncMock()

    client = create_test_app(create_mock_user(), ws_svc, summary_svc)
    response = client.get("/workspaces/missing/summary")

    assert response.status_code == 404


def test_workspace_summary_returns_403_for_non_owner():
    ws_svc = AsyncMock()
    ws_svc.get = AsyncMock(return_value=create_workspace(user_id="owner-2"))
    summary_svc = AsyncMock()

    client = create_test_app(create_mock_user(user_id="user-1"), ws_svc, summary_svc)
    response = client.get("/workspaces/ws-1/summary")

    assert response.status_code == 403

"""Tests for user/admin dashboard router."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import dashboard
from src.gateway.routers.auth import get_current_user


def _mock_user(user_id: str = "user-1", is_superuser: bool = False):
    user = MagicMock()
    user.id = user_id
    user.is_superuser = is_superuser
    user.is_active = True
    return user


def _create_client(
    *,
    user,
    user_dashboard_service=None,
    admin_dashboard_service=None,
    credit_service=None,
    release_gate_service=None,
) -> TestClient:
    app = FastAPI()

    async def override_get_current_user():
        return user

    async def override_user_dashboard_service():
        return user_dashboard_service or AsyncMock()

    async def override_admin_dashboard_service():
        return admin_dashboard_service or AsyncMock()

    async def override_credit_service():
        return credit_service or AsyncMock()

    async def override_release_gate_service():
        return release_gate_service or AsyncMock()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[dashboard.get_user_dashboard_service] = (
        override_user_dashboard_service
    )
    app.dependency_overrides[dashboard.get_admin_dashboard_service] = (
        override_admin_dashboard_service
    )
    app.dependency_overrides[dashboard.get_credit_service] = override_credit_service
    app.dependency_overrides[dashboard.get_release_gate_service] = (
        override_release_gate_service
    )
    app.include_router(dashboard.router)
    return TestClient(app)


def test_get_my_dashboard_returns_payload():
    svc = AsyncMock()
    svc.get_dashboard = AsyncMock(return_value={"profile": {"id": "user-1"}})
    client = _create_client(user=_mock_user(), user_dashboard_service=svc)

    response = client.get("/dashboard/me")

    assert response.status_code == 200
    assert response.json()["profile"]["id"] == "user-1"
    svc.get_dashboard.assert_awaited_once_with("user-1")


def test_get_admin_dashboard_requires_admin():
    client = _create_client(user=_mock_user(is_superuser=False))

    response = client.get("/dashboard/admin")

    assert response.status_code == 403


def test_get_admin_dashboard_success():
    svc = AsyncMock()
    svc.get_dashboard = AsyncMock(return_value={"summary": {"users": {"total": 12}}})
    client = _create_client(user=_mock_user(is_superuser=True), admin_dashboard_service=svc)

    response = client.get("/dashboard/admin")

    assert response.status_code == 200
    assert response.json()["summary"]["users"]["total"] == 12
    svc.get_dashboard.assert_awaited_once()


def test_grant_credits_logs_admin_action():
    tx = MagicMock()
    tx.id = "tx-1"
    tx.amount = 50
    tx.balance_after = 150

    credit_service = AsyncMock()
    credit_service.admin_grant = AsyncMock(return_value=tx)

    admin_service = AsyncMock()
    admin_service.create_admin_log = AsyncMock(return_value=MagicMock())

    client = _create_client(
        user=_mock_user(user_id="admin-1", is_superuser=True),
        credit_service=credit_service,
        admin_dashboard_service=admin_service,
    )

    response = client.post(
        "/dashboard/admin/credits/grant",
        json={
            "user_id": "user-2",
            "amount": 50,
            "description": "测试发放",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["transaction"]["id"] == "tx-1"
    credit_service.admin_grant.assert_awaited_once()
    admin_service.create_admin_log.assert_awaited_once()


def test_get_admin_release_gate_requires_admin():
    client = _create_client(user=_mock_user(is_superuser=False))

    response = client.get("/dashboard/admin/release-gate")

    assert response.status_code == 403


def test_get_admin_release_gate_runs_service_with_query_flag():
    release_gate_service = AsyncMock()
    release_gate_service.run = AsyncMock(
        return_value={
            "status": "passed",
            "go_no_go": "go",
            "core_gate": {"status": "passed"},
            "extended_gate": {"status": "failed"},
        }
    )

    client = _create_client(
        user=_mock_user(is_superuser=True),
        release_gate_service=release_gate_service,
    )

    response = client.get("/dashboard/admin/release-gate?include_extended=true")

    assert response.status_code == 200
    assert response.json()["go_no_go"] == "go"
    release_gate_service.run.assert_awaited_once_with(include_extended=True)


def test_get_admin_release_gate_defaults_to_core_only():
    release_gate_service = AsyncMock()
    release_gate_service.run = AsyncMock(
        return_value={
            "status": "passed",
            "go_no_go": "go",
            "core_gate": {"status": "passed"},
            "extended_gate": {"status": "pending"},
        }
    )

    client = _create_client(
        user=_mock_user(is_superuser=True),
        release_gate_service=release_gate_service,
    )

    response = client.get("/dashboard/admin/release-gate")

    assert response.status_code == 200
    assert response.json()["extended_gate"]["status"] == "pending"
    release_gate_service.run.assert_awaited_once_with(include_extended=False)


def test_update_user_status_rejects_disabling_last_active_admin():
    admin_service = AsyncMock()
    admin_service.update_user_status = AsyncMock(
        side_effect=ValueError("Cannot disable the last active admin")
    )

    client = _create_client(
        user=_mock_user(user_id="admin-1", is_superuser=True),
        admin_dashboard_service=admin_service,
    )

    response = client.post(
        "/dashboard/admin/users/admin-2/status",
        json={"is_active": False},
    )

    assert response.status_code == 400
    assert "last active admin" in response.json()["detail"]


def test_update_user_role_rejects_demoting_last_active_admin():
    admin_service = AsyncMock()
    admin_service.update_user_role = AsyncMock(
        side_effect=ValueError("Cannot demote the last active admin")
    )

    client = _create_client(
        user=_mock_user(user_id="admin-1", is_superuser=True),
        admin_dashboard_service=admin_service,
    )

    response = client.post(
        "/dashboard/admin/users/admin-2/role",
        json={"role": "user"},
    )

    assert response.status_code == 400
    assert "last active admin" in response.json()["detail"]

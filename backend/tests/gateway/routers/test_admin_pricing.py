"""Tests for admin pricing gateway routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.routers import admin_pricing


def _admin() -> AccountAuthSubject:
    return AccountAuthSubject(
        id="admin-1",
        email="admin@example.com",
        name="Admin",
        role="admin",
        is_active=True,
        is_superuser=True,
    )


class _FakePricingService:
    async def simulate(self, command):
        return {
            "charge_credits": 3,
            "raw_cost_cny": 0.2,
            "margin_cny": 0.1,
            "breakdown": {"weighted_tokens": 3000},
        }


def test_admin_pricing_simulator_returns_breakdown() -> None:
    app = FastAPI()
    app.include_router(admin_pricing.router)
    app.dependency_overrides[admin_pricing._service] = lambda: _FakePricingService()
    app.dependency_overrides[get_current_admin] = lambda: _admin()
    client = TestClient(app)

    response = client.post(
        "/admin/pricing/simulate",
        json={"policy_kind": "model_usage", "prompt_tokens": 1000, "completion_tokens": 500},
    )

    assert response.status_code == 200
    assert response.json()["charge_credits"] == 3
    assert response.json()["breakdown"]["weighted_tokens"] == 3000

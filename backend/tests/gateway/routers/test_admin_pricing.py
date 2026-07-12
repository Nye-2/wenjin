"""Tests for admin pricing gateway routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.pricing import PricingPolicyPayload
from src.dataservice_client.errors import DataServiceClientError
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
    def __init__(self) -> None:
        self.created = None
        self.updated = None
        self.disabled = None

    async def list_policies(self, *, policy_kind: str | None = None, enabled_only: bool = False):
        return [
            PricingPolicyPayload(
                id="policy-1",
                policy_key="model-standard",
                policy_kind="model_usage",
                name="Model standard",
                enabled=True,
                version=1,
                config={"credits_per_1k_weighted_tokens": 6},
            )
        ]

    async def create_policy(self, command, *, admin_id: str):
        self.created = (command, admin_id)
        return PricingPolicyPayload(
            id="policy-1",
            policy_key=command.policy_key,
            policy_kind=command.policy_kind,
            name=command.name,
            enabled=True,
            version=1,
            config=command.config,
        )

    async def update_policy(self, policy_id_or_key: str, command, *, admin_id: str):
        self.updated = (policy_id_or_key, command, admin_id)
        return PricingPolicyPayload(
            id="policy-1",
            policy_key=policy_id_or_key,
            policy_kind="model_usage",
            name=command.name or "Model standard",
            enabled=True,
            version=2,
            config=command.config or {"credits_per_1k_weighted_tokens": 6},
        )

    async def disable_policy(self, policy_id_or_key: str, *, admin_id: str):
        self.disabled = (policy_id_or_key, admin_id)
        return PricingPolicyPayload(
            id="policy-1",
            policy_key=policy_id_or_key,
            policy_kind="model_usage",
            name="Model standard",
            enabled=False,
            version=2,
            config={"credits_per_1k_weighted_tokens": 6},
        )

    async def simulate(self, command):
        return {
            "charge_credits": 3,
            "raw_cost_cny": 0.2,
            "margin_cny": 0.1,
            "breakdown": {"weighted_tokens": 3000},
        }


class _FakeDataServiceErrorPricingService(_FakePricingService):
    async def create_policy(self, command, *, admin_id: str):
        _ = command, admin_id
        raise DataServiceClientError("policy key already exists", status_code=409)


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


def test_admin_pricing_policy_crud_routes() -> None:
    service = _FakePricingService()
    app = FastAPI()
    app.include_router(admin_pricing.router)
    app.include_router(admin_pricing.policies_router)
    app.dependency_overrides[admin_pricing._service] = lambda: service
    app.dependency_overrides[get_current_admin] = lambda: _admin()
    client = TestClient(app)

    list_response = client.get("/admin/pricing-policies?policy_kind=model_usage&enabled_only=true")
    create_response = client.post(
        "/admin/pricing-policies",
        json={
            "policy_key": "model-standard",
            "policy_kind": "model_usage",
            "name": "Model standard",
            "config": {"credits_per_1k_weighted_tokens": 6},
        },
    )
    update_response = client.patch("/admin/pricing-policies/model-standard", json={"name": "Model v2"})
    disable_response = client.post("/admin/pricing-policies/model-standard/disable")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["policy_key"] == "model-standard"
    assert create_response.status_code == 200
    command, admin_id = service.created
    assert command.policy_key == "model-standard"
    assert admin_id == "admin-1"
    assert update_response.json()["version"] == 2
    assert service.updated[2] == "admin-1"
    assert disable_response.json()["enabled"] is False
    assert service.disabled == ("model-standard", "admin-1")


def test_admin_pricing_routes_preserve_dataservice_client_status() -> None:
    app = FastAPI()
    app.include_router(admin_pricing.policies_router)
    app.dependency_overrides[admin_pricing._service] = lambda: _FakeDataServiceErrorPricingService()
    app.dependency_overrides[get_current_admin] = lambda: _admin()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/admin/pricing-policies",
        json={
            "policy_key": "model-standard",
            "policy_kind": "model_usage",
            "name": "Model standard",
            "config": {"credits_per_1k_weighted_tokens": 6},
        },
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

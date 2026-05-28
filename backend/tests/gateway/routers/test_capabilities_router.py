"""Unit tests for capabilities router — Option A (mocked resolver).

Tests verify router wiring, status codes, and response shapes without a DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.routers import capabilities

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

USER_ID = "user-cap-1"


def _make_user() -> MagicMock:
    u = MagicMock()
    u.id = USER_ID
    return u


def _make_capability(cap_id: str = "deep_research", ws_type: str = "thesis") -> SimpleNamespace:
    return SimpleNamespace(
        id=cap_id,
        workspace_type=ws_type,
        enabled=True,
        tier="primary",
        display_name="Deep Research",
        description="Deep research capability",
        intent_description="Do deep research",
        trigger_phrases=["research this"],
        required_decisions=[],
        brief_schema={"type": "object"},
        graph_template={"phases": []},
        ui_meta={"icon": "search", "order": 0},
        runtime={"mode": "compute_agentic"},
        dashboard_meta={"status_kind": "deep_research"},
        notes=None,
    )


def _build_app(*, resolver: MagicMock) -> TestClient:
    app = FastAPI()

    async def override_user() -> MagicMock:
        return _make_user()

    async def override_resolver() -> MagicMock:
        return resolver

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[capabilities._get_resolver] = override_resolver
    app.include_router(capabilities.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListCapabilities:
    def test_list_happy(self) -> None:
        fake_cap = _make_capability()
        resolver = MagicMock()
        resolver.list_for_workspace_type = AsyncMock(return_value=[fake_cap])

        client = _build_app(resolver=resolver)
        resp = client.get("/capabilities?workspace_type=thesis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == "deep_research"
        resolver.list_for_workspace_type.assert_awaited_once_with("thesis")

    def test_list_returns_empty_when_no_capabilities(self) -> None:
        resolver = MagicMock()
        resolver.list_for_workspace_type = AsyncMock(return_value=[])

        client = _build_app(resolver=resolver)
        resp = client.get("/capabilities?workspace_type=patent")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["items"] == []

    def test_list_filters_hidden_capabilities(self) -> None:
        visible = _make_capability("visible_cap")
        hidden = _make_capability("internal_sandbox_smoke")
        hidden.tier = "hidden"
        hidden.ui_meta = {"entry_tier": "hidden"}
        resolver = MagicMock()
        resolver.list_for_workspace_type = AsyncMock(return_value=[visible, hidden])

        client = _build_app(resolver=resolver)
        resp = client.get("/capabilities?workspace_type=thesis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert [item["id"] for item in data["items"]] == ["visible_cap"]


class TestGetCapability:
    def test_get_happy(self) -> None:
        fake_cap = _make_capability()
        resolver = MagicMock()
        resolver.resolve = AsyncMock(return_value=fake_cap)

        client = _build_app(resolver=resolver)
        resp = client.get("/capabilities/deep_research?workspace_type=thesis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "deep_research"
        assert data["workspace_type"] == "thesis"
        resolver.resolve.assert_awaited_once_with("deep_research", "thesis")

    def test_get_not_found(self) -> None:
        from src.services.capability_resolver import CapabilityNotFound

        resolver = MagicMock()
        resolver.resolve = AsyncMock(
            side_effect=CapabilityNotFound("missing_cap", "thesis")
        )

        client = _build_app(resolver=resolver)
        resp = client.get("/capabilities/missing_cap?workspace_type=thesis")

        assert resp.status_code == 404
        assert "missing_cap" in resp.json()["detail"]

    def test_get_hidden_returns_not_found(self) -> None:
        hidden = _make_capability("internal_sandbox_smoke")
        hidden.tier = "hidden"
        hidden.ui_meta = {"entry_tier": "hidden"}
        resolver = MagicMock()
        resolver.resolve = AsyncMock(return_value=hidden)

        client = _build_app(resolver=resolver)
        resp = client.get("/capabilities/internal_sandbox_smoke?workspace_type=thesis")

        assert resp.status_code == 404
        assert "internal_sandbox_smoke" in resp.json()["detail"]

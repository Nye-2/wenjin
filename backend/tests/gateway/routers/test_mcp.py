"""Tests for MCP configuration router."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config.extensions_config import reset_extensions_config
from src.gateway.routers import mcp as mcp_router
from src.gateway.routers.auth import get_current_user
from src.mcp import get_mcp_manager, reset_mcp_manager


def _mock_user(*, is_superuser: bool) -> SimpleNamespace:
    return SimpleNamespace(id="admin-1", is_superuser=is_superuser, is_active=True)


def _create_client(*, is_superuser: bool = True) -> TestClient:
    app = FastAPI()

    async def override_get_current_user():
        return _mock_user(is_superuser=is_superuser)

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(mcp_router.router)
    return TestClient(app)


def test_get_mcp_configuration_returns_current_servers(tmp_path, monkeypatch):
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "enabled": True,
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                    }
                },
                "skills": {},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GUANLAN_EXTENSIONS_CONFIG_PATH", str(config_path))
    reset_extensions_config()
    reset_mcp_manager()

    client = _create_client()
    response = client.get("/mcp/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mcp_servers"]["github"]["command"] == "npx"
    assert payload["mcp_servers"]["github"]["type"] == "stdio"


def test_update_mcp_configuration_persists_and_refreshes_runtime(tmp_path, monkeypatch):
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {},
                "skills": {
                    "deep-research": {"enabled": True},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GUANLAN_EXTENSIONS_CONFIG_PATH", str(config_path))
    reset_extensions_config()
    reset_mcp_manager()

    class FakeValidationManager:
        async def load_from_extensions_config(self, _config):
            return None

        async def load_tools(self, *, force_reload: bool = False):
            return []

        def get_last_load_errors(self):
            return {}

        async def close(self):
            return None

    async def _fake_activate_mcp_runtime(**kwargs):
        manager = get_mcp_manager(str(config_path))
        await manager.load_from_extensions_config(kwargs["extensions_config"])
        return manager, []

    monkeypatch.setattr(mcp_router, "MCPManager", lambda config_path=None: FakeValidationManager())
    monkeypatch.setattr(mcp_router, "activate_mcp_runtime", _fake_activate_mcp_runtime)

    client = _create_client()
    response = client.put(
        "/mcp/config",
        json={
            "mcp_servers": {
                "secure-http": {
                    "enabled": True,
                    "type": "http",
                    "url": "https://api.example.com/mcp",
                    "headers": {"X-Test": "1"},
                    "oauth": {
                        "enabled": True,
                        "token_url": "https://auth.example.com/oauth/token",
                        "grant_type": "client_credentials",
                        "client_id": "client-id",
                        "client_secret": "client-secret",
                    },
                    "timeout": 45,
                    "description": "Secure MCP server",
                }
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mcp_servers"]["secure-http"]["type"] == "http"
    assert payload["mcp_servers"]["secure-http"]["oauth"]["token_url"] == ("https://auth.example.com/oauth/token")

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["skills"]["deep-research"]["enabled"] is True
    assert saved["mcpServers"]["secure-http"]["timeout"] == 45

    manager = get_mcp_manager(str(config_path))
    assert manager.list_servers() == ["secure-http"]


def test_update_mcp_configuration_rejects_invalid_runtime_without_persisting(tmp_path, monkeypatch):
    config_path = tmp_path / "extensions_config.json"
    original_payload = {
        "mcpServers": {
            "stable": {
                "enabled": True,
                "type": "stdio",
                "command": "echo",
            }
        },
        "skills": {},
    }
    config_path.write_text(json.dumps(original_payload), encoding="utf-8")

    monkeypatch.setenv("GUANLAN_EXTENSIONS_CONFIG_PATH", str(config_path))
    reset_extensions_config()
    reset_mcp_manager()

    class FakeValidationManager:
        async def load_from_extensions_config(self, _config):
            return None

        async def load_tools(self, *, force_reload: bool = False):
            return []

        def get_last_load_errors(self):
            return {"broken": "connection refused"}

        async def close(self):
            return None

    activate_calls: list[dict] = []

    async def _fake_activate_mcp_runtime(**kwargs):
        activate_calls.append(kwargs)
        return get_mcp_manager(str(config_path)), []

    monkeypatch.setattr(mcp_router, "MCPManager", lambda config_path=None: FakeValidationManager())
    monkeypatch.setattr(mcp_router, "activate_mcp_runtime", _fake_activate_mcp_runtime)

    client = _create_client()
    response = client.put(
        "/mcp/config",
        json={
            "mcp_servers": {
                "broken": {
                    "enabled": True,
                    "type": "http",
                    "url": "https://broken.example.com/mcp",
                }
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["errors"] == {"broken": "connection refused"}
    assert json.loads(config_path.read_text(encoding="utf-8")) == original_payload
    assert activate_calls == []


def test_mcp_configuration_requires_admin():
    client = _create_client(is_superuser=False)

    response = client.get("/mcp/config")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"

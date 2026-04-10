"""Tests for gateway liveness/readiness helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.config.extensions_config import ExtensionsConfig
from src.gateway import health as health_module


def test_build_liveness_report_is_static():
    report = health_module.build_liveness_report()

    assert report == {
        "status": "alive",
        "version": "2.0.0",
    }


@pytest.mark.asyncio
async def test_build_readiness_report_aggregates_component_health(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "check_database",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_redis",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_task_backend",
        AsyncMock(return_value={"status": "healthy", "mode": "celery"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_mcp",
        AsyncMock(return_value={"status": "healthy", "tool_count": 0}),
    )
    monkeypatch.setattr(
        health_module,
        "check_execution",
        AsyncMock(return_value={"status": "healthy"}),
    )

    report = await health_module.build_readiness_report()

    assert report["status"] == "healthy"
    assert report["checks"]["task_backend"]["mode"] == "celery"


@pytest.mark.asyncio
async def test_build_readiness_report_is_unhealthy_if_any_component_fails(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "check_database",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_redis",
        AsyncMock(return_value={"status": "unhealthy", "error": "ping timeout"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_task_backend",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_mcp",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_execution",
        AsyncMock(return_value={"status": "healthy"}),
    )

    report = await health_module.build_readiness_report()

    assert report["status"] == "unhealthy"
    assert report["checks"]["redis"]["error"] == "ping timeout"


@pytest.mark.asyncio
async def test_build_readiness_report_is_degraded_when_optional_dependency_fails(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "check_database",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_redis",
        AsyncMock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_task_backend",
        AsyncMock(return_value={"status": "healthy", "mode": "celery"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_mcp",
        AsyncMock(return_value={"status": "degraded"}),
    )
    monkeypatch.setattr(
        health_module,
        "check_execution",
        AsyncMock(return_value={"status": "healthy"}),
    )

    report = await health_module.build_readiness_report()

    assert report["status"] == "degraded"
    assert report["degraded_dependencies"] == ["mcp"]


@pytest.mark.asyncio
async def test_check_mcp_is_degraded_when_runtime_has_server_errors(monkeypatch):
    class FakeManager:
        async def load_tools(self, *, force_reload: bool = False):
            return [object()]

        def get_last_load_errors(self):
            return {"remote": "connection refused"}

    config = ExtensionsConfig.model_validate(
        {
            "mcpServers": {
                "remote": {
                    "enabled": True,
                    "type": "http",
                    "url": "https://example.com/mcp",
                }
            }
        }
    )

    monkeypatch.setattr(health_module.settings, "mcp_required_for_readiness", False)
    monkeypatch.setattr(health_module, "get_extensions_config", lambda: config)
    monkeypatch.setattr(health_module, "peek_mcp_manager", lambda: FakeManager())

    report = await health_module.check_mcp()

    assert report["status"] == "degraded"
    assert report["errors"] == {"remote": "connection refused"}


@pytest.mark.asyncio
async def test_check_mcp_is_unhealthy_in_strict_readiness_mode(monkeypatch):
    class FakeManager:
        async def load_tools(self, *, force_reload: bool = False):
            return [object()]

        def get_last_load_errors(self):
            return {"remote": "connection refused"}

    config = ExtensionsConfig.model_validate(
        {
            "mcpServers": {
                "remote": {
                    "enabled": True,
                    "type": "http",
                    "url": "https://example.com/mcp",
                }
            }
        }
    )

    monkeypatch.setattr(health_module.settings, "mcp_required_for_readiness", True)
    monkeypatch.setattr(health_module, "get_extensions_config", lambda: config)
    monkeypatch.setattr(health_module, "peek_mcp_manager", lambda: FakeManager())

    report = await health_module.check_mcp()

    assert report["status"] == "unhealthy"
    assert report["errors"] == {"remote": "connection refused"}

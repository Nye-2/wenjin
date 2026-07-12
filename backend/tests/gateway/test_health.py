"""Tests for gateway liveness/readiness helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.config.extensions_config import ExtensionsConfig
from src.gateway import health as health_module


@pytest.fixture(autouse=True)
def healthy_mission_catalog(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "check_mission_catalog",
        AsyncMock(return_value={"status": "healthy", "policy_count": 6, "skill_count": 15}),
    )


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
        "check_dataservice",
        AsyncMock(return_value={"status": "healthy", "service": "dataservice"}),
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
        "check_sandbox",
        AsyncMock(return_value={"status": "healthy"}),
    )

    report = await health_module.build_readiness_report()

    assert report["status"] == "healthy"
    assert "dataservice" in report["required_dependencies"]
    assert report["checks"]["dataservice"]["service"] == "dataservice"
    assert report["checks"]["task_backend"]["mode"] == "celery"


@pytest.mark.asyncio
async def test_build_readiness_report_is_unhealthy_if_any_component_fails(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "check_dataservice",
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
        "check_sandbox",
        AsyncMock(return_value={"status": "healthy"}),
    )

    report = await health_module.build_readiness_report()

    assert report["status"] == "unhealthy"
    assert report["checks"]["redis"]["error"] == "ping timeout"


@pytest.mark.asyncio
async def test_build_readiness_report_is_degraded_when_optional_dependency_fails(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "check_dataservice",
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
        "check_sandbox",
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


@pytest.mark.asyncio
async def test_build_readiness_report_marks_dependency_unhealthy_on_timeout(monkeypatch):
    async def _slow_check():
        await asyncio.sleep(5)
        return {"status": "healthy"}

    monkeypatch.setattr(health_module, "check_dataservice", _slow_check)
    monkeypatch.setattr(
        health_module,
        "check_redis",
        AsyncMock(return_value={"status": "healthy"}),
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
        "check_sandbox",
        AsyncMock(return_value={"status": "healthy"}),
    )

    report = await health_module.build_readiness_report()

    assert report["status"] == "unhealthy"
    assert report["checks"]["dataservice"]["status"] == "unhealthy"
    assert "timeout" in report["checks"]["dataservice"]["error"]


@pytest.mark.asyncio
async def test_check_dataservice_uses_dataservice_readyz(monkeypatch):
    class _FakeDataServiceClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def readyz(self):
            return {
                "status": "healthy",
                "service": "dataservice",
                "database": {"status": "healthy"},
            }

    monkeypatch.setattr(health_module, "dataservice_client", _FakeDataServiceClient)

    report = await health_module.check_dataservice()

    assert report == {
        "status": "healthy",
        "service": "dataservice",
        "database": {"status": "healthy"},
    }


@pytest.mark.asyncio
async def test_check_task_backend_falls_back_to_worker_metrics(monkeypatch):
    class _Inspect:
        def ping(self):
            return None

    class _Control:
        def inspect(self, timeout=1.5):  # noqa: ARG002
            return _Inspect()

    monkeypatch.setattr(health_module.celery_settings, "enabled", True)
    monkeypatch.setattr(health_module.celery_app, "control", _Control())
    monkeypatch.setattr(
        health_module,
        "_check_worker_metrics_endpoint",
        AsyncMock(return_value=(True, None)),
    )

    report = await health_module.check_task_backend()

    assert report["status"] == "healthy"
    assert report["mode"] == "celery"
    assert report["probe"] == "worker_metrics"
    assert "warning" in report


@pytest.mark.asyncio
async def test_check_task_backend_unhealthy_when_inspect_and_metrics_fail(monkeypatch):
    class _Inspect:
        def ping(self):
            return None

    class _Control:
        def inspect(self, timeout=1.5):  # noqa: ARG002
            return _Inspect()

    monkeypatch.setattr(health_module.celery_settings, "enabled", True)
    monkeypatch.setattr(health_module.celery_app, "control", _Control())
    monkeypatch.setattr(
        health_module,
        "_check_worker_metrics_endpoint",
        AsyncMock(return_value=(False, "connection refused")),
    )

    report = await health_module.check_task_backend()

    assert report["status"] == "unhealthy"
    assert report["mode"] == "celery"
    assert report["inspect_error"] == "No Celery workers responded to ping"
    assert report["metrics_error"] == "connection refused"

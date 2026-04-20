"""Gateway liveness and readiness checks."""

from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text

from src.academic.cache.redis_client import redis_client
from src.config import get_extensions_config, settings
from src.config.app_config import celery_settings, get_prometheus_settings
from src.database.session import engine
from src.execution.capabilities import execution_type_readiness
from src.execution.types import ExecutionType
from src.mcp import peek_mcp_manager
from src.task import celery_app
from src.thesis.execution import get_execution_service

logger = logging.getLogger(__name__)
_READINESS_DEPENDENCY_TIMEOUT_SECONDS = 3.0


def _mcp_failure_status() -> str:
    return "unhealthy" if settings.mcp_required_for_readiness else "degraded"


async def check_database() -> dict[str, Any]:
    """Verify database connectivity."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def check_redis() -> dict[str, Any]:
    """Verify Redis connectivity."""
    try:
        await redis_client.ping()
        await redis_client.connect_stream()
        await redis_client.stream_client.ping()
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def check_task_backend() -> dict[str, Any]:
    """Verify the configured async task backend is actually runnable."""
    if not celery_settings.enabled:
        return {
            "status": "unhealthy",
            "mode": "celery",
            "error": "CELERY_ENABLED must be true",
        }

    inspect_error: str | None = None
    try:
        inspect = celery_app.control.inspect(timeout=1.5)
        ping_result = await asyncio.to_thread(inspect.ping)
        if ping_result:
            return {
                "status": "healthy",
                "mode": "celery",
                "probe": "inspect",
                "workers": sorted(ping_result.keys()),
            }
    except Exception as exc:
        inspect_error = str(exc)
    else:
        inspect_error = "No Celery workers responded to ping"

    metrics_ok, metrics_error = await _check_worker_metrics_endpoint()
    if metrics_ok:
        report: dict[str, Any] = {
            "status": "healthy",
            "mode": "celery",
            "probe": "worker_metrics",
        }
        if inspect_error:
            report["warning"] = f"inspect ping unavailable: {inspect_error}"
        return report

    error_parts = [part for part in [inspect_error, metrics_error] if part]
    return {
        "status": "unhealthy",
        "mode": "celery",
        "error": "; ".join(error_parts) or "Task backend unavailable",
        "inspect_error": inspect_error,
        "metrics_error": metrics_error,
    }


async def _check_worker_metrics_endpoint() -> tuple[bool, str | None]:
    """Fallback worker readiness probe through the worker metrics endpoint."""
    worker_port = int(get_prometheus_settings().worker_port)
    target = f"http://worker:{worker_port}/metrics"

    def _fetch() -> int:
        with urllib.request.urlopen(target, timeout=1.5) as response:
            return int(getattr(response, "status", 200))

    try:
        status = await asyncio.to_thread(_fetch)
    except urllib.error.URLError as exc:
        return False, str(exc.reason or exc)
    except Exception as exc:
        return False, str(exc)

    if 200 <= status < 300:
        return True, None
    return False, f"metrics probe returned HTTP {status}"


async def check_mcp() -> dict[str, Any]:
    """Verify MCP runtime/cache readiness when MCP servers are configured."""
    configured_servers = sorted(get_extensions_config().get_enabled_mcp_servers().keys())
    if not configured_servers:
        return {
            "status": "healthy",
            "configured_servers": [],
            "tool_count": 0,
            "required": bool(settings.mcp_required_for_readiness),
        }

    failed_status = _mcp_failure_status()

    manager = peek_mcp_manager()
    if manager is None:
        return {
            "status": failed_status,
            "configured_servers": configured_servers,
            "error": "MCP runtime is not initialized",
            "required": bool(settings.mcp_required_for_readiness),
        }

    try:
        tools = await manager.load_tools(force_reload=False)
        errors = manager.get_last_load_errors()
        if errors:
            return {
                "status": failed_status,
                "configured_servers": configured_servers,
                "tool_count": len(tools),
                "errors": errors,
                "required": bool(settings.mcp_required_for_readiness),
            }
        return {
            "status": "healthy",
            "configured_servers": configured_servers,
            "tool_count": len(tools),
            "required": bool(settings.mcp_required_for_readiness),
        }
    except Exception as exc:
        return {
            "status": failed_status,
            "configured_servers": configured_servers,
            "error": str(exc),
            "required": bool(settings.mcp_required_for_readiness),
        }


async def check_execution() -> dict[str, Any]:
    """Verify execution infrastructure and core providers."""
    try:
        service = get_execution_service()
        health = await service.health_check()
        docker_health = health.get("docker", {})
        docker_ready = bool(docker_health.get("healthy"))

        capability_checks: dict[str, dict[str, Any]] = {}
        for execution_type in (
            ExecutionType.LATEX_COMPILE,
            ExecutionType.PYTHON_PLOT,
            ExecutionType.MERMAID_DIAGRAM,
            ExecutionType.AI_IMAGE,
        ):
            ready, reason = execution_type_readiness(service, execution_type)
            capability_checks[execution_type.value] = {
                "ready": ready,
                "reason": reason,
            }

        core_ready = docker_ready and all(
            capability_checks[execution_type.value]["ready"]
            for execution_type in (
                ExecutionType.LATEX_COMPILE,
                ExecutionType.PYTHON_PLOT,
                ExecutionType.MERMAID_DIAGRAM,
            )
        )
        return {
            "status": "healthy" if core_ready else "unhealthy",
            "docker": docker_health,
            "capabilities": capability_checks,
        }
    except Exception as exc:
        logger.warning("Execution readiness check failed: %s", exc, exc_info=True)
        return {"status": "unhealthy", "error": str(exc)}


async def build_readiness_report() -> dict[str, Any]:
    """Build aggregate readiness report for dependency-aware health checks."""
    async def _run_check_with_timeout(
        name: str,
        checker: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                checker(),
                timeout=_READINESS_DEPENDENCY_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "Readiness check timed out: dependency=%s timeout=%.1fs",
                name,
                _READINESS_DEPENDENCY_TIMEOUT_SECONDS,
            )
            return {
                "status": "unhealthy",
                "error": f"timeout after {_READINESS_DEPENDENCY_TIMEOUT_SECONDS:.1f}s",
            }
        except Exception as exc:
            logger.warning(
                "Readiness check failed unexpectedly: dependency=%s error=%s",
                name,
                exc,
                exc_info=True,
            )
            return {"status": "unhealthy", "error": str(exc)}

    database, redis, task_backend, mcp, execution = await asyncio.gather(
        _run_check_with_timeout("database", check_database),
        _run_check_with_timeout("redis", check_redis),
        _run_check_with_timeout("task_backend", check_task_backend),
        _run_check_with_timeout("mcp", check_mcp),
        _run_check_with_timeout("execution", check_execution),
    )
    checks = {
        "database": database,
        "redis": redis,
        "task_backend": task_backend,
        "mcp": mcp,
        "execution": execution,
    }
    required_dependencies = ["database", "redis", "task_backend", "execution"]
    if settings.mcp_required_for_readiness:
        required_dependencies.append("mcp")

    required_failures = [
        name
        for name in required_dependencies
        if checks.get(name, {}).get("status") != "healthy"
    ]
    optional_degradations = [
        name
        for name, report in checks.items()
        if name not in required_dependencies and report.get("status") != "healthy"
    ]

    if required_failures:
        overall = "unhealthy"
    elif optional_degradations:
        overall = "degraded"
    else:
        overall = "healthy"
    return {
        "status": overall,
        "version": "2.0.0",
        "required_dependencies": required_dependencies,
        "degraded_dependencies": optional_degradations,
        "checks": checks,
    }


def build_liveness_report() -> dict[str, Any]:
    """Build minimal liveness payload that does not depend on downstream services."""
    return {
        "status": "alive",
        "version": "2.0.0",
    }

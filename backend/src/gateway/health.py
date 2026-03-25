"""Gateway liveness and readiness checks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from src.academic.cache.redis_client import redis_client
from src.config import get_extensions_config, settings
from src.config.app_config import celery_settings
from src.database.session import engine
from src.execution.capabilities import execution_type_readiness
from src.execution.types import ExecutionType
from src.mcp import peek_mcp_manager
from src.task import celery_app
from src.thesis.execution import get_execution_service

logger = logging.getLogger(__name__)


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
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def check_task_backend() -> dict[str, Any]:
    """Verify the configured async task backend is actually runnable."""
    if not celery_settings.enabled:
        if settings.environment.lower() in {"development", "test"}:
            return {"status": "healthy", "mode": "local_executor"}
        return {
            "status": "unhealthy",
            "mode": "local_executor",
            "error": "LocalExecutor is disabled for production readiness",
        }

    try:
        inspect = celery_app.control.inspect(timeout=1.5)
        ping_result = await asyncio.to_thread(inspect.ping)
        if ping_result:
            return {
                "status": "healthy",
                "mode": "celery",
                "workers": sorted(ping_result.keys()),
            }
        return {
            "status": "unhealthy",
            "mode": "celery",
            "error": "No Celery workers responded to ping",
        }
    except Exception as exc:
        return {"status": "unhealthy", "mode": "celery", "error": str(exc)}


async def check_mcp() -> dict[str, Any]:
    """Verify MCP runtime/cache readiness when MCP servers are configured."""
    configured_servers = sorted(get_extensions_config().get_enabled_mcp_servers().keys())
    if not configured_servers:
        return {"status": "healthy", "configured_servers": [], "tool_count": 0}

    manager = peek_mcp_manager()
    if manager is None:
        return {
            "status": "unhealthy",
            "configured_servers": configured_servers,
            "error": "MCP runtime is not initialized",
        }

    try:
        tools = await manager.load_tools(force_reload=False)
        errors = manager.get_last_load_errors()
        if errors:
            return {
                "status": "unhealthy",
                "configured_servers": configured_servers,
                "tool_count": len(tools),
                "errors": errors,
            }
        return {
            "status": "healthy",
            "configured_servers": configured_servers,
            "tool_count": len(tools),
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "configured_servers": configured_servers,
            "error": str(exc),
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
    database, redis, task_backend, mcp, execution = await asyncio.gather(
        check_database(),
        check_redis(),
        check_task_backend(),
        check_mcp(),
        check_execution(),
    )
    checks = {
        "database": database,
        "redis": redis,
        "task_backend": task_backend,
        "mcp": mcp,
        "execution": execution,
    }
    overall = "healthy" if all(item.get("status") == "healthy" for item in checks.values()) else "unhealthy"
    return {
        "status": overall,
        "version": "2.0.0",
        "checks": checks,
    }


def build_liveness_report() -> dict[str, Any]:
    """Build minimal liveness payload that does not depend on downstream services."""
    return {
        "status": "alive",
        "version": "2.0.0",
    }

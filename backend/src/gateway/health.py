"""Gateway liveness and readiness checks."""

from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

from src.academic.cache.redis_client import redis_client
from src.config.app_config import celery_settings, get_prometheus_settings
from src.dataservice_client.provider import dataservice_client
from src.sandbox.preflight import run_sandbox_preflight
from src.services.mission_catalog_readiness import evaluate_mission_catalog_readiness
from src.services.model_catalog_cache import (
    get_default_runtime_model_id,
    get_runtime_model_config,
)
from src.task import celery_app

logger = logging.getLogger(__name__)
_READINESS_DEPENDENCY_TIMEOUT_SECONDS = 3.0


async def check_dataservice() -> dict[str, Any]:
    """Verify standalone DataService readiness."""
    try:
        async with dataservice_client() as client:
            report = await client.readyz()
        status = str(report.get("status") or "unhealthy")
        return {
            **report,
            "status": status,
            "service": report.get("service") or "dataservice",
        }
    except Exception as exc:
        return {"status": "unhealthy", "service": "dataservice", "error": str(exc)}


async def check_mission_catalog() -> dict[str, Any]:
    """Require an enabled, cross-referenced policy catalog for every workspace type."""
    try:
        async with dataservice_client() as client:
            policies = await client.list_mission_policies(enabled_only=True)
            skills = await client.list_worker_skills(enabled_only=True)
        try:
            model_id = get_default_runtime_model_id()
            model = get_runtime_model_config(model_id)
        except ValueError:
            model = None
        return evaluate_mission_catalog_readiness(
            policies,
            skills,
            mission_model=model,
        )
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
    return await _check_metrics_endpoint("worker")


async def _check_mission_worker_metrics_endpoint() -> tuple[bool, str | None]:
    """Verify the Mission worker that passed sandbox startup preflight."""
    return await _check_metrics_endpoint("mission-worker")


async def _check_metrics_endpoint(host: str) -> tuple[bool, str | None]:
    worker_port = int(get_prometheus_settings().worker_port)
    target = f"http://{host}:{worker_port}/metrics"

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


async def check_sandbox() -> dict[str, Any]:
    """Verify the operation sandbox required by Mission tools."""
    if celery_settings.enabled:
        metrics_ok, metrics_error = await _check_mission_worker_metrics_endpoint()
        return {
            "status": "healthy" if metrics_ok else "unhealthy",
            "provider": "docker",
            "execution_host": "mission-worker",
            "probe": "release_preflight_then_metrics",
            **({"error": metrics_error} if metrics_error else {}),
        }
    try:
        report = await run_sandbox_preflight(release_gate=False)
        return {
            "status": "healthy" if report.operational_ready else "unhealthy",
            "provider": report.provider,
            "checks": [check.model_dump(mode="json") for check in report.checks],
        }
    except Exception as exc:
        logger.warning("Sandbox readiness check failed: %s", exc, exc_info=True)
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

    dataservice, mission_catalog, redis, task_backend, sandbox = await asyncio.gather(
        _run_check_with_timeout("dataservice", check_dataservice),
        _run_check_with_timeout("mission_catalog", check_mission_catalog),
        _run_check_with_timeout("redis", check_redis),
        _run_check_with_timeout("task_backend", check_task_backend),
        _run_check_with_timeout("sandbox", check_sandbox),
    )
    checks = {
        "dataservice": dataservice,
        "mission_catalog": mission_catalog,
        "redis": redis,
        "task_backend": task_backend,
        "sandbox": sandbox,
    }
    required_dependencies = [
        "dataservice",
        "mission_catalog",
        "redis",
        "task_backend",
        "sandbox",
    ]
    required_failures = [name for name in required_dependencies if checks.get(name, {}).get("status") != "healthy"]
    optional_degradations = [name for name, report in checks.items() if name not in required_dependencies and report.get("status") != "healthy"]

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

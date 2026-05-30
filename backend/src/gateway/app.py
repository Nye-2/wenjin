"""FastAPI Gateway Application."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.app_config import celery_settings, get_settings, redis_settings
from src.gateway.middleware.correlation import correlation_middleware
from src.gateway.middleware.error_handler import register_error_handlers
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    # Initialize Sentry (must be before anything else)
    from src.observability.sentry import init_sentry
    init_sentry()

    # Initialize structured logging
    setup_logging(level="INFO")
    logger.info("Wenjin Gateway starting up...")

    # Connect Redis
    from src.academic.cache.redis_client import redis_client
    await redis_client.connect()
    await redis_client.connect_stream()

    try:
        from src.dataservice_client.provider import dataservice_client
        from src.services.model_catalog_cache import refresh_model_catalog_cache

        async with dataservice_client() as dataservice:
            snapshot = await refresh_model_catalog_cache(dataservice)
        logger.info(
            "Model catalog runtime cache loaded (%d models, version=%s)",
            len(snapshot.by_id),
            snapshot.version,
        )
    except Exception as exc:
        logger.warning(
            "Model catalog runtime cache warmup skipped: %s",
            exc,
            exc_info=True,
        )

    # Initialize run runtime singletons.
    from src.runtime.runs import RunManager
    from src.runtime.stream_bridge import RedisStreamBridge

    if not redis_settings.enabled:
        raise RuntimeError("Gateway run runtime requires REDIS_ENABLED=true")
    if not celery_settings.enabled:
        raise RuntimeError("Gateway run runtime requires CELERY_ENABLED=true")

    app.state.run_manager = RunManager(
        redis_backend=redis_client.client,
        run_ttl_seconds=settings.runtime_run_ttl_seconds,
    )
    await app.state.run_manager.hydrate_recent_runs(
        limit=settings.runtime_run_recovery_limit
    )
    app.state.stream_bridge = RedisStreamBridge(
        redis_client.stream_client,
        queue_maxsize=512,
        stream_ttl_seconds=settings.runtime_run_ttl_seconds,
    )
    logger.info(
        "Runtime run subsystem configured with Redis persistence "
        "(recovery_limit=%s ttl=%ss)",
        settings.runtime_run_recovery_limit,
        settings.runtime_run_ttl_seconds,
    )
    app.state.event_loop_watchdog_task = None

    # Detect severe event-loop blocking and force process restart to recover.
    # Skip in test environment to avoid destabilizing deterministic tests.
    if (
        settings.gateway_event_loop_watchdog_enabled
        and settings.environment.lower() != "test"
    ):
        from src.gateway.watchdog import run_event_loop_watchdog

        app.state.event_loop_watchdog_task = asyncio.create_task(
            run_event_loop_watchdog(
                interval_seconds=settings.gateway_event_loop_watchdog_interval_seconds,
                lag_threshold_seconds=settings.gateway_event_loop_watchdog_lag_threshold_seconds,
                max_consecutive_breaches=settings.gateway_event_loop_watchdog_max_breaches,
            )
        )

    # Reconcile task states that may have been interrupted by process restarts.
    from src.task.recovery import reconcile_interrupted_tasks

    await reconcile_interrupted_tasks()

    try:
        from src.config import get_extensions_config
        from src.mcp import activate_mcp_runtime

        await activate_mcp_runtime(
            extensions_config=get_extensions_config(),
            warmup=True,
        )
    except Exception as exc:
        logger.warning("MCP runtime warmup skipped: %s", exc, exc_info=True)

    yield

    # Shutdown
    logger.info("Wenjin Gateway shutting down...")
    try:
        from src.mcp import shutdown_mcp_runtime

        await shutdown_mcp_runtime()
    except Exception as exc:
        logger.warning("MCP runtime shutdown skipped: %s", exc, exc_info=True)
    stream_bridge = getattr(app.state, "stream_bridge", None)
    if stream_bridge is not None:
        try:
            await stream_bridge.close()
        except Exception:
            logger.warning("Failed to close stream bridge", exc_info=True)
    watchdog_task = getattr(app.state, "event_loop_watchdog_task", None)
    if watchdog_task is not None:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("Failed to stop event loop watchdog", exc_info=True)
    await redis_client.disconnect()


# Create FastAPI application
app = FastAPI(
    title="Wenjin API",
    description="问津 — AI workspace API for papers, proposals, patents, and research workflows",
    version="2.0.0",
    lifespan=lifespan,
)

# Register centralized error handlers
register_error_handlers(app)

# Load settings for CORS configuration
settings = get_settings()

# Add correlation ID middleware for request tracing
app.middleware("http")(correlation_middleware)

# Rate limiting middleware
from src.academic.cache.redis_client import redis_client as _redis_client
from src.gateway.middleware import setup_rate_limiting

setup_rate_limiting(app, redis_client=_redis_client)

# Prometheus metrics
from src.observability.prometheus import setup_prometheus

setup_prometheus(app)

# CORS middleware - configured from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/livez", include_in_schema=False)
async def live_check() -> dict[str, str]:
    """Process liveness endpoint."""
    from src.gateway.health import build_liveness_report

    return build_liveness_report()


@app.get("/readyz", include_in_schema=False)
async def readiness_check() -> Any:
    """Dependency-aware readiness endpoint."""
    from src.gateway.health import build_readiness_report

    report = await build_readiness_report()
    if report["status"] == "unhealthy":
        return JSONResponse(status_code=503, content=report)
    return report

# Include routers (imported after app creation to avoid circular imports)
from .routers import (  # noqa: E402
    admin_analytics,
    admin_capabilities,
    admin_credit_rules,
    admin_models,
    admin_pricing,
    admin_redeem_codes,
    admin_skills,
    artifacts,
    auth,
    capabilities,
    compute,
    credits_redeem,
    dashboard,
    execution_commit,
    executions,
    latex,
    mcp,
    memory,
    models,
    references,
    runs,
    templates,
    thread_runs,
    threads,
    uploads,
    workspace_rooms,
    workspaces,
)

app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(threads.router, prefix="/api", tags=["threads"])
app.include_router(thread_runs.router, prefix="/api", tags=["runs"])
app.include_router(runs.router, prefix="/api", tags=["runs"])
app.include_router(uploads.router, prefix="/api", tags=["uploads"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])
app.include_router(compute.router, prefix="/api", tags=["compute"])
app.include_router(latex.router, prefix="/api", tags=["latex"])
app.include_router(templates.router, prefix="/api", tags=["templates"])
app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
app.include_router(references.router, prefix="/api", tags=["references"])
app.include_router(mcp.router, prefix="/api", tags=["mcp"])
app.include_router(memory.router, prefix="/api", tags=["memory"])
app.include_router(executions.router, prefix="/api", tags=["executions"])
app.include_router(execution_commit.router, tags=["executions"])
app.include_router(workspace_rooms.router, prefix="/api", tags=["workspace_rooms"])
app.include_router(capabilities.router, prefix="/api", tags=["capabilities"])
app.include_router(admin_capabilities.router, prefix="/api", tags=["admin", "capabilities"])
app.include_router(admin_skills.router, prefix="/api", tags=["admin", "skills"])
app.include_router(admin_models.router, prefix="/api", tags=["admin", "models"])
app.include_router(admin_pricing.router, prefix="/api", tags=["admin", "pricing"])
app.include_router(admin_pricing.policies_router, prefix="/api", tags=["admin", "pricing"])
app.include_router(admin_analytics.router, prefix="/api", tags=["admin", "analytics"])
app.include_router(admin_credit_rules.router, prefix="/api", tags=["admin", "credits"])
app.include_router(admin_redeem_codes.router, prefix="/api", tags=["admin", "credits"])
app.include_router(credits_redeem.router, prefix="/api", tags=["credits"])

# Dev-only test hooks for Playwright e2e (Plan 3 T2). Disabled in production.
if settings.environment.lower() != "production":
    from .routers import dev_test_hooks  # noqa: E402
    app.include_router(dev_test_hooks.router)

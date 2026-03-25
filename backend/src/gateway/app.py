"""FastAPI Gateway Application."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.app_config import get_settings
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
    print("AcademiaGPT Gateway starting up...")

    # Initialize database
    from src.database import init_db
    await init_db()

    # Connect Redis
    from src.academic.cache.redis_client import redis_client
    await redis_client.connect()

    # Reconcile any tasks that were interrupted while using the in-process executor.
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
    print("AcademiaGPT Gateway shutting down...")
    try:
        from src.mcp import shutdown_mcp_runtime

        await shutdown_mcp_runtime()
    except Exception as exc:
        logger.warning("MCP runtime shutdown skipped: %s", exc, exc_info=True)
    await redis_client.disconnect()
    from src.database import close_db

    await close_db()


# Create FastAPI application
app = FastAPI(
    title="AcademiaGPT API",
    description="Academic AI Assistant API",
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
async def live_check():
    """Process liveness endpoint."""
    from src.gateway.health import build_liveness_report

    return build_liveness_report()


@app.get("/readyz", include_in_schema=False)
async def readiness_check():
    """Dependency-aware readiness endpoint."""
    from fastapi.responses import JSONResponse

    from src.gateway.health import build_readiness_report

    report = await build_readiness_report()
    if report["status"] != "healthy":
        return JSONResponse(status_code=503, content=report)
    return report


@app.get("/health", include_in_schema=False)
async def health_check():
    """Backward-compatible readiness alias."""
    return await readiness_check()


# Include routers (imported after app creation to avoid circular imports)
from src.api.subagents import router as subagents_router  # noqa: E402

from .routers import artifacts, auth, chat, dashboard, features, literature, mcp, memory, models, papers, tasks, workspaces  # noqa: E402

app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(subagents_router, prefix="/api", tags=["subagents"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])
app.include_router(features.router, prefix="/api", tags=["features"])
app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
app.include_router(literature.router, prefix="/api", tags=["literature"])
app.include_router(mcp.router, prefix="/api", tags=["mcp"])
app.include_router(memory.router, prefix="/api", tags=["memory"])
app.include_router(papers.router, prefix="/api", tags=["papers"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])

"""FastAPI Gateway Application."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from src.config.app_config import get_settings
from src.gateway.middleware.correlation import correlation_middleware
from src.gateway.middleware.error_handler import register_error_handlers
from src.logging_config import setup_logging


async def deprecation_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add Deprecation and Sunset headers to deprecated routes.

    Deprecated routes (retained for >=1 release cycle, sunset 2026-05-01):
    - /api/thesis/*  — thesis direct API (use feature execute instead)
    - academic router routes registered via ``academic.router``
      These overlap path-wise with the active ``papers.router``; we
      distinguish them by checking the matched route's ``tags``.
    """
    response: Response = await call_next(request)
    path = request.url.path

    is_deprecated = False
    # 1) thesis routes — simple prefix match, no overlap with other routers
    if path.startswith("/api/thesis/"):
        is_deprecated = True
    else:
        # 2) academic router routes — identified by their FastAPI tags
        route = request.scope.get("route")
        if route and hasattr(route, "tags") and "academic" in (route.tags or []):
            is_deprecated = True

    if is_deprecated:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2026-05-01"

    return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    # Initialize structured logging
    setup_logging(level="INFO")
    print("AcademiaGPT Gateway starting up...")

    # Initialize database
    from src.database import init_db
    await init_db()

    # Connect Redis
    from src.academic.cache.redis_client import redis_client
    await redis_client.connect()

    yield

    # Shutdown
    print("AcademiaGPT Gateway shutting down...")
    await redis_client.disconnect()


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

# Add deprecation signal middleware for retired routes
app.middleware("http")(deprecation_middleware)

# Add correlation ID middleware for request tracing
app.middleware("http")(correlation_middleware)

# Rate limiting middleware
from src.academic.cache.redis_client import redis_client as _redis_client
from src.gateway.middleware import setup_rate_limiting

setup_rate_limiting(app, redis_client=_redis_client)

# CORS middleware - configured from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0"}


# Include routers (imported after app creation to avoid circular imports)
from src.thesis.api import router as thesis_router  # noqa: E402

from .routers import academic, artifacts, auth, chat, dashboard, features, literature, models, papers, tasks, workspaces  # noqa: E402

app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(academic.router, prefix="/api", tags=["academic"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])
app.include_router(features.router, prefix="/api", tags=["features"])
app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
app.include_router(literature.router, prefix="/api", tags=["literature"])
app.include_router(papers.router, prefix="/api", tags=["papers"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(thesis_router, prefix="/api/thesis", tags=["thesis"])

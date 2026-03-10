"""FastAPI Gateway Application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.app_config import get_settings
from src.gateway.middleware.error_handler import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    print("AcademiaGPT Gateway starting up...")

    # Initialize database
    from src.academic.database.session import init_db
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
from .routers import academic, artifacts, auth, chat, models, papers, workspaces  # noqa: E402

app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(academic.router, prefix="/api", tags=["academic"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])
app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
app.include_router(papers.router, prefix="/api", tags=["papers"])

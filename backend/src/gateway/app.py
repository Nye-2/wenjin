"""FastAPI Gateway Application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0"}


# Include routers
from .routers import models, academic, chat, auth, workspaces, artifacts, papers

app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(academic.router, prefix="/api", tags=["academic"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])
app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
app.include_router(papers.router, prefix="/api", tags=["papers"])

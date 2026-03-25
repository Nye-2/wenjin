"""Routers module initialization."""

from .artifacts import router as artifacts_router
from .auth import router as auth_router
from .chat import router as chat_router
from .dashboard import router as dashboard_router
from .literature import router as literature_router
from .mcp import router as mcp_router
from .memory import router as memory_router
from .models import router as models_router

__all__ = [
    "models_router",
    "chat_router",
    "auth_router",
    "dashboard_router",
    "artifacts_router",
    "literature_router",
    "mcp_router",
    "memory_router",
]

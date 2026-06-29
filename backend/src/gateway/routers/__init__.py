"""Routers module initialization."""

from .artifacts import router as artifacts_router
from .auth import router as auth_router
from .compute import router as compute_router
from .dashboard import router as dashboard_router
from .mcp import router as mcp_router
from .models import router as models_router
from .references import router as references_router
from .runs import router as runs_router
from .thread_runs import router as thread_runs_router
from .threads import router as threads_router

__all__ = [
    "models_router",
    "auth_router",
    "compute_router",
    "dashboard_router",
    "artifacts_router",
    "references_router",
    "mcp_router",
    "runs_router",
    "thread_runs_router",
    "threads_router",
]

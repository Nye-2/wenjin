"""Routers module initialization."""

from .academic import router as academic_router
from .artifacts import router as artifacts_router
from .auth import router as auth_router
from .chat import router as chat_router
from .models import router as models_router

__all__ = ["models_router", "academic_router", "chat_router", "auth_router", "artifacts_router"]

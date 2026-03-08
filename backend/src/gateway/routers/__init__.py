"""Routers module initialization."""

from .models import router as models_router
from .academic import router as academic_router
from .chat import router as chat_router

__all__ = ["models_router", "academic_router", "chat_router"]

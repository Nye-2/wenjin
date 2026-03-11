"""AcademiaGPT v2 Backend package."""

from src import models
from src import database
from src import agents
from src import services
from src import academic
from src import gateway
from src import execution
from src import config

__all__ = [
    "models",
    "database",
    "agents",
    "services",
    "academic",
    "gateway",
    "execution",
    "config",
]

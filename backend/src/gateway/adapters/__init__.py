"""Frontend API adapters for bridging frontend with backend services.

This module provides adapter classes that translate between frontend API
requests and backend service calls.
"""

from .skill_adapter import SkillAdapter
from .workspace_adapter import WorkspaceAdapter

__all__ = [
    "SkillAdapter",
    "WorkspaceAdapter",
]

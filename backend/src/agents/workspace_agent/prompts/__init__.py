"""WorkspaceAgent prompt package."""

from .mission import render_workspace_mission_prompt
from .principles import SHARED_OPERATING_RULES, WORKSPACE_AGENT_IDENTITY
from .system import render_workspace_agent_prompt

__all__ = [
    "SHARED_OPERATING_RULES",
    "WORKSPACE_AGENT_IDENTITY",
    "render_workspace_agent_prompt",
    "render_workspace_mission_prompt",
]

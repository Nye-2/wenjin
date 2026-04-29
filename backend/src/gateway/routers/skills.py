"""Skills router for workspace skill discovery.

Skills are conversational entry points for workspace features.
They provide UI metadata and LLM guidance prompts.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.academic.services.workspace_service import WorkspaceService
from src.agents.lead_agent.thread_skill_catalog import list_workspace_thread_skills
from src.application.workspace_resolvers import resolve_workspace_type
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_workspace_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["skills"])


class SkillResponse(BaseModel):
    """A skill available in a workspace."""

    id: str
    name: str
    description: str
    featureId: str
    icon: str
    color: str
    guidancePrompt: str
    followUpSkills: list[str]


class SkillsListResponse(BaseModel):
    """Response for skills list."""

    skills: list[SkillResponse]


@router.get(
    "/workspaces/{workspace_id}/skills",
    response_model=SkillsListResponse,
)
async def get_workspace_skills(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> SkillsListResponse:
    """Get available skills for a workspace."""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        workspace_type = resolve_workspace_type(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    skills = [
        SkillResponse(**skill.to_api_dict())
        for skill in list_workspace_thread_skills(workspace_type)
    ]
    return SkillsListResponse(skills=skills)

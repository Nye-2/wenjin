"""Workspace-aware chat skill catalog shared by bridge and prompt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkspaceChatSkillDefinition:
    """Declarative chat skill entry for a workspace."""

    id: str
    description: str
    feature_id: str
    defaults: tuple[tuple[str, Any], ...] = ()
    name: str = ""
    icon: str = "sparkles"
    color: str = "blue"
    guidance_prompt: str = ""
    follow_up_skills: tuple[str, ...] = ()

    def to_mapping_entry(self) -> tuple[str, dict[str, Any]]:
        return self.feature_id, dict(self.defaults)

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize for the REST API."""
        return {
            "id": self.id,
            "name": self.name or self.id.replace("-", " ").title(),
            "description": self.description,
            "featureId": self.feature_id,
            "icon": self.icon,
            "color": self.color,
            "guidancePrompt": self.guidance_prompt,
            "followUpSkills": list(self.follow_up_skills),
        }


WORKSPACE_CHAT_SKILLS: dict[str, tuple[WorkspaceChatSkillDefinition, ...]] = {
    "thesis": (
        WorkspaceChatSkillDefinition(
            id="deep-research",
            description="Comprehensive literature analysis and idea generation",
            feature_id="deep_research",
        ),
        WorkspaceChatSkillDefinition(
            id="framework-designer",
            description="Generate thesis outline and chapter structure",
            feature_id="thesis_writing",
            defaults=(("action", "generate_outline"),),
        ),
        WorkspaceChatSkillDefinition(
            id="fullpaper-writer",
            description="Draft the whole thesis from the current workspace context",
            feature_id="thesis_writing",
            defaults=(("action", "write_all"),),
        ),
        WorkspaceChatSkillDefinition(
            id="literature-review",
            description="Generate a literature-review style opening research report",
            feature_id="opening_research",
            defaults=(("report_type", "literature_review"),),
        ),
    ),
    "sci": (
        WorkspaceChatSkillDefinition(
            id="deep-research",
            description="Search literature and identify research gaps",
            feature_id="literature_search",
        ),
        WorkspaceChatSkillDefinition(
            id="framework-designer",
            description="Generate abstract, keywords, and paper outline",
            feature_id="framework_outline",
        ),
        WorkspaceChatSkillDefinition(
            id="literature-review",
            description="Turn current context into a structured literature review",
            feature_id="literature_review",
        ),
        WorkspaceChatSkillDefinition(
            id="peer-reviewer",
            description="Review the latest draft and highlight revision priorities",
            feature_id="peer_review",
        ),
        WorkspaceChatSkillDefinition(
            id="journal-recommender",
            description="Recommend candidate journals from the current manuscript state",
            feature_id="journal_recommend",
        ),
    ),
    "proposal": (
        WorkspaceChatSkillDefinition(
            id="proposal-writer",
            description="Generate a proposal outline from the current task context",
            feature_id="proposal_outline",
        ),
        WorkspaceChatSkillDefinition(
            id="experiment-designer",
            description="Design experiments, variables, and evaluation strategy",
            feature_id="experiment_design",
        ),
    ),
    "software_copyright": (),
    "patent": (),
}

SKILL_TO_FEATURE: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {
    workspace_type: {
        skill.id: skill.to_mapping_entry()
        for skill in skills
    }
    for workspace_type, skills in WORKSPACE_CHAT_SKILLS.items()
}


def list_workspace_chat_skills(
    workspace_type: str | None,
) -> tuple[WorkspaceChatSkillDefinition, ...]:
    """Return chat skill definitions for the given workspace type."""
    if not workspace_type:
        return ()
    return WORKSPACE_CHAT_SKILLS.get(workspace_type, ())


def get_skill_by_id(
    workspace_type: str | None,
    skill_id: str,
) -> WorkspaceChatSkillDefinition | None:
    """Look up a single skill by id within a workspace type."""
    for skill in list_workspace_chat_skills(workspace_type):
        if skill.id == skill_id:
            return skill
    return None

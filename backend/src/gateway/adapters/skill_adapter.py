"""Adapter for bridging frontend API with skill services.

This module provides the SkillAdapter class that translates frontend API
requests into skill service calls and formats responses for frontend consumption.
"""

from typing import Any

from src.skills.loader import load_skills


class SkillAdapter:
    """Adapter for skill-related frontend API operations.

    This adapter bridges the frontend API with the backend skill loading
    system, providing methods to list and retrieve skill metadata.

    The adapter uses the existing skill loader from src/skills/loader.py
    to discover and parse skills from the skills directory.
    """

    async def list_skills(self) -> list[dict[str, Any]]:
        """List all available skills.

        Returns:
            List of skill metadata dictionaries, each containing:
            - name: Unique skill identifier
            - description: Human-readable skill description
            - license: License type (e.g., MIT)
            - enabled: Whether the skill is enabled
            - allowed_tools: Tuple of allowed tool names
        """
        skills = load_skills()
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "license": skill.license,
                "enabled": skill.enabled,
                "allowed_tools": list(skill.allowed_tools),
            }
            for skill in skills
        ]

    async def get_skill(self, name: str) -> dict[str, Any] | None:
        """Get a specific skill by name.

        Args:
            name: The unique name of the skill to retrieve.

        Returns:
            Skill metadata dictionary if found, None otherwise.
            The dictionary contains:
            - name: Unique skill identifier
            - description: Human-readable skill description
            - license: License type
            - enabled: Whether the skill is enabled
            - allowed_tools: List of allowed tool names
            - content: The skill's markdown content
        """
        skills = load_skills()
        for skill in skills:
            if skill.name == name:
                return {
                    "name": skill.name,
                    "description": skill.description,
                    "license": skill.license,
                    "enabled": skill.enabled,
                    "allowed_tools": list(skill.allowed_tools),
                    "content": skill.content,
                }
        return None

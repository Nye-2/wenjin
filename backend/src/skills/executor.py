"""Skill executor for managing and executing skills.

This module provides the SkillExecutor class which handles skill registration,
lookup, and execution. It serves as the central registry for all skills
in the AcademiaGPT system.
"""

from typing import Optional

from src.agents.thread_state import ThreadState
from src.skills.base import BaseSkill, SkillInput, SkillOutput


class SkillNotFoundError(Exception):
    """Raised when a requested skill is not registered."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        super().__init__(f"Skill not found: {skill_name}")


class SkillValidationError(Exception):
    """Raised when skill input validation fails."""

    def __init__(self, skill_name: str, error_message: str):
        self.skill_name = skill_name
        self.error_message = error_message
        super().__init__(f"Validation failed for skill '{skill_name}': {error_message}")


class SkillExecutionError(Exception):
    """Raised when skill execution fails."""

    def __init__(self, skill_name: str, original_error: Exception):
        self.skill_name = skill_name
        self.original_error = original_error
        super().__init__(f"Execution failed for skill '{skill_name}': {original_error}")


class SkillExecutor:
    """Central registry and executor for skills.

    The SkillExecutor manages skill registration and provides methods
    to execute skills by name, list available skills, and retrieve
    skill instances.

    Example:
        executor = SkillExecutor()
        executor.register_skill(MySkill())
        output = executor.execute("my_skill", skill_input, state)
    """

    def __init__(self) -> None:
        """Initialize an empty skill registry."""
        self._skills: dict[str, BaseSkill] = {}

    def register_skill(self, skill: BaseSkill) -> None:
        """Register a skill instance with the executor.

        If a skill with the same name already exists, it will be replaced.

        Args:
            skill: The BaseSkill instance to register.
        """
        if not isinstance(skill, BaseSkill):
            raise TypeError(f"Expected BaseSkill instance, got {type(skill).__name__}")
        self._skills[skill.name] = skill

    def unregister_skill(self, skill_name: str) -> bool:
        """Unregister a skill by name.

        Args:
            skill_name: The name of the skill to unregister.

        Returns:
            True if the skill was unregistered, False if it wasn't found.
        """
        if skill_name in self._skills:
            del self._skills[skill_name]
            return True
        return False

    def execute(self, skill_name: str, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute a skill by name with the given input and state.

        This method validates the input, executes the skill, and handles
        any errors that occur during execution.

        Args:
            skill_name: The name of the skill to execute.
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state.

        Returns:
            SkillOutput containing the results of the skill execution.

        Raises:
            SkillNotFoundError: If the skill is not registered.
            SkillValidationError: If input validation fails.
            SkillExecutionError: If the skill execution fails unexpectedly.
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            raise SkillNotFoundError(skill_name)

        # Validate input
        validation_error = skill.validate_input(input)
        if validation_error is not None:
            raise SkillValidationError(skill_name, validation_error)

        # Execute the skill
        try:
            output = skill.execute(input, state)
            return output
        except Exception as e:
            # If the skill already returned an error output, pass it through
            if isinstance(e, SkillExecutionError):
                raise
            raise SkillExecutionError(skill_name, e) from e

    def list_skills(self) -> list[str]:
        """List all registered skill names.

        Returns:
            A sorted list of registered skill names.
        """
        return sorted(self._skills.keys())

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """Get a skill instance by name.

        Args:
            name: The name of the skill to retrieve.

        Returns:
            The BaseSkill instance if found, None otherwise.
        """
        return self._skills.get(name)

    def has_skill(self, name: str) -> bool:
        """Check if a skill is registered.

        Args:
            name: The name of the skill to check.

        Returns:
            True if the skill is registered, False otherwise.
        """
        return name in self._skills

    def get_skill_info(self, name: str) -> Optional[dict]:
        """Get information about a skill.

        Args:
            name: The name of the skill.

        Returns:
            A dictionary with skill information, or None if not found.
        """
        skill = self.get_skill(name)
        if skill is None:
            return None
        return {
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
        }

    def get_all_skills_info(self) -> list[dict]:
        """Get information about all registered skills.

        Returns:
            A list of dictionaries with skill information.
        """
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
            }
            for skill in self._skills.values()
        ]

    def clear(self) -> None:
        """Clear all registered skills."""
        self._skills.clear()

    def __len__(self) -> int:
        """Return the number of registered skills."""
        return len(self._skills)

    def __contains__(self, skill_name: str) -> bool:
        """Check if a skill is registered using 'in' operator."""
        return skill_name in self._skills

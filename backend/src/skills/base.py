"""Base skill classes for the skill execution framework.

This module provides the foundational classes for implementing skills
in Wenjin. Skills are specialized capabilities that can be dynamically
executed by the lead agent.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from src.agents.thread_state import AcademicArtifact, ThreadState


class SkillInput(BaseModel):
    """Input model for skill execution.

    Attributes:
        workspace_id: The workspace context for this skill execution.
        user_query: The user's query or request to process.
        context: Additional context data for the skill.
    """

    workspace_id: str = Field(..., description="The workspace context for this skill execution")
    user_query: str = Field(..., description="The user's query or request to process")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context data for the skill",
    )


class SkillOutput(BaseModel):
    """Output model for skill execution.

    Attributes:
        success: Whether the skill execution was successful.
        content: The main content/result from the skill.
        artifacts: List of academic artifacts produced by the skill.
        metadata: Additional metadata about the execution.
        error_message: Error message if success is False.
    """

    success: bool = Field(default=True, description="Whether the skill execution was successful")
    content: str = Field(default="", description="The main content/result from the skill")
    artifacts: list[AcademicArtifact] = Field(
        default_factory=list,
        description="List of academic artifacts produced by the skill",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the execution",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if success is False",
    )


class BaseSkill(ABC):
    """Abstract base class for all skills.

    All skills in Wenjin must inherit from this class
    and implement the execute method.

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description of the skill.
        version: Version string for the skill.
    """

    name: str
    description: str
    version: str = "1.0.0"

    @abstractmethod
    def execute(self, input: SkillInput, state: ThreadState) -> SkillOutput:
        """Execute the skill with the given input and state.

        Args:
            input: The skill input containing workspace_id, user_query, and context.
            state: The current thread state for context and artifact storage.

        Returns:
            SkillOutput containing the results of the skill execution.
        """
        pass

    def validate_input(self, input: SkillInput) -> str | None:
        """Validate the input before execution.

        Override this method to add custom validation logic.

        Args:
            input: The skill input to validate.

        Returns:
            None if validation passes, or an error message string if validation fails.
        """
        if not input.workspace_id:
            return "workspace_id is required"
        if not input.user_query or not input.user_query.strip():
            return "user_query cannot be empty"
        return None

    def __repr__(self) -> str:
        """Return a string representation of the skill."""
        return f"{self.__class__.__name__}(name={self.name!r}, version={self.version!r})"

"""TaskBrief contract — describes a unit of work dispatched to a subagent."""

from pydantic import BaseModel, Field


class TaskBrief(BaseModel):
    """Describes a unit of work dispatched from the lead agent to a capability executor.

    Attributes:
        capability_id: Identifier for the capability being invoked.
        brief: Capability-specific input data conforming to the capability's brief_schema.
        raw_message: The original user message that triggered this task.
        decisions: Prior decisions to carry forward (key → value).
        workspace_id: Identifier of the workspace this task belongs to.
    """

    capability_id: str = Field(..., min_length=1)
    brief: dict = Field(default_factory=dict)
    raw_message: str = Field(..., min_length=1)
    decisions: dict[str, str] = Field(default_factory=dict)
    workspace_id: str = Field(default="")

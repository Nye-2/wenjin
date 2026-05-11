"""Subagent v2 base classes — SubagentContext, SubagentResult, SubagentBase."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.database.models.capability_skill import CapabilitySkill


@dataclass
class SubagentContext:
    """Execution context passed into every subagent run call.

    Attributes:
        workspace_id: Workspace the execution belongs to.
        execution_id: Unique identifier for this execution run.
        prompt: The assembled prompt for this subagent.
        inputs: Capability-specific input data.
        tools: Names of tools this subagent is allowed to use.
        workspace_data: Snapshot of workspace rooms (library, decisions, etc.).
    """

    workspace_id: str
    execution_id: str
    prompt: str
    inputs: dict
    tools: list[str]
    workspace_data: dict = field(default_factory=dict)
    skill: CapabilitySkill | None = None


@dataclass
class SubagentResult:
    """Structured result returned by a subagent after execution.

    Attributes:
        output: Primary output data (shape is subagent-specific).
        thinking: Optional chain-of-thought or reasoning trace.
        tool_calls: Optional list of tool invocation records.
        token_usage: Optional token usage statistics.
    """

    output: dict
    thinking: str | None = None
    tool_calls: list[dict] | None = None
    token_usage: dict | None = None


class SubagentBase(ABC):
    """Abstract base class for all v2 subagents.

    Subclasses must:
    1. Be decorated with @subagent(name) to register in the global REGISTRY.
    2. Implement the async run() method.
    3. Declare allowed_tools (may be empty for pure-compute agents).
    """

    name: str = ""
    allowed_tools: list[str] = []

    @abstractmethod
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        """Execute the subagent logic given the provided context.

        Args:
            ctx: Execution context including inputs, workspace snapshot, and tool whitelist.

        Returns:
            SubagentResult with output matching this subagent's documented output shape.
        """
        ...

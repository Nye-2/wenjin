"""Subagent v2 base classes — SubagentContext, SubagentResult, SubagentBase."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


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
    capability_policy: dict = field(default_factory=dict)
    skill: Any | None = None
    team_context: dict[str, Any] = field(default_factory=dict)
    invocation: dict[str, Any] | None = None
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None
    publish_event: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None
    expert_snapshot_emitter: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    async def emit(self, event_type: str, content: str) -> None:
        """Emit an incremental delta event. No-op when emit_delta is not set."""
        if self.emit_delta is not None:
            await self.emit_delta(event_type, content)

    async def emit_expert_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Emit a user-visible expert progress snapshot. No-op outside team runtime."""
        if self.expert_snapshot_emitter is not None:
            await self.expert_snapshot_emitter(snapshot)


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
    metadata: dict | None = None


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

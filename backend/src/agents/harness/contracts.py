"""Contracts for Compute-scoped agent harness providers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.subagents.parallel import PhasedPlan, PhaseResult


@dataclass(frozen=True, slots=True)
class SubtaskRequest:
    """Single agentic subtask request bound to an execution session."""

    subagent_type: str
    prompt: str
    context: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubtaskResult:
    """Provider-neutral single subtask result."""

    subagent_type: str
    success: bool
    result: Any = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AgentSessionRequest:
    """Multi-step agentic session request owned by a Compute session."""

    strategy: str
    phased_plan: PhasedPlan
    context: Mapping[str, Any]
    phase_callback: Callable[[PhaseResult], Awaitable[None]] | None = None


@dataclass(frozen=True, slots=True)
class AgentSessionResult:
    """Provider-neutral session result returned to feature runtime."""

    provider: str
    strategy: str
    phase_results: list[PhaseResult]


@runtime_checkable
class AgentHarness(Protocol):
    """Execution boundary for native, DeerFlow, Claude SDK, or Codex providers."""

    provider: str

    async def run_subtask(self, request: SubtaskRequest) -> SubtaskResult:
        """Run one bound subtask and return a structured result."""

    async def run_session(self, request: AgentSessionRequest) -> AgentSessionResult:
        """Run a bound multi-phase agentic session."""

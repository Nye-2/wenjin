"""Codex harness adapter placeholder."""

from __future__ import annotations

from .contracts import AgentSessionRequest, AgentSessionResult, SubtaskRequest, SubtaskResult


class CodexAgentAdapter:
    """Future Codex provider boundary for Compute-scoped agent sessions."""

    provider = "codex"

    async def run_subtask(self, request: SubtaskRequest) -> SubtaskResult:
        _ = request
        raise NotImplementedError("Codex harness provider is not enabled")

    async def run_session(self, request: AgentSessionRequest) -> AgentSessionResult:
        _ = request
        raise NotImplementedError("Codex harness provider is not enabled")

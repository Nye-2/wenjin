"""Claude Agent SDK harness adapter placeholder."""

from __future__ import annotations

from .contracts import AgentSessionRequest, AgentSessionResult, SubtaskRequest, SubtaskResult


class ClaudeAgentSdkAdapter:
    """Future Claude provider boundary for Compute-scoped agent sessions."""

    provider = "claude_agent_sdk"

    async def run_subtask(self, request: SubtaskRequest) -> SubtaskResult:
        _ = request
        raise NotImplementedError("Claude Agent SDK harness provider is not enabled")

    async def run_session(self, request: AgentSessionRequest) -> AgentSessionResult:
        _ = request
        raise NotImplementedError("Claude Agent SDK harness provider is not enabled")

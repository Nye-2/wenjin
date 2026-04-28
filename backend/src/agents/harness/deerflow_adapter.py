"""DeerFlow AgentHarness adapter placeholder.

The adapter is intentionally disabled until a feature runtime profile selects it.
"""

from __future__ import annotations

from .contracts import AgentSessionRequest, AgentSessionResult, SubtaskRequest, SubtaskResult


class DeerFlowHarnessAdapter:
    """Future DeerFlow provider boundary for Compute-scoped agent sessions."""

    provider = "deerflow"

    async def run_subtask(self, request: SubtaskRequest) -> SubtaskResult:
        _ = request
        raise NotImplementedError("DeerFlow harness provider is not enabled")

    async def run_session(self, request: AgentSessionRequest) -> AgentSessionResult:
        _ = request
        raise NotImplementedError("DeerFlow harness provider is not enabled")

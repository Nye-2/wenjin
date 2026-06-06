from __future__ import annotations

import pytest

from src.agents.harness.contracts import HarnessRunContext
from src.agents.harness.events import publish_harness_event


@pytest.mark.asyncio
async def test_publish_harness_event_uses_existing_execution_event_publisher() -> None:
    calls: list[tuple[str, str, dict]] = []

    async def publisher(execution_id: str, event_type: str, payload: dict) -> None:
        calls.append((execution_id, event_type, payload))

    ctx = HarnessRunContext(
        workspace_id="ws-1",
        user_id="user-1",
        execution_id="exec-1",
        node_id="node-1",
        invocation_id="invocation-1",
        workspace_type="sci",
        capability_id="capability-1",
        publish_event=publisher,
    )

    await publish_harness_event(
        ctx,
        "tool_call.completed",
        visibility="debug_only",
        sequence_kind="tool",
        payload={"name": "sandbox.read_file", "status": "completed"},
    )

    assert calls == [
        (
            "exec-1",
            "execution.harness.tool_call.completed",
            {
                "execution_id": "exec-1",
                "node_id": "node-1",
                "invocation_id": "invocation-1",
                "workspace_id": "ws-1",
                "visibility": "debug_only",
                "sequence_kind": "tool",
                "payload": {"name": "sandbox.read_file", "status": "completed"},
            },
        )
    ]
